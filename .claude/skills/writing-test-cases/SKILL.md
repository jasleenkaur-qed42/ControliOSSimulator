---
name: writing-test-cases
description: Use when authoring a new test-case markdown file for run_test_case.py, when a test-case doc fails to parse, or when its rows aren't hitting the zero-LLM deterministic fast path (falling into the slower LLM-agentic loop instead) or are getting a wrong/deferred verdict.
---

# Writing test cases

`test_case.py` parses one specific markdown shape. If it isn't found, parsing fails explicitly — this is not general markdown-table support.

## Required structure

1. An "Attribute | Details" table (2+ columns) somewhere near the top. Recognized keys: `Test Scenario`, `Priority`, `Pre-conditions`.
2. A "Step | Action | Expected Result | ... | Status" table — column order doesn't matter beyond needing an `Action` column and one column containing "expected" (case-insensitive); the *last* column is treated as Status and gets overwritten with PASS/FAIL/BLOCKED.
3. A `### Post-conditions` or `#### Post-conditions` heading followed by a `*`/`-` bullet list (optional).

## The quoting convention (this is what makes rows fast and reliable)

Quote the exact target in each row's own instruction text:

| Step | Action | Expected Result | Status |
|---|---|---|---|
| 1 | Tap the "Username or email" field. | The field becomes focused. | |
| 2 | Type "user1@xyz.com". | "user1@xyz.com" appears in the field. | |
| 3 | Tap the "Sign in" link. | The home screen appears with "Products" visible. | |

- **Action**: exactly one quoted string lets `_try_deterministic_action` resolve and execute the row with zero LLM calls. A row instructing typing (starts with "Type") is only deterministic if the *immediately preceding* row's tap left a text-entry field focused — always precede a `Type "X".` row with its own `Tap "field label".` row; the row's own text (not history) is what decides whether typing is expected, so never phrase one row as "tap or type".
- **Expected Result**: every quoted label in it must currently be resolvable for a deterministic PASS. For a `Type "X".` row specifically, PASS also confirms the previously-focused field's live value exactly equals `X` (skipped for `SecureTextField` — masked values can't be verified either way).
- Avoid words that assert a state change you can't verify from presence alone — `enabled`, `disabled`, `selected`, `active`, `becomes`, `(un)checked`, `(un)highlighted` — perception only ever captures label/type/frame/value, never enabled/selected state. Expected Results containing these always defer to `judge_step` (the local model's non-authoritative self-grading), even if the quoted labels are all present.

Anything not matching this — no quote, a compound instruction, an ambiguous label — still works, just falls through to the slower per-row LLM loop instead of failing.

## Verifying a new test case

Run it (see `running-the-agent`) and check the JSON log: `deterministic_action_used`/`deterministic_verdict_used` on the rows you expected to be fast, `llm_verdict_used` only where a state-change claim genuinely requires it.
