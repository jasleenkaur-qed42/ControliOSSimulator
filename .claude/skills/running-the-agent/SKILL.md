---
name: running-the-agent
description: Use when asked to run agent.py or run_test_case.py against the iOS Simulator, when a run exits at preflight with a FAILURE message, or when you need to find a booted simulator's UDID, start idb_companion, or check the Ollama model is installed for this project.
---

# Running the agent

## Setup, in order (each step is what `agent.preflight` checks and errors on)

```bash
brew services start ollama            # or: ollama serve
ollama pull llama3.2:3b                # must match reasoning.MODEL exactly
xcrun simctl list devices booted       # get the UDID of a booted simulator
                                        # (xcrun simctl boot <udid> if none is booted)
idb_companion --udid <UDID> --grpc-port 10882 &
idb connect localhost 10882
```

`preflight()` in `agent.py` checks all four in order and exits with the exact remediation command on the first failure — if a run fails immediately, read that message rather than guessing.

## Running

Always use the venv's Python — `fb-idb` is only installed there:

```bash
.venv/bin/python agent.py --task 'Tap the About button' --udid <UDID>
.venv/bin/python run_test_case.py --test-case path/to/case.md --udid <UDID>
```

`run_test_case.py` defaults `state/` and `results/` to live next to the test-case file, not the cwd — pass `--state-dir`/`--results-dir` to override.

## After a run

- Stdout is JSON-lines, one event per line (`state_captured`, `action_selected`, `action_executed`, `test_step_verdict`, ...). Use `run-log-analyzer` (an agent) to diagnose a specific failure or a suspicious verdict from this output.
- Screenshots: `<state-dir>/step_NNN.png`, one per perception snapshot (not one per test-case row — a row can take several).
- For `run_test_case.py`: results are written to `<results-dir>/<stem>_results.md` (never overwrites the source test case), plus a console line `N passed, M failed, K blocked`.
- Any PASS/FAIL from `judge_step` (logged as `llm_verdict_used`) is the local model self-grading against prose, not authoritative — spot-check the actual screenshot before trusting it, especially anything marked BLOCKED (means an earlier row failed and everything after was skipped, not attempted).
