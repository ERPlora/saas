#!/usr/bin/env bash
# Prints, one per line, the e2e specs a push runs (e2e.yml with `specs: changed`): the spec of the
# assistant's doors, which no screen covers (saas#285), and every spec under tests/e2e/ that the branch
# adds, changes or renames since it left <base>. Sorted, each once. What the branch does not touch is
# the nightly run's (nightly.yml, saas#296): a change to a helper or a seed shows there.
#   bash .github/scripts/e2e-specs.sh <base>          (from the repository's root; base: origin/main in CI)
#   bash .github/scripts/e2e-specs.sh --many <base>   many=true when they are more than e2e.yml's short timeout
#                                                      holds (they get the timeout of every spec), else many=false
# An unknown base fails: running fewer specs than the branch changed would pass for green.
set -euo pipefail

DOORS=tests/e2e/panel/assistant-gateway.spec.ts
# On GitHub's runner the ten longest specs take some 17 of the short timeout's 30 minutes, setup aside.
MANY=10

mode=list
if [ "${1:-}" = --many ]; then
  mode=many
  shift
fi
base="${1:?usage: e2e-specs.sh [--many] <base>}"
fork="$(git merge-base "$base" HEAD)"

specs="$(
  {
    echo "$DOORS"
    # --diff-filter=d: a deleted spec is not run; a renamed one is, under its new name.
    git diff --name-only --diff-filter=d "$fork" HEAD -- 'tests/e2e/*.spec.ts'
  } | sort -u
)"

if [ "$mode" = list ]; then
  echo "$specs"
elif [ "$(wc -l <<< "$specs")" -gt "$MANY" ]; then
  echo many=true
else
  echo many=false
fi
