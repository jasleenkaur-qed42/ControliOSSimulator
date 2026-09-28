"""Perception layer: captures a screenshot and a compact accessibility tree
from a booted iOS Simulator.

Commands used here were verified directly against a booted simulator:
  xcrun simctl io <udid> screenshot <path>
  idb ui describe-all --udid <udid> --json

The raw `idb ui describe-all` output is a JSON array of elements shaped like:
  {"AXLabel": "About", "type": "Button", "frame": {"x":16,"y":220,"width":361,"height":52}, ...}
This module trims that down to {"label", "type", "frame", "value"} for
elements that carry a non-empty AXLabel, and drops everything else the model
doesn't need.

`value` (from AXValue) was added after a verified real failure: a test-case
verdict step marked PASS for "the email text appears in the field" when the
wrong text had actually been typed there — the reasoning layer had no way to
check field content at all, since it was never captured. Note verified
directly: an empty text field's AXValue is its placeholder text (e.g.
'username@example.com'), not null/empty — callers comparing `value` against
expected content must account for that, not treat any non-empty value as
"something was entered".
"""
import json
import subprocess
import time
from pathlib import Path


class PerceptionError(Exception):
    pass


def _run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise PerceptionError(f"Command timed out: {' '.join(cmd)} ({e})")
    except FileNotFoundError as e:
        raise PerceptionError(f"Command not found: {cmd[0]} ({e})")


def capture_screenshot(udid, out_path):
    result = _run(["xcrun", "simctl", "io", udid, "screenshot", str(out_path)])
    if result.returncode != 0:
        raise PerceptionError(
            f"Screenshot capture failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
        raise PerceptionError(f"Screenshot command reported success but no file was written at {out_path}")
    return str(out_path)


def capture_accessibility_tree(udid):
    result = _run(["idb", "ui", "describe-all", "--udid", udid, "--json"], timeout=30)
    if result.returncode != 0:
        raise PerceptionError(
            "idb ui describe-all failed "
            f"(exit {result.returncode}): {result.stderr.strip()}\n"
            "Is idb_companion running and connected to this simulator? "
            "(idb_companion --udid <udid> --grpc-port 10882, then idb connect localhost 10882)"
        )
    try:
        tree = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise PerceptionError(f"idb ui describe-all returned invalid JSON: {e}")

    if not tree:
        raise PerceptionError("Accessibility tree is empty — no elements returned for the current screen.")
    return tree


def _compact_elements(raw_tree):
    elements = []
    for el in raw_tree:
        label = el.get("AXLabel")
        if not label or not str(label).strip():
            continue
        frame = el.get("frame") or {}
        try:
            compact_frame = {
                "x": round(frame["x"]),
                "y": round(frame["y"]),
                "width": round(frame["width"]),
                "height": round(frame["height"]),
            }
        except (KeyError, TypeError):
            continue
        compact = {
            "label": str(label),
            "type": el.get("type") or el.get("role") or "Unknown",
            "frame": compact_frame,
        }
        value = el.get("AXValue")
        if value is not None and str(value).strip():
            compact["value"] = str(value)
        elements.append(compact)
    return elements


def capture_elements(udid):
    """Like capture_state but skips the screenshot — just the compact
    accessibility tree. Used for fast, repeated polling (e.g. waiting for
    the UI to stabilize after an action) where a screenshot would only add
    cost without being needed."""
    return _compact_elements(capture_accessibility_tree(udid))


def _elements_signature(elements):
    """Comparable snapshot of an elements list for stability polling —
    label, type, and value only. `frame` is deliberately excluded: a frame
    can jitter by sub-pixel rounding between two really-identical renders,
    which would make the poll never see two consecutive identical
    snapshots and always fall through to the max-wait ceiling instead of
    returning early."""
    return tuple(sorted((el["label"], el["type"], el.get("value")) for el in elements))


def wait_for_stable_ui(udid, max_wait=3.0, poll_interval=0.15, stable_polls=2):
    """Polls the accessibility tree (no screenshot — cheap) until
    `stable_polls` consecutive snapshots come back identical, or `max_wait`
    seconds have passed, whichever is first. Replaces a blind fixed sleep
    after an action: returns as soon as the UI has genuinely settled (often
    much faster than a worst-case guess) and keeps waiting, up to
    `max_wait`, if it's still actively changing (more correct under real
    memory-pressure load than a fixed duration that isn't always enough).
    Never raises for "still not stable by max_wait" — just returns
    whatever the last poll saw, the same "settle for what you've got after
    a bounded wait" behavior the fixed-delay code it replaces already had.
    Returns the final elements list, so callers get a fresh snapshot for
    free instead of needing a separate capture afterward."""
    start = time.monotonic()
    elements = capture_elements(udid)
    last_sig = _elements_signature(elements)
    stable_count = 1
    while stable_count < stable_polls:
        if time.monotonic() - start >= max_wait:
            break
        time.sleep(poll_interval)
        elements = capture_elements(udid)
        sig = _elements_signature(elements)
        stable_count = stable_count + 1 if sig == last_sig else 1
        last_sig = sig
    return elements


def capture_state(step, udid, state_dir):
    """Captures screenshot + accessibility tree, returns
    {"step": step, "screenshot": path, "elements": [...]}.
    Raises PerceptionError explicitly — never fabricates a fallback state.
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = state_dir / f"step_{step:03d}.png"

    capture_screenshot(udid, screenshot_path)
    raw_tree = capture_accessibility_tree(udid)
    elements = _compact_elements(raw_tree)

    if not elements:
        raise PerceptionError(
            "Accessibility tree contains no usable labeled/interactable elements. "
            f"Raw tree had {len(raw_tree)} node(s), none with a usable AXLabel."
        )

    return {"step": step, "screenshot": str(screenshot_path), "elements": elements}
