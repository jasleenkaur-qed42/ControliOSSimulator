"""Action layer: deterministically converts one structured action into an
actual `idb ui` command against the booted simulator.

Commands verified directly against a booted simulator:
  idb ui tap --udid <udid> <x> <y>            (integer coordinates only — floats are rejected by idb)
  idb ui swipe --udid <udid> <x1> <y1> <x2> <y2>
  idb ui text --udid <udid> "<text>"

The model never supplies raw coordinates for a labeled tap: it names a label,
and this layer resolves that label to a frame from the current accessibility
tree, then computes the center deterministically.

`idb ui text` sends keystrokes to whatever currently has OS keyboard focus —
it has no concept of a target. Observed failure mode: the model called
type("Sign in") instead of tap("Sign in") on a button, several times in a
row; idb reported success each time (it always succeeds — text went
wherever focus happened to be, or nowhere), and the run then falsely
reported overall SUCCESS. `execute()` now requires the caller to report
which element type was last successfully tapped, and refuses `type` unless
that was a genuine text-entry element — command success is not proof
anything meaningful happened.
"""
import json
import subprocess

from perception import wait_for_stable_ui

TEXT_ENTRY_TYPES = {"TextField", "SecureTextField", "TextView", "SearchField"}

# Verified real bug: a single `idb ui text` call with a longer string (e.g.
# "user1@xyz.com") corrupted the result into 'user1user1user1@xyz.com' —
# idb sending keystrokes faster than this React Native TextInput's
# controlled-component re-render cycle could keep up caused the leading
# chars to be replayed. Splitting into small chunks with a short pause
# between each, verified directly, fixes it (confirmed with plain
# fixed-size slicing, not just at word/symbol boundaries).
#
# Chunk size 4 was NOT enough on its own, though: verified directly against
# a real run, "user1@xyz.com" landed as "user12xyz.com" — the '@' silently
# substituted for '2' — with the chunk boundary nowhere near '@' (it fell
# mid-chunk, in "1@xy"). Manual isolated retests of the same 4-char chunk
# were inconsistent — sometimes correct, sometimes lost characters entirely
# — pointing to the same underlying re-render race as the duplication bug
# above, just surfacing as corruption instead of duplication, and timing-
# sensitive rather than tied to '@' specifically. Sending one character at
# a time, with a settle delay after each, reduced but did not eliminate the
# corruption — it's still reproduced intermittently on strings like
# "user1@xyz.com" even with a flat per-character delay.
#
# User-supplied insight: the iOS keyboard isn't one static layout — it has
# separate pages for letters, numbers/symbols, and emoji, and typing a
# character from a different page than the previous one requires the
# on-screen keyboard to actually switch pages first. A flat delay applied
# equally to every keystroke is too short for a page-switching transition
# (still racing the layout change) while being needlessly long for a run of
# same-page characters. Classifying each character (alpha / digit / symbol,
# where "symbol" covers everything off the default letter page — '@', '.',
# space, emoji, etc.) and only paying the longer delay AT a class boundary
# — not on every keystroke — targets the actual mechanism instead of
# guessing a single duration for all cases.
#
# These aren't blind sleep durations, though — they're MAX-WAIT ceilings
# passed to wait_for_stable_ui, which polls the live accessibility tree and
# returns as soon as two consecutive snapshots match (usually much faster
# than the ceiling) rather than always sleeping the full guessed duration.
# A same-class keystroke gets a short ceiling since no real transition is
# expected; a class-switching keystroke gets a longer one to allow for a
# genuine page switch, but still returns immediately once things settle.
TYPE_SAME_CLASS_MAX_WAIT = 0.3
TYPE_CLASS_SWITCH_MAX_WAIT = 1.2


def _char_class(ch):
    """Which keyboard page a character lives on, for deciding whether
    consecutive characters need a page-switch delay between them."""
    if ch.isalpha():
        return "alpha"
    if ch.isdigit():
        return "digit"
    return "symbol"  # punctuation, '@', space, emoji, etc. — off the default letter page


# Verified real, 100%-reproducible bug (not a timing race — confirmed by
# testing with delays up to 0.8s and by testing `idb ui key <shift-2-code>
# --shift` directly): '@' consistently lands as '2' regardless of delay.
# idb's shift modifier is not reliably honored for these characters, so no
# amount of pacing fixes it — sending a shifted symbol via `idb ui text` (or
# `idb ui key --shift`) is fundamentally unreliable for this class of
# character. Verified fix: the on-screen keyboard for an email-type field
# already exposes '@' (and '.') as their own directly-tappable Button
# elements on the default page — tapping that key's frame bypasses the
# broken shift-modifier path entirely instead of trying to inject the
# character as a keystroke.
_SHIFTED_SYMBOLS = set('!@#$%^&*()_+{}|:"<>?~')

