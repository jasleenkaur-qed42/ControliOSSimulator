#!/bin/bash
# PostToolUse hook (Write|Edit): this repo has no linter or test suite, so a
# syntax error in a .py file is otherwise only caught by actually running it.
# Blocks with the compiler error so Claude sees and fixes it immediately.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN=python3

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"

if [ -n "$file" ] && [[ "$file" == *.py ]] && [ -f "$file" ]; then
  if ! out="$("$PYTHON_BIN" -m py_compile "$file" 2>&1)"; then
    reason="$(printf '%s' "$out" | jq -Rs .)"
    printf '{"decision":"block","reason":%s}\n' "$reason"
  fi
fi
exit 0
