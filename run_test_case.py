"""Runs a markdown test-case doc (see test_case.py for the expected format)
step by step against a booted simulator's frontmost native app.

Each step's Action is executed via the same perception -> reasoning -> action
loop as agent.py, bounded to a small per-step budget (a single test-case row
like "Enter a valid first and last name" may take several taps/types). After
each step, a separate model call (reasoning.judge_step) gives a best-effort
verdict against that step's Expected Result text.

IMPORTANT, verified limitation: judge_step is the local model self-grading
against prose, not an authoritative check. Verified directly: it can be
internally self-contradictory (returned passed=True with a reason stating
the opposite). Treat PASS/FAIL in the output as a first-pass signal to
review, not a substitute for a human checking the actual screenshots.

If a step's action loop fails outright (no matching label, perception/
reasoning error, or its step budget is exhausted without task_complete),
that step is marked FAIL and every remaining step is marked BLOCKED — a
failed step generally invalidates the rest of a scripted flow, and
continuing would produce meaningless verdicts against a broken flow.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from perception import capture_state, capture_elements, PerceptionError
from reasoning import decide_next_action, judge_step, ReasoningError, MODEL as REASONING_MODEL
from actions import execute, ActionError, resolve_label, _probe_native_header, TEXT_ENTRY_TYPES
from test_case import parse_test_case, write_results, TestCaseError, extract_quoted_strings
from agent import preflight, log, _describe

DEFAULT_STEPS_PER_ACTION = 4


def _action_signature(action):
    """Identity of an action for repeat-detection, ignoring extra keys the
    model sometimes hallucinates onto a call beyond its declared schema.
    Verified real case: a `type` call was repeated with a spurious extra
    'label' key not part of type's schema, making a raw dict comparison
    miss an otherwise-identical repeat."""
    kind = action.get("action")
    if kind == "tap":
        return (kind, action.get("label"))
    if kind == "type":
        return (kind, action.get("text"))
    if kind == "swipe":
        return (kind, action.get("from_x"), action.get("from_y"), action.get("to_x"), action.get("to_y"))
    return (kind,)


def _instructs_typing(action_text):
    """True if a test-case row's own instruction text (from the markdown doc
    itself, not history) is asking for text entry, e.g. 'Type "user1".' —
    this test-case format's own convention (see signin_use_case.md). Used
    only to validate that a row which explicitly asks for typing actually
    attempted a type() call at least once, not to inspect history content."""
    return action_text.strip().lower().startswith("type")


# Verified real, reproducible failure: the product detail page fetches its
# content asynchronously and shows a transient placeholder ({'Expo Go',
# 'Loading...', 'gearshape.fill'} — nothing else) before the real content
# renders. A fixed 1s settle delay after the triggering tap (actions.py's
# earlier TAP_SETTLE_DELAY) was not reliably enough on this machine — under
# real memory pressure the actual fetch/render time varies a lot, so a
# single guessed duration either wastes time when it's fast or still isn't
# enough when it's slow. Actively re-checking until the placeholder is gone
# (or a bounded ceiling is hit) adapts to that instead of guessing — and
# polling with capture_elements (no screenshot) rather than full
# capture_state on every retry means the wait itself doesn't pay for a
# screenshot on every poll, only once the row has actually settled.
LOADING_WAIT_POLL_INTERVAL = 0.3
LOADING_WAIT_MAX_RETRIES = 30  # ~9s ceiling at 0.3s/poll — same ceiling as the previous 6x1.5s design


def _looks_like_loading(elements):
    """True for a transient async-loading placeholder, not just any small
    screen (a real empty state — e.g. 'Your cart is empty' — is also small
    but must not be waited out). Requires both a small element count and an
    explicit 'Loading' label, matching the verified real case above."""
    if len(elements) > 5:
        return False
    return any("loading" in (el.get("label") or "").lower() for el in elements)


def _capture_with_loading_wait(step_counter, udid, state_dir):
    """Polls capture_elements() (cheap — no screenshot) while
    _looks_like_loading(), then takes one real capture_state() (with its
    screenshot) once the row has settled or the retry ceiling is hit —
    shared by the deterministic fast path and run_step's own LLM loop so
    both use the same policy instead of duplicating it. Raises
    PerceptionError like capture_state (uncaught here; callers already
    handle it)."""
    step_counter[0] += 1
    n = step_counter[0]
    elements = capture_elements(udid)
    retry = 0
    while _looks_like_loading(elements) and retry < LOADING_WAIT_MAX_RETRIES:
        log("waiting_for_content_to_load", step=n, retry=retry,
            labels=[el["label"] for el in elements])
        time.sleep(LOADING_WAIT_POLL_INTERVAL)
        elements = capture_elements(udid)
        retry += 1
    return capture_state(n, udid, state_dir)


def _try_deterministic_action(action_text, udid, state_dir, step_counter, last_tapped_type_ref):
    """Attempts to resolve and execute a row's action with zero LLM calls,
    when the row's own instruction text unambiguously names its target —
    e.g. 'Tap the "Sign in" link.' or 'Type "user1@xyz.com".'. Verified
    against the real test-case docs: 34 of 36 rows across signin_use_case.md
    and make_order_use_case.md quote exactly one target this way.

    Returns one of:
      ("not_applicable", reason) — no idb call attempted; caller falls
          through into the existing LLM-agentic loop unchanged.
      ("ok", action, result, screenshot) — executed successfully.
      ("failed", action, error, screenshot) — idb genuinely failed; this is
          a real row failure, not a signal to fall back (the existing LLM
          loop treats a real ActionError from a tap the same way).

    The quote-count and typing-focus checks happen before any idb call, so
    rows that obviously need the LLM (no quoted target, e.g. make_order's
    "Tap the first product..." or "Tap the back button...") cost nothing
    extra. The typing-focus guard is checked here explicitly — mirroring
    actions.execute's own internal guard — rather than relying on catching
    execute's exception, so that once execute() is actually called for a
    `type`, any ActionError it raises is unambiguously a genuine idb
    failure, not a guard rejection; this also avoids the LLM fallback loop
    re-sending characters into a field this attempt may have half-typed."""
    quoted = extract_quoted_strings(action_text)
    if len(quoted) != 1:
        return ("not_applicable", f"expected exactly 1 quoted target, found {len(quoted)}")
    target = quoted[0]

    if _instructs_typing(action_text):
        if last_tapped_type_ref[0] not in TEXT_ENTRY_TYPES:
            return ("not_applicable",
                    f"typing instructed but no text-entry field known-focused "
                    f"(last_tapped_type={last_tapped_type_ref[0]!r})")
        state = _capture_with_loading_wait(step_counter, udid, state_dir)
        action = {"action": "type", "text": target}
        try:
            result = execute(action, state["elements"], udid, last_tapped_type_ref[0])
        except ActionError as e:
            return ("failed", action, str(e), state["screenshot"])
        return ("ok", action, result, state["screenshot"])

    state = _capture_with_loading_wait(step_counter, udid, state_dir)
    try:
        resolve_label(target, state["elements"])
    except ActionError as e:
        # Mirrors actions.execute's own fallback: a native nav-bar button
        # (e.g. a headerLeft back button) never appears in state["elements"]
        # at all — idb's full-tree walk collapses it into an unlabeled
        # opaque Group — even when it carries a real accessibilityLabel.
        # Only treat this row as deterministically resolvable if the same
        # verified-label probe execute() would use actually finds it.
        if _probe_native_header(target, state["elements"], udid) is None:
            return ("not_applicable", f"quoted target {target!r} not resolvable: {e}")
    action = {"action": "tap", "label": target}
    try:
        result = execute(action, state["elements"], udid, last_tapped_type_ref[0])
    except ActionError as e:
        return ("failed", action, str(e), state["screenshot"])
    return ("ok", action, result, state["screenshot"])


def run_step(scenario, preconditions, action_text, udid, state_dir, step_counter, history, max_sub_steps,
             last_tapped_type_ref, last_tapped_label_ref):
    """Runs one test-case row's Action to completion (or failure). Returns
    (ok: bool, error: str|None). `step_counter`, `last_tapped_type_ref` and
    `last_tapped_label_ref` are single-item lists used as mutable state so
    screenshot numbering, the tap/type guard, and (for main()'s deterministic
    verdict check) the label of whatever was last tapped all carry over
    continuously across the whole test case (not just within one row).
    `history` is different: the caller seeds it with at most the previous
    row's final action (see main()) rather than the whole test case's
    history — this function just reads/appends to whatever list it's
    handed, same as before.

    First tries _try_deterministic_action() — a zero-LLM-call fast path for
    rows whose instruction unambiguously quotes its own target (verified:
    34 of 36 real rows across both test-case docs do). Falls straight
    through into the existing LLM-agentic loop below, completely unchanged,
    whenever the fast path doesn't apply."""
    fast_kind, *fast_rest = _try_deterministic_action(
        action_text, udid, state_dir, step_counter, last_tapped_type_ref)

    if fast_kind == "ok":
        action, result, screenshot = fast_rest
        log("deterministic_action_used", step=step_counter[0], action=action,
            result=result, screenshot=screenshot)
        history.append(_describe(action))
        last_tapped_type_ref[0] = result.get("element_type") if action["action"] == "tap" else None
        last_tapped_label_ref[0] = result.get("resolved_label") if action["action"] == "tap" else None
        return True, None

    if fast_kind == "failed":
        action, error, screenshot = fast_rest
        log("deterministic_action_failed", step=step_counter[0], action=action,
            error=error, screenshot=screenshot)
        return False, f"deterministic action failed: {error}"

    log("deterministic_action_not_applicable", step=step_counter[0],
        action_text=action_text, reason=fast_rest[0])

    # Verified real failure this targets: for a row whose instruction was
    # "Type 'user1@xyz.com'." into a field already tapped/focused by the
    # *previous* row, the model repeated tap("Username or email") instead of
    # ever calling type() — it never attempted the actual instruction, and
    # the row only failed loudly because of the step_repeat_detected_but_
    # never_typed guard below (previously it silently "completed" instead).
    # Two earlier attempts at fixing this via wording alone did not work:
    # (1) a combined "if not focused tap, if focused type" conditional in
    # this same task text, and (2) rewording the `type` tool's own schema
    # description in reasoning.py. Both still let the model choose to tap.
    # This test-case format already gives each row exactly one action (a
    # separate "Tap the X field." row always precedes a "Type '...'." row —
    # see signin_use_case.md) so which one applies is not actually ambiguous
    # information the model needs to infer; it's known deterministically
    # from the row's own instruction text via _instructs_typing(). Removing
    # the tap-or-type branch entirely and giving a single, unconditional
    # instruction per row (never mentioning the other action as an option)
    # is the next attempt.
    if _instructs_typing(action_text):
        step_instruction = (
            "This step's instruction is to type text into a field. That field was already "
            "tapped and focused by the PREVIOUS step, and that focus is still active — do not "
            "call tap on it or on anything else. Call type() right now with the exact text from "
            "the instruction above."
        )
    else:
        step_instruction = (
            "Perform this step with the one matching action (tap or swipe) for it. Do not call "
            "type() for this step."
        )
    task = (
        f"Overall test scenario: {scenario}\n"
        + (f"Pre-conditions: {preconditions}\n" if preconditions else "")
        + f"\nCurrent step to perform: {action_text}\n\n"
        f"{step_instruction}\n\n"
        "When this specific step has been performed, call task_complete."
    )
    last_action = None
    actions_taken = 0

    # Verified real failure this targets: on a busier screen (the product
    # detail page, with many more distractor buttons than the sign-in form
    # ever had), the model repeatedly needed its FULL sub-action budget just
    # to stumble onto the right action (e.g. wasting attempts on "Decrease
    # quantity" / a redundant "Add to cart" before finally tapping "Increase
    # quantity") — and each time, that correct action landed on the loop's
    # LAST iteration. The old `for _ in range(max_sub_steps)` bound ties
    # "real actions allowed" and "decide-cycles allowed" together 1:1, so a
    # success on the final iteration was never followed by another decide
    # cycle to notice the step is done — it was reported as budget-exhausted
    # every time, even though the row's actual goal had just been met.
    # Decoupling them — allow one extra decide-only cycle after the last
    # real action, which may confirm completion (task_complete, or a repeat
    # the existing guard above already treats as completion) but may not
    # spend a fresh action — fixes this without loosening the budget itself.
    for _ in range(max_sub_steps + 1):
        try:
            state = _capture_with_loading_wait(step_counter, udid, state_dir)
        except PerceptionError as e:
            log("perception_failed", step=step_counter[0], error=str(e))
            return False, f"perception failed: {e}"
        n = step_counter[0]

        log("state_captured", step=n, screenshot=state["screenshot"], history_len=len(history),
            labels=[el["label"] for el in state["elements"]])

        try:
            action = decide_next_action(task, state["elements"], history)
        except ReasoningError as e:
            log("reasoning_failed", step=n, error=str(e))
            return False, f"reasoning failed: {e}"

        log("action_selected", step=n, action=action)

        if action["action"] == "task_complete":
            log("step_action_complete", step=n)
            return True, None

        # Deterministic guard: a bounded per-row sub-loop is meant to perform
        # one micro-action. If the model selects the same action it just
        # executed (by semantic signature, not raw dict equality — verified
        # real case: a repeat carried a spurious extra key that made a raw
        # comparison miss it), that's the model failing to recognize the step
        # is already done (verified directly: an explicit prompt instruction
        # to check history first did not fix this) rather than a legitimate
        # reason to repeat it — treat the row as complete instead of
        # re-executing (which risks hitting a since-changed/ambiguous label).
        if _action_signature(action) == _action_signature(last_action or {}):
            # Verified real failure: a row whose OWN instruction says to type
            # (e.g. 'Type "user1@xyz.com".') instead just repeated a tap on
            # the field twice and "completed" here having never called
            # type() — judge_step then false-PASSed it by misreading the
            # field's placeholder as entered content. This checks the row's
            # own instruction text, not history content, so it doesn't
            # revisit the rejected content-based repeat guard (which would
            # have broken a legitimate same-text-in-two-fields form) — it
            # only refuses to call a type-row "done" if a type() was never
            # even attempted.
            if action["action"] == "tap" and _instructs_typing(action_text):
                log("step_repeat_detected_but_never_typed", step=n, action=action)
                return False, (
                    f"step instructs typing ({action_text!r}) but the model only "
                    f"repeated tap({action.get('label')!r}) and never called "
                    "type() — refusing to report this as a false completion"
                )
            log("step_repeat_detected_as_complete", step=n, action=action)
            return True, None

        if actions_taken >= max_sub_steps:
            # The real-action budget is already spent — this cycle only
            # existed to give the model one last chance to say it's done
            # (task_complete or a repeat, both handled above). It picked a
            # new, different action instead, so it's still genuinely
            # flailing, not just one confirmation short — fail now rather
            # than execute yet another unbudgeted action.
            log("step_budget_exhausted_after_confirmation_check", step=n, action=action)
            return False, f"step budget ({max_sub_steps} sub-actions) exhausted without task_complete"

        try:
            result = execute(action, state["elements"], udid, last_tapped_type_ref[0])
        except ActionError as e:
            log("action_failed", step=n, action=action, error=str(e))
            return False, f"action failed: {e}"

        log("action_executed", step=n, action=action, result=result)
        history.append(_describe(action))
        last_action = action
        actions_taken += 1
        last_tapped_type_ref[0] = result.get("element_type") if action["action"] == "tap" else None
        last_tapped_label_ref[0] = result.get("resolved_label") if action["action"] == "tap" else None

    return False, f"step budget ({max_sub_steps} sub-actions) exhausted without task_complete"


