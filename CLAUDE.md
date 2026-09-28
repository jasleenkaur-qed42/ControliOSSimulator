# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local LLM agent that drives native iOS Simulator apps. A plain-language task (or a markdown
test-case doc) is executed as a loop of: capture the simulator's accessibility tree → ask a local
Ollama model for exactly one structured action → deterministically translate that action into an
`idb ui` command.

Everything runs on this machine: the simulator, `idb`/`idb_companion`, and Ollama. There is no
network service and no cloud model.

**Scope is native UIKit/SwiftUI screens only.** Safari/web content was explored and dropped: `idb`'s
real touches conflict with any attached WebDriver-style automation session on Safari.

## Commands

Run the venv's Python (`fb-idb` is installed there, not globally):

```bash
# One-off task
.venv/bin/python agent.py --task 'Tap the About button' --udid <UDID> [--max-steps 15] [--state-dir state]

# Run a markdown test-case doc end to end
.venv/bin/python run_test_case.py --test-case path/to/case.md --udid <UDID> [--steps-per-action 4]
```

`run_test_case.py` defaults `state/` and `results/` to directories next to the **test-case markdown
file**, not the cwd. Results are written to `<results-dir>/<stem>_results.md`; the source test case is
never overwritten.

There is no test suite, linter, build step, or dependency manifest in this repo.

### Environment the agent requires (checked by `agent.preflight`, shared by both entry points)

```bash
brew services start ollama            # or: ollama serve
ollama pull llama3.2:3b               # reasoning.MODEL
xcrun simctl list devices             # find/boot a simulator, get its UDID
idb_companion --udid <UDID> --grpc-port 10882 &
idb connect localhost 10882
```

Preflight exits with an explicit remediation message on the first missing dependency — never a silent
fallback.

## Architecture

Four layers, imported in one direction: `perception → reasoning → actions`, wired by `agent.py`.
`run_test_case.py` reuses all four plus `test_case.py`.

- **`perception.py`** — `capture_state()` returns a screenshot path plus a compact element list
  (`label`, `type`, `frame`, and `value` when non-empty) built from `idb ui describe-all`. Everything
  without an `AXLabel` is dropped. `wait_for_stable_ui()` polls the tree (no screenshot) until two
  consecutive snapshots match or a max-wait ceiling is hit — used instead of fixed sleeps everywhere.
- **`reasoning.py`** — one Ollama `/api/chat` call per decision with a `tools` array; the answer must
  arrive as a structured `tool_calls` entry. Actions are `tap`/`swipe`/`type`/`task_complete`.
  `judge_step()` is a separate call using a `step_verdict` tool. No natural-language parsing anywhere,
  with one narrow, explicitly-enabled exception (`_try_recover_tool_call`, judge-only).
- **`actions.py`** — the only module that issues `idb ui` commands. The model never supplies
  coordinates for a tap: it names a label, `resolve_label()` finds it in the current tree, and the
  center is computed here.
- **`test_case.py`** — parses one specific markdown format (an "Attribute | Details" table, a
  Step/Action/Expected Result/Status table, a "Post-conditions" bullet list) and writes results back
  into a copy of that structure. Deliberately narrow — it fails explicitly rather than guessing at
  markdown tables in general.
- **`run_test_case.py`** — per test-case row, tries a zero-LLM deterministic fast path first, falls
  through to the same agentic loop as `agent.py` bounded to `--steps-per-action`, then produces a
  verdict (deterministic where possible, else `judge_step`). A failed row marks every remaining row
  BLOCKED.

## Invariants to preserve

These encode failure modes that were hit and fixed for real. Read the module docstrings and inline
comments before changing any of them — they document what was already tried and why it didn't work.

- **Never fabricate a fallback.** Every layer raises its own explicit error type (`PerceptionError`,
  `ReasoningError`, `ActionError`, `TestCaseError`) and both entry points exit on it. No retries, no
  guessed coordinate, no invented state.
- **Command success is not proof anything happened.** `idb ui text` sends keystrokes to whatever has
  OS focus and always reports success. `execute()` therefore refuses `type` unless the caller reports
  that the last successful tap resolved to a text-entry type — this is what `last_tapped_type` is
  threaded through the loops for.
- **An empty text field's `AXValue` is its placeholder text**, not empty. Any check comparing `value`
  against expected content must account for that; treating a non-empty value as "something was
  entered" false-PASSes.
- **`judge_step` verdicts are the local model self-grading against prose, not authoritative.** It has
  been observed returning `passed=True` with a reason stating the opposite. Both the output file and
  the console summary say so; keep that caveat wherever verdicts are surfaced.
- **`idb` cannot type shifted symbols** (`@`, `#`, …) — `@` lands as `2` regardless of delay, and
  `idb ui key --shift` is equally unreliable. `actions.py` taps those characters' on-screen keyboard
  Buttons instead. Text is also sent one character at a time, with a longer settle ceiling only at a
  keyboard-page boundary (alpha/digit/symbol), because bulk sends race the app's re-render.
- **Native nav bars collapse into one unlabeled Group** in `describe-all`, so a back button with a
  real `accessibilityLabel` never reaches `elements`. `_probe_native_header()` hit-tests candidate
  points with `idb ui describe-point` and only returns a match whose live-queried label actually
  matches what was asked for.
- **History carried between test-case rows is exactly one entry** — the previous row's final action.
  Both alternatives were tried and each caused a distinct regression (see the comment in
  `run_test_case.main`).
- **Deterministic paths only ever confirm or defer, never fail.** `_deterministic_verdict` and its
  helpers return `None` to fall back to `judge_step` on any mismatch, on masked `SecureTextField`
  values, or when the expected text asserts a state change (enabled/selected/…) that perception never
  captures.
