"""Reasoning layer: sends task + UI state + history to a local Ollama model
and returns exactly one structured action.

Verified against a live Ollama instance running llama3.2:1b (see README / chat
transcript for the verification commands): the /api/chat endpoint with a
`tools` array reliably returns a `tool_calls` entry with a name and a JSON
`arguments` object. No natural-language parsing is used anywhere here.
"""
import json
import re
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2:3b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tap",
            "description": "Tap a UI element identified by its exact accessibility label. Use this for buttons, links, tabs, and any element with type Button/StaticText/Heading/Image — including elements labeled like 'Sign in', 'Submit', or similar. Tap the field first before typing into it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Exact label of the element to tap, copied verbatim from the current UI elements list."}
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swipe",
            "description": "Swipe from one point to another on screen, e.g. to scroll.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_x": {"type": "integer"},
                    "from_y": {"type": "integer"},
                    "to_x": {"type": "integer"},
                    "to_y": {"type": "integer"},
                },
                "required": ["from_x", "from_y", "to_x", "to_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type text into whichever text field is CURRENTLY focused/editable (type: TextField/SecureTextField/TextView/SearchField). The field does not need to have just been tapped in this same turn — if a previous step already tapped and focused it, that focus is still active, so call type() directly now instead of tapping that field again. Never use this to 'press' a button or link, even if its label looks like text you'd type; use tap for that instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Call this when the task has been fully accomplished and no further actions are needed.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


STEP_VERDICT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "step_verdict",
            "description": "Report whether the expected result actually happened, based only on the current UI elements listed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean", "description": "true only if the current UI elements show clear evidence the expected result happened"},
                    "reason": {"type": "string", "description": "One short sentence citing specific current UI elements that support this verdict"},
                },
                "required": ["passed", "reason"],
            },
        },
    }
]


class ReasoningError(Exception):
    pass


def _format_elements(elements):
    if not elements:
        return "(no labeled/interactable elements visible)"
    lines = []
    for el in elements:
        value = el.get("value")
        suffix = f", value: {value!r}" if value is not None else ""
        lines.append(f"- {el['label']!r} (type: {el['type']}{suffix})")
    return "\n".join(lines)


def _format_history(history, max_items=6):
    if not history:
        return "(none yet)"
    recent = history[-max_items:]
    lines = [f"{i + 1}. {h}" for i, h in enumerate(recent)]
    return "\n".join(lines)


def build_prompt(task, elements, history):
    return (
        f"Task:\n{task}\n\n"
        f"Previous actions:\n{_format_history(history)}\n\n"
        f"Current UI elements (tap only elements listed here, using the exact label):\n"
        f"{_format_elements(elements)}\n\n"
        "Note: for an empty text field, 'value' shows its placeholder text (e.g. "
        "'username@example.com'), not real content — verified directly against a real "
        "empty field. Only treat 'value' as actually entered if it plausibly matches "
        "what was typed, not a generic placeholder-looking hint.\n\n"
        "Choose exactly one next action by calling exactly one tool. "
        "If the task is already accomplished, call task_complete."
    )


def _try_recover_tool_call(content, tools):
    """Best-effort recovery for judge_step only: verified real case where the
    model emitted a tool-call-shaped JSON blob as plain text content (not
    Ollama's structured tool_calls field) because a string value — a reason
    quoting a UI label — contained unescaped quotes, breaking JSON parsing.
    Extracts `passed`/`reason` via regex from the raw text. Returns
    (name, args) or None if nothing recoverable is found — never invents a
    verdict; the `passed` boolean must actually be present in the text."""
    name_match = re.search(r'"name"\s*:\s*"(\w+)"', content)
    if not name_match:
        return None
    name = name_match.group(1)
    if name not in {t["function"]["name"] for t in tools}:
        return None

    passed_match = re.search(r'"passed"\s*:\s*(true|false)', content)
    if not passed_match:
        return None

    reason = ""
    reason_match = re.search(r'"reason"\s*:\s*"(.*)', content, re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip().rstrip('}').rstrip('"').strip()

    return name, {"passed": passed_match.group(1) == "true", "reason": reason}


def _call_with_tools(prompt, tools, allow_content_recovery=False):
    """Sends one prompt + tool schema to Ollama, returns the single resulting
    tool call as (name, args). Raises ReasoningError on any failure — no
    retries, no natural-language fallback parsing (except the narrow,
    transparent judge_step recovery above, when explicitly enabled)."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "tools": tools,
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # TimeoutError/OSError verified necessary: a real run crashed with an
        # unhandled raw TimeoutError from the socket layer — urllib.error.URLError
        # alone does not cover that case.
        raise ReasoningError(f"Could not reach Ollama at {OLLAMA_URL}: {e}")

    if "error" in body:
        raise ReasoningError(f"Ollama returned an error: {body['error']}")

    message = body.get("message", {})
    tool_calls = message.get("tool_calls") or []

    if len(tool_calls) == 0:
        content = message.get("content") or ""
        if allow_content_recovery:
            recovered = _try_recover_tool_call(content, tools)
            if recovered is not None:
                return recovered
        raise ReasoningError(
            f"Model returned no structured tool call. Raw content: {content!r}"
        )
    if len(tool_calls) > 1:
        raise ReasoningError(
            f"Model returned {len(tool_calls)} tool calls in one step; expected exactly one: {tool_calls}"
        )

    call = tool_calls[0]["function"]
    return call.get("name"), (call.get("arguments") or {})


def decide_next_action(task, elements, history):
    """Returns a dict like {"action": "tap", "label": "Continue"} or raises ReasoningError."""
    prompt = build_prompt(task, elements, history)
    name, args = _call_with_tools(prompt, TOOLS)

    if name not in {"tap", "swipe", "type", "task_complete"}:
        raise ReasoningError(f"Model returned unsupported action: {name!r}")

    return {"action": name, **args}


def judge_step(expected_result, elements):
    """Best-effort verdict on whether `expected_result` is observed in the
    current UI. This is the local model self-grading against prose — not an
    authoritative check. Returns {"passed": bool, "reason": str}."""
    prompt = (
        f"Expected result for the test step just performed:\n{expected_result}\n\n"
        f"Current UI elements:\n{_format_elements(elements)}\n\n"
        "Based only on the current UI elements above, did the expected result happen? "
        "Call step_verdict with your judgment."
    )
    name, args = _call_with_tools(prompt, STEP_VERDICT_TOOL, allow_content_recovery=True)

    if name != "step_verdict":
        raise ReasoningError(f"Model returned unsupported tool for a verdict call: {name!r}")

    return {"passed": bool(args.get("passed")), "reason": args.get("reason", "")}
