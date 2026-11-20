#!/usr/bin/env bash
# The checks a change passes before it is pushed; .githooks/pre-push runs `fast` on every pushed commit.
#   fast [<since>]: the guardrail tests of file size and of ruff's function limits, and then ESLint, the typecheck,
#         Vitest and pytest on what the change touches since <since> (scripts/checks.py).
set -u
cd "$(dirname "$0")/.." || exit 1
exec uv run --no-sync python scripts/checks.py "$@"