# Verified real bug: tapping a product card navigated correctly, but the
# next screen ("Product" detail) fetches its content asynchronously and
# shows a transient "Loading..." placeholder first. The very next
# perception snapshot landed during that window, so the model's next tap
# (on a heading it correctly anticipated would appear) failed outright —
# the label genuinely did not exist yet, not a reasoning mistake. Waiting
# for the accessibility tree to stabilize after every successful tap
# (wait_for_stable_ui) gives async content a chance to render before the
# caller's next capture — adaptively, not a fixed guessed duration: a
# simple screen settles almost immediately, a slow one gets up to the full
# ceiling below rather than a flat guess that isn't always enough.
TAP_SETTLE_MAX_WAIT = 3.0

# Verified real cases this disambiguates: (1) a screen had three elements
# labeled exactly "Sign in" — a nav-bar heading, a form heading, and the
# actual submit button — only the button is meaningfully tappable; (2) a
# text field's own on-screen label ("Username or email") and the input
# itself share that exact label — only the TextField is meaningfully
# tappable. Restricting ambiguous matches to actually-tappable types
# resolves both without guessing between genuinely distinct elements (still
# ambiguous if more than one tappable-type match remains).
TAPPABLE_TYPES = {"Button"} | TEXT_ENTRY_TYPES


class ActionError(Exception):
    pass


def _run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ActionError(f"Command timed out: {' '.join(cmd)} ({e})")
    except FileNotFoundError as e:
        raise ActionError(f"Command not found: {cmd[0]} ({e})")


def _label_starts_with(label, prefix):
    """True if `label` begins with `prefix` at a real word boundary — the
    next character (if any) isn't a continuing letter. Verified real case:
    a checkout button's accessible label includes a dynamic price ("Pay
    ₹298") that changes with the cart total, so a test case can't hardcode
    it in advance; naming just the static prefix ("Pay") should resolve to
    whatever price is actually showing. A boundary check is required,
    though — a bare .startswith("Pay") would also match "Payment method"
    and "Payment details", both genuinely present alongside it on the same
    screen, which would make this MORE ambiguous instead of solving
    anything."""
    if not label.startswith(prefix):
        return False
    rest = label[len(prefix):]
    return rest == "" or not rest[0].isalpha()


def resolve_label(label, elements):
    matches = [el for el in elements if el["label"] == label]
    if not matches:
        # Fallback only — never engages when an exact match exists, so
        # every already-verified exact-label row is completely unaffected.
        matches = [el for el in elements if _label_starts_with(el["label"], label)]
    if len(matches) == 0:
        available = ", ".join(repr(el["label"]) for el in elements)
        raise ActionError(
            f"Requested label {label!r} does not exist in the current UI. Available labels: {available}"
        )
    if len(matches) > 1:
        tappable = [el for el in matches if el["type"] in TAPPABLE_TYPES]
        if len(tappable) == 1:
            return tappable[0]
        types = ", ".join(f"{el['type']}" for el in matches)
        raise ActionError(
            f"Label {label!r} matches {len(matches)} elements (types: {types}) — "
            "still ambiguous after preferring tappable types, refusing to guess which one."
        )
    return matches[0]


def _center(frame):
    return round(frame["x"] + frame["width"] / 2), round(frame["y"] + frame["height"] / 2)


# Verified real limitation: `idb ui describe-all` (the full-tree walk
# `elements` comes from) reports an entire native iOS navigation bar as a
# single opaque Group with no AXLabel, not decomposed into its
# back/title/right-bar-button children — even when a child genuinely has
# an accessibilityLabel set in the app's own source. `_compact_elements`
# drops that Group entirely (no label), so it never reaches `resolve_label`
# at all. Verified real case: an "Order details" screen's headerLeft back
# button has accessibilityLabel="Back", renders visibly on screen, but
# never appears in `elements`. `idb ui describe-point` (hit-testing one
# screen coordinate) sees through the same native chrome and correctly
# returns that button, labeled "Back". This probes a short list of
# candidate points along the nav bar's row — never a single blind guess —
# and only ever returns a match whose live-queried label actually matches
# what was requested, same "verify before tap" principle as resolve_label,
# just a second lookup strategy for controls hidden inside native chrome.
_NAV_BAR_FALLBACK_CY = 76  # observed nav-bar vertical center, consistent across every screen this app renders
_NAV_BAR_PROBE_X_CANDIDATES = [20, 40, 60, 330, 350]