# Words that make a quoted-label's mere PRESENCE insufficient evidence for
# an Expected Result claim, because perception (see perception.py) never
# captures element enabled/selected/checked state — only label/type/frame/
# value. A row like 'The "Continue to payment" button becomes enabled.' has
# that label present in the UI both before AND after the button is actually
# enabled, so a presence-only check would false-PASS it regardless of the
# real state. Verified against make_order_use_case.md: rows 6, 22, 24 and
# the postcondition ("...with 'Home' active...") all hit this guard and
# correctly defer to judge_step instead.
_STATE_QUALIFIER_KEYWORDS = {
    "disabled", "enabled", "selected", "unselected", "checked", "unchecked",
    "grayed", "greyed", "active", "inactive", "becomes", "highlighted",
}


def _asserts_state_change(text):
    lowered = text.lower()
    return any(kw in lowered for kw in _STATE_QUALIFIER_KEYWORDS)


def _deterministic_type_verdict(action_text, elements, target_field_label):
    """For a row whose action was Type "X": deterministic PASS only if the
    field the PREVIOUS row's tap focused (target_field_label, threaded in
    from main() via last_tapped_label_ref — a Type row's own action never
    resolves a label itself) now shows value == X exactly. Returns None
    (defer to judge_step) for a SecureTextField (masked password — its
    value can't be verified as real content either way; a weaker heuristic
    wouldn't add real confidence) or on any mismatch (the app may have
    reformatted the input — a false deterministic FAIL is worse than one
    extra LLM call, so this never fails, only confirms or defers)."""
    quoted = extract_quoted_strings(action_text)
    if len(quoted) != 1 or target_field_label is None:
        return None
    typed_text = quoted[0]
    try:
        element = resolve_label(target_field_label, elements)
    except ActionError:
        return None
    if element["type"] == "SecureTextField":
        return None
    if element.get("value") == typed_text:
        return {"passed": True,
                "reason": f"deterministic: {target_field_label!r} value exactly matches typed text {typed_text!r}"}
    return None


