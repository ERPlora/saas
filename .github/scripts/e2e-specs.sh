#!/usr/bin/env bash
# Prints, one per line, the e2e specs a push runs (e2e.yml with `specs: changed`): the spec of the
# assistant's doors, which no screen covers (saas#285), and every spec under tests/e2e/ that the branch
# adds, changes or renames since it left <base>. Sorted, each once. What the branch does not touch is
# the nightly run's (nightly.yml, saas#296): a change to a helper or a seed shows there.
#   bash .github/scripts/e2e-specs.sh <base>        (from the repository's root; base: origin/main in CI)
# An unknown base fails: running fewer specs than the branch changed would pass for green.
set -euo pipefail

DOORS=tests/e2e/panel/assistant-gateway.spec.ts

base="${1:?usage: e2e-specs.sh <base>}"
fork="$(git merge-base "$base" HEAD)"

{
  echo "$DOORS"
  # --diff-filter=d: a deleted spec is not run; a renamed one is, under its new name.
  git diff --name-only --diff-filter=d "$fork" HEAD -- 'tests/e2e/*.spec.ts'
} | sort -u
