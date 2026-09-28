"""Parses a test-case markdown doc in the specific format demonstrated by the
user (an "Attribute | Details" table, a "Test Execution Steps" table with
Step/Action/Expected Result/Status columns, and a "Post-conditions" bullet
list), and writes results back into a copy of that same structure.

This is deliberately narrow — it matches the one format shown, not markdown
tables in general. If the expected structure isn't found, parsing fails
explicitly rather than guessing.
"""
import re


class TestCaseError(Exception):
    pass


def _strip_cell(text):
    text = text.strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # drop **bold**
    text = text.replace("<br>", " ").replace("<br/>", " ")
    return text.strip()


_QUOTED_RE = re.compile(r'"([^"]+)"')


def extract_quoted_strings(text):
    """Every double-quoted substring in `text`, in appearance order, e.g.
    'Tap the "Sign in" link.' -> ['Sign in']. [] if none. Never raises.
    Shared by run_test_case.py's deterministic action and verdict fast
    paths, so both agree on what counts as an exact, checkable target."""
    return _QUOTED_RE.findall(text)


def _split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def _is_separator_row(cells):
    return all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def parse_test_case(path):
    with open(path) as f:
        lines = f.readlines()

    attributes = {}
    steps = []
    postconditions = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()

        if line.startswith("|") and "attribute" in line.lower() and "details" in line.lower():
            i += 2  # header + separator
            while i < n and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i])
                if len(cells) >= 2:
                    key = _strip_cell(cells[0])
                    value = _strip_cell(cells[1])
                    attributes[key] = value
                i += 1
            continue

        if line.startswith("|") and "step" in line.lower() and "action" in line.lower():
            header_cells = [c.lower() for c in _split_row(line)]
            try:
                action_idx = header_cells.index("action")
                expected_idx = next(idx for idx, c in enumerate(header_cells) if "expected" in c)
            except (ValueError, StopIteration):
                raise TestCaseError(f"Steps table header missing 'Action' or 'Expected Result' column: {line}")
            i += 2  # header + separator
            step_num = 0
            while i < n and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i])
                if len(cells) > max(action_idx, expected_idx):
                    step_num += 1
                    steps.append({
                        "step": step_num,
                        "action": _strip_cell(cells[action_idx]),
                        "expected": _strip_cell(cells[expected_idx]),
                        "line_index": i,
                        "cells": cells,
                    })
                i += 1
            continue

        if line.lower().startswith("#### post-conditions") or line.lower().startswith("### post-conditions"):
            i += 1
            while i < n and (lines[i].strip().startswith("*") or lines[i].strip().startswith("-")):
                postconditions.append(_strip_cell(lines[i].strip().lstrip("*-").strip()))
                i += 1
            continue

        i += 1

    if not steps:
        raise TestCaseError(
            f"No 'Test Execution Steps' table found in {path} — expected a markdown table "
            "with 'Step' and 'Action' columns."
        )

    return {
        "scenario": attributes.get("Test Scenario", ""),
        "priority": attributes.get("Priority", ""),
        "preconditions": attributes.get("Pre-conditions", ""),
        "steps": steps,
        "postconditions": postconditions,
        "raw_lines": lines,
    }


def _escape_table_cell(text):
    """Verified real bug: a verdict reason containing a literal '|' (the
    model's own prose, not markdown syntax — e.g. mentioning two fields
    separated by '|') was inserted unescaped into a table row built by
    joining cells with ' | ', silently adding an extra column and
    corrupting/truncating everything after it when the file was re-read.
    Standard markdown escaping (\\|) keeps it inside its own cell. Newlines
    are also collapsed — a table row must stay on one line."""
    return text.replace("|", "\\|").replace("\n", " ")


def write_results(test_case, step_results, postcondition_result, out_path):
    """step_results: list of {"passed": bool|None, "reason": str} aligned with
    test_case['steps'] (None = blocked/not attempted). Writes a new file —
    never overwrites the source test case."""
    lines = list(test_case["raw_lines"])

    for step, result in zip(test_case["steps"], step_results):
        cells = list(step["cells"])
        if result["passed"] is None:
            status = "BLOCKED"
        else:
            status = "PASS" if result["passed"] else "FAIL"
        reason = _escape_table_cell(result["reason"]) if result["reason"] else ""
        status_idx = len(cells) - 1
        cells[status_idx] = f"{status} — {reason}" if reason else status
        lines[step["line_index"]] = "| " + " | ".join(cells) + " |\n"

    summary = ["\n#### Automated Run Results (agent self-assessment — not authoritative)\n\n"]
    for step, result in zip(test_case["steps"], step_results):
        status = "BLOCKED" if result["passed"] is None else ("PASS" if result["passed"] else "FAIL")
        summary.append(f"- Step {step['step']}: **{status}** — {result['reason']}\n")
    if postcondition_result is not None:
        pc_status = "BLOCKED" if postcondition_result["passed"] is None else (
            "PASS" if postcondition_result["passed"] else "FAIL")
        summary.append(f"- Post-conditions: **{pc_status}** — {postcondition_result['reason']}\n")

    with open(out_path, "w") as f:
        f.writelines(lines)
        f.writelines(summary)