def _deterministic_label_presence_verdict(expected_text, elements):
    """Deterministic PASS only if EVERY quoted substring in the Expected
    Result text exact-resolves as a currently-present label, and the text
    doesn't assert a state change (_asserts_state_change). If some but not
    all quoted labels are present, still defers rather than failing —
    absence isn't proof of failure for compound/fuzzy expected-result
    prose (e.g. an "either X or Y" claim)."""
    quoted = extract_quoted_strings(expected_text)
    if not quoted or _asserts_state_change(expected_text):
        return None
    present = []
    for label in quoted:
        try:
            resolve_label(label, elements)
            present.append(label)
        except ActionError:
            return None
    return {"passed": True,
            "reason": f"deterministic: expected label(s) {present} all present in current UI"}


def _deterministic_verdict(action_text, expected_text, elements, target_field_label):
    """Tries the Type-value check first (when the row's action instructs
    typing), else the label-presence check. Returns None if neither
    applies — meaning: fall back to judge_step, completely unchanged.

    Verified real case this guards against: make_order row 22 ("Type
    'USA'.") has a COMPOUND Expected Result — "the text appears in the
    Country field" AND "...the 'Continue to payment' button becomes
    enabled." The type-value check alone only verifies the first clause;
    returning its PASS directly would silently skip ever verifying the
    second (state-change) clause at all, neither deterministically nor via
    judge_step — strictly less thorough than the LLM path it's replacing.
    Requiring _asserts_state_change to be false before trusting the
    type-value check alone ensures a compound claim like this always falls
    through to the label-presence check (which itself defers to judge_step
    for the same reason), preserving the original verification thoroughness
    for every row that has anything beyond a single plain value claim."""
    if _instructs_typing(action_text) and not _asserts_state_change(expected_text):
        verdict = _deterministic_type_verdict(action_text, elements, target_field_label)
        if verdict is not None:
            return verdict
    return _deterministic_label_presence_verdict(expected_text, elements)