def _probe_native_header(label, elements, udid):
    gear = next((el for el in elements if el["label"] == "gearshape.fill"), None)
    cy = gear["frame"]["y"] + gear["frame"]["height"] // 2 if gear else _NAV_BAR_FALLBACK_CY
    for cx in _NAV_BAR_PROBE_X_CANDIDATES:
        result = _run(["idb", "ui", "describe-point", "--udid", udid, str(cx), str(cy), "--json"])
        if result.returncode != 0:
            continue
        try:
            el = json.loads(result.stdout)
        except (ValueError, TypeError):
            continue
        found_label = el.get("AXLabel")
        frame = el.get("frame")
        if not found_label or not frame:
            continue
        if found_label == label or _label_starts_with(found_label, label):
            try:
                compact_frame = {
                    "x": round(frame["x"]),
                    "y": round(frame["y"]),
                    "width": round(frame["width"]),
                    "height": round(frame["height"]),
                }
            except (KeyError, TypeError):
                continue
            return {"label": found_label, "type": el.get("type") or "Unknown", "frame": compact_frame}
    return None


def execute(action, elements, udid, last_tapped_type=None):
    """action is the dict returned by reasoning.decide_next_action.
    Raises ActionError explicitly on any failure; never taps a fallback coordinate.

    last_tapped_type: the accessibility `type` of the element the previous
    successful tap resolved to (None if the last action wasn't a tap), used
    to gate `type` — see module docstring.
    """
    kind = action.get("action")

    if kind == "tap":
        label = action.get("label")
        if not label:
            raise ActionError("tap action missing required 'label' argument")
        try:
            element = resolve_label(label, elements)
        except ActionError:
            element = _probe_native_header(label, elements, udid)
            if element is None:
                raise
        x, y = _center(element["frame"])
        result = _run(["idb", "ui", "tap", "--udid", udid, str(x), str(y)])
        if result.returncode != 0:
            raise ActionError(f"tap({label!r}) -> idb failed: {result.stderr.strip()}")
        wait_for_stable_ui(udid, max_wait=TAP_SETTLE_MAX_WAIT)
        return {"resolved_label": element["label"], "coordinates": [x, y], "element_type": element["type"]}

    if kind == "swipe":
        required = ("from_x", "from_y", "to_x", "to_y")
        missing = [k for k in required if k not in action]
        if missing:
            raise ActionError(f"swipe action missing required argument(s): {missing}")
        try:
            x1, y1, x2, y2 = (round(float(action[k])) for k in required)
        except (TypeError, ValueError):
            raise ActionError(f"swipe action has non-numeric argument(s): {action}")
        result = _run(["idb", "ui", "swipe", "--udid", udid, str(x1), str(y1), str(x2), str(y2)])
        if result.returncode != 0:
            raise ActionError(f"swipe(({x1},{y1})->({x2},{y2})) -> idb failed: {result.stderr.strip()}")
        return {"from": [x1, y1], "to": [x2, y2]}

    if kind == "type":
        text = action.get("text")
        if not text:
            raise ActionError("type action missing required 'text' argument")
        if last_tapped_type not in TEXT_ENTRY_TYPES:
            raise ActionError(
                f"type({text!r}) refused: the last tap was not on a text-entry element "
                f"(was {last_tapped_type!r}). idb ui text sends keystrokes to whatever has "
                "focus, which is meaningless here — tap the actual text field first."
            )
        for i, ch in enumerate(text):
            key = None
            if ch in _SHIFTED_SYMBOLS:
                key = next((el for el in elements if el.get("label") == ch and el.get("type") == "Button"), None)
            if key is not None:
                x, y = _center(key["frame"])
                result = _run(["idb", "ui", "tap", "--udid", udid, str(x), str(y)])
                if result.returncode != 0:
                    raise ActionError(f"type({text!r}) -> idb failed tapping on-screen key "
                                       f"{ch!r} (index {i}): {result.stderr.strip()}")
            else:
                result = _run(["idb", "ui", "text", "--udid", udid, ch])
                if result.returncode != 0:
                    raise ActionError(f"type({text!r}) -> idb failed on char {ch!r} (index {i}): {result.stderr.strip()}")
            if i + 1 < len(text):
                switching_page = _char_class(text[i + 1]) != _char_class(ch)
                max_wait = TYPE_CLASS_SWITCH_MAX_WAIT if switching_page else TYPE_SAME_CLASS_MAX_WAIT
                elements = wait_for_stable_ui(udid, max_wait=max_wait)
        return {"text": text}

    raise ActionError(f"Unsupported or invalid action: {action!r}")
