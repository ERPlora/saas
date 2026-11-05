#!/usr/bin/env bash
# Tests for e2e-specs.sh against a throwaway git repository with the shape of tests/e2e/.
#   bash .github/scripts/e2e-specs.test.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Commits never read the developer's git configuration (identity, signing).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
repo="$work/repo"
commit() { git -C "$repo" add -A && git -C "$repo" -c user.name=ci -c user.email=ci@example.com commit --quiet -m "$1"; }
# write <path> [<content>]: each file its own content (its path), so git pairs no unrelated add and delete as a rename.
write() { mkdir -p "$(dirname "$repo/$1")" && printf '%s\n' "${2:-$1}" > "$repo/$1"; }

DOORS=tests/e2e/panel/assistant-gateway.spec.ts

# main: the doors' spec, a public spec, three panel specs and a helper.
git init --quiet -b main "$repo"
write "$DOORS"
write tests/e2e/public-web.spec.ts
write tests/e2e/panel/login.spec.ts
write tests/e2e/panel/billing.spec.ts
write tests/e2e/panel/members.spec.ts
write tests/e2e/panel/fixtures.ts
write docs.md
commit main

# specs [base]: runs e2e-specs.sh in the repository; prints its lines, or FAILS.
specs() {
  if (cd "$repo" && bash "$here/e2e-specs.sh" "$@") > "$work/out" 2> "$work/err"; then
    cat "$work/out"
  else
    echo FAILS
  fi
}

# expect <name> <expected> <actual>
expect() {
  if [ "$3" = "$2" ]; then
    echo "ok   - $1"
  else
    echo "FAIL - $1: expected '$2', got '$3'"
    failures=$((failures + 1))
  fi
}

expect "main itself runs only the doors' spec" "$DOORS" "$(specs main)"

# A branch that changes a panel spec, adds a public one, deletes another, renames a third and
# touches a helper and a doc.
git -C "$repo" switch --quiet -c work
write tests/e2e/panel/login.spec.ts changed
write tests/e2e/public-new.spec.ts
git -C "$repo" rm --quiet tests/e2e/panel/billing.spec.ts
git -C "$repo" mv tests/e2e/public-web.spec.ts tests/e2e/public-renamed.spec.ts
write tests/e2e/panel/fixtures.ts changed
write docs.md changed
commit work

expected="$DOORS
tests/e2e/panel/login.spec.ts
tests/e2e/public-new.spec.ts
tests/e2e/public-renamed.spec.ts"
expect "a branch runs the doors' spec and every spec it adds, changes or renames, sorted" "$expected" "$(specs main)"

# main moves on after the branch left it, adding a spec and changing another: the specs main
# changed are not the branch's.
git -C "$repo" switch --quiet main
write tests/e2e/panel/later-on-main.spec.ts
write tests/e2e/panel/members.spec.ts changed-on-main
commit "main moves on"
git -C "$repo" switch --quiet work
expect "the specs main changed since the branch left it do not count" "$expected" "$(specs main)"

# The branch changes the doors' spec: it is still listed once.
write "$DOORS" changed
commit "doors"
expect "the doors' spec is listed once when the branch changes it too" 1 "$(specs main | grep -c "^$DOORS\$")"

# A spec outside tests/e2e/ is not an e2e spec.
write frontend/__tests__/widget.spec.ts
commit "vitest spec"
expect "a spec outside tests/e2e/ is not listed" 0 "$(specs main | grep -c '^frontend/' || true)"

expect "an unknown base fails instead of running fewer specs" FAILS "$(specs origin/nowhere)"
expect "no base fails" FAILS "$(specs)"

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