def main():
    parser = argparse.ArgumentParser(description="Run a markdown test-case doc against a booted iOS Simulator native app.")
    parser.add_argument("--test-case", required=True, help="Path to the test-case markdown file")
    parser.add_argument("--udid", required=True)
    parser.add_argument("--steps-per-action", type=int, default=DEFAULT_STEPS_PER_ACTION,
                         help="Max sub-actions (taps/types) allowed per test-case row")
    parser.add_argument("--state-dir", help="Directory screenshots are written into (default: 'state' next to the test-case file)")
    parser.add_argument("--results-dir", help="Directory results files are written into (default: 'results' next to the test-case file)")
    parser.add_argument("--out", help="Output path for results (default: <results-dir>/<test-case-stem>_results.md)")
    args = parser.parse_args()

    try:
        tc = parse_test_case(args.test_case)
    except TestCaseError as e:
        sys.exit(f"FAILURE: could not parse test case: {e}")

    # Default state/ and results/ to live next to the test-case markdown file
    # itself, not wherever this script happens to be invoked from — keeps a
    # test case's own screenshots/results colocated with it instead of
    # scattered across whatever cwd different invocations used.
    test_case_dir = Path(args.test_case).resolve().parent
    if args.state_dir is None:
        args.state_dir = str(test_case_dir / "state")
    if args.results_dir is None:
        args.results_dir = str(test_case_dir / "results")

    preflight(args.udid)
    Path(args.state_dir).mkdir(parents=True, exist_ok=True)
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)

    log("test_case_start", scenario=tc["scenario"], priority=tc["priority"],
        step_count=len(tc["steps"]), model=REASONING_MODEL)

    # History is carried across rows as AT MOST ONE entry — the previous
    # row's final action — not the whole growing list, and not nothing.
    # Verified empirically, two full runs of this exact test case:
    #   - Full global history (unbounded, 6-item window): row 7's
    #     instruction ("Type 'user1'") was overridden by row 5's
    #     type("user1@xyz.com") still sitting in the window (2 rows back) —
    #     the model anchored on the older, formally-similar action.
    #   - Fully blank history per row: fixed that, but row 5 lost the "a
    #     field was just focused" continuity from row 4 and tapped Sign-in
    #     prematurely instead of typing directly — a new regression.
    #   - Carrying forward exactly the immediately-previous row's last
    #     action (this design): row 4->5 keeps its continuity (seed shows
    #     "just tapped Username"), while row 7 no longer sees row 5's action
    #     at all (it's 2 hops back, beyond the 1-item carry), removing the
    #     distractor. This is informational continuity, not a
    #     repeat-blocking check — it doesn't inspect history to refuse an
    #     action (a content-based guard was explicitly rejected: it would
    #     break a legitimate form requiring the same text in two fields).
    carry_over = []
    step_counter = [0]
    last_tapped_type_ref = [None]
    last_tapped_label_ref = [None]
    step_results = []
    blocked = False

    for step in tc["steps"]:
        if blocked:
            step_results.append({"passed": None, "reason": "not attempted — a prior step failed"})
            continue

        history = list(carry_over)
        # Snapshotted BEFORE run_step() runs this row: for a Type row, this
        # is the label the PREVIOUS row's tap focused (a Type row's own
        # action never resolves a label itself) — exactly what
        # _deterministic_type_verdict needs to check post-type value below.
        target_field_label = last_tapped_label_ref[0]
        log("test_step_start", step=step["step"], action=step["action"])
        ok, error = run_step(tc["scenario"], tc["preconditions"], step["action"], args.udid,
                              args.state_dir, step_counter, history, args.steps_per_action,
                              last_tapped_type_ref, last_tapped_label_ref)
        carry_over = history[-1:]

        if not ok:
            step_results.append({"passed": False, "reason": error})
            log("test_step_failed", step=step["step"], error=error)
            blocked = True
            continue

        try:
            # Verified real bug: this used to reuse step_counter[0] as-is,
            # so this verdict screenshot overwrote the last sub-action's
            # step_NNN.png every row, destroying the evidence of what the
            # action actually did. Incrementing first gives it its own frame.
            step_counter[0] += 1
            state = capture_state(step_counter[0], args.udid, args.state_dir)
            verdict = _deterministic_verdict(step["action"], step["expected"], state["elements"],
                                              target_field_label)
            if verdict is not None:
                log("deterministic_verdict_used", step=step["step"], verdict=verdict)
            else:
                log("deterministic_verdict_not_applicable", step=step["step"])
                verdict = judge_step(step["expected"], state["elements"])
                log("llm_verdict_used", step=step["step"], verdict=verdict)
        except (PerceptionError, ReasoningError) as e:
            verdict = {"passed": False, "reason": f"could not verify: {e}"}

        step_results.append(verdict)
        log("test_step_verdict", step=step["step"], verdict=verdict)

    postcondition_result = None
    if tc["postconditions"] and not blocked:
        try:
            step_counter[0] += 1  # own frame, not a reused/overwritten one — see the step-verdict capture above
            state = capture_state(step_counter[0], args.udid, args.state_dir)
            combined = " ".join(tc["postconditions"])
            postcondition_result = _deterministic_verdict("", combined, state["elements"], None)
            if postcondition_result is not None:
                log("deterministic_verdict_used", step="postconditions", verdict=postcondition_result)
            else:
                log("deterministic_verdict_not_applicable", step="postconditions")
                postcondition_result = judge_step(combined, state["elements"])
                log("llm_verdict_used", step="postconditions", verdict=postcondition_result)
        except (PerceptionError, ReasoningError) as e:
            postcondition_result = {"passed": False, "reason": f"could not verify: {e}"}
    elif tc["postconditions"]:
        postcondition_result = {"passed": None, "reason": "not attempted — a prior step failed"}

    out_path = args.out or str(Path(args.results_dir) / (Path(args.test_case).stem + "_results.md"))
    write_results(tc, step_results, postcondition_result, out_path)

    passed = sum(1 for r in step_results if r["passed"] is True)
    failed = sum(1 for r in step_results if r["passed"] is False)
    blocked_n = sum(1 for r in step_results if r["passed"] is None)
    log("test_case_complete", passed=passed, failed=failed, blocked=blocked_n, out=out_path)
    print(f"\nResults written to {out_path}")
    print(f"{passed} passed, {failed} failed, {blocked_n} blocked")
    print("NOTE: verdicts are the local model's best-effort self-assessment against prose — "
          "not an authoritative check. Review the screenshots in the state dir before trusting a PASS.")

    sys.exit(0 if failed == 0 and blocked_n == 0 else 1)


if __name__ == "__main__":
    main()
