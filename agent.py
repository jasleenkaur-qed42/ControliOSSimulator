"""Agent control loop wiring perception -> reasoning -> action.

    for step in range(max_steps):
        state = capture_state(step)
        action = decide_next_action(task, state.elements, history)
        if action == task_complete: stop successfully
        execute(action, state.elements)
        history.append(action)
    else:
        stop with failure (max steps reached)

Everything is local: the simulator, idb, and Ollama all run on this machine.
Scope: native UIKit/SwiftUI app screens only, via idb. Safari/web content was
explored and dropped — see README notes / conversation history for why
(idb's real touches conflict with any attached WebDriver-style automation
session on Safari, and no verified alternative reached real, trusted clicks).
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from perception import capture_state, PerceptionError
from reasoning import decide_next_action, ReasoningError, MODEL as REASONING_MODEL, OLLAMA_URL
from actions import execute, ActionError

DEFAULT_MAX_STEPS = 15


def log(event, **fields):
    record = {"ts": time.strftime("%H:%M:%S"), "event": event, **fields}
    # flush=True verified necessary: stdout fully buffers (rather than
    # line-buffers) when redirected to a file/pipe instead of a terminal, so
    # a run's progress was invisible in its output file until the whole
    # process exited — a long run looked identical to a hung one.
    print(json.dumps(record, default=str), flush=True)


def preflight(udid):
    """Verify every external dependency explicitly. Exits with a clear
    message on the first failure — no silent fallback, no retries."""

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL.rsplit('/api', 1)[0]}/api/version", timeout=5) as resp:
            json.loads(resp.read())
    except urllib.error.URLError:
        sys.exit(
            "FAILURE: Ollama is not reachable at localhost:11434.\n"
            "Start it with: brew services start ollama   (or: ollama serve)"
        )

    list_result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if REASONING_MODEL not in list_result.stdout:
        sys.exit(
            f"FAILURE: model '{REASONING_MODEL}' is not installed in Ollama.\n"
            f"Install it with: ollama pull {REASONING_MODEL}"
        )

    booted = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"], capture_output=True, text=True)
    if udid not in booted.stdout:
        sys.exit(
            f"FAILURE: no booted simulator with udid {udid} found.\n"
            "Boot one with: xcrun simctl boot <udid>  (see `xcrun simctl list devices` for options)"
        )

    targets = subprocess.run(["idb", "list-targets"], capture_output=True, text=True)
    target_line = next((line for line in targets.stdout.splitlines() if udid in line), None)
    if target_line is None or "No Companion Connected" in target_line:
        sys.exit(
            f"FAILURE: idb has no companion connected for {udid}.\n"
            "Start one and connect:\n"
            f"  idb_companion --udid {udid} --grpc-port 10882 &\n"
            "  idb connect localhost 10882"
        )


def run(task, udid, max_steps, state_dir):
    log("agent_start", task=task, udid=udid, max_steps=max_steps, model=REASONING_MODEL)
    history = []
    last_tapped_type = None

    for step in range(1, max_steps + 1):
        try:
            state = capture_state(step, udid, state_dir)
        except PerceptionError as e:
            log("perception_failed", step=step, error=str(e))
            sys.exit(f"FAILURE: perception step failed: {e}")

        log("state_captured", step=step, screenshot=state["screenshot"],
            element_count=len(state["elements"]),
            labels=[el["label"] for el in state["elements"]])

        try:
            action = decide_next_action(task, state["elements"], history)
        except ReasoningError as e:
            log("reasoning_failed", step=step, error=str(e))
            sys.exit(f"FAILURE: reasoning step failed: {e}")

        log("action_selected", step=step, action=action)

        if action["action"] == "task_complete":
            log("task_complete", step=step)
            print(f"SUCCESS: task completed after {step} step(s).")
            return 0

        try:
            result = execute(action, state["elements"], udid, last_tapped_type)
        except ActionError as e:
            log("action_failed", step=step, action=action, error=str(e))
            sys.exit(f"FAILURE: action execution failed: {e}")

        log("action_executed", step=step, action=action, result=result)
        history.append(_describe(action))
        last_tapped_type = result.get("element_type") if action["action"] == "tap" else None

    log("max_steps_reached", max_steps=max_steps)
    print(f"FAILURE: maximum step count ({max_steps}) reached without task_complete.")
    return 1


def _describe(action):
    kind = action["action"]
    if kind == "tap":
        return f'tap("{action.get("label")}")'
    if kind == "swipe":
        return f'swipe(({action.get("from_x")},{action.get("from_y")}) -> ({action.get("to_x")},{action.get("to_y")}))'
    if kind == "type":
        return f'type("{action.get("text")}")'
    return kind


def main():
    parser = argparse.ArgumentParser(description="Local LLM agent that drives native iOS Simulator apps via Ollama + idb.")
    parser.add_argument("--task", required=True, help="Plain-language task, e.g. 'Tap the About button'")
    parser.add_argument("--udid", required=True, help="Booted simulator UDID (see: xcrun simctl list devices booted)")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--state-dir", default="state")
    args = parser.parse_args()

    preflight(args.udid)
    Path(args.state_dir).mkdir(parents=True, exist_ok=True)
    exit_code = run(args.task, args.udid, args.max_steps, args.state_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
