#!/usr/bin/env bash
# Tests for e2e-report.sh with Playwright JSON reports written here and a fake gh CLI that answers
# the open issues (OPEN_ISSUES) and records its calls and the bodies it is given.
#   bash .github/scripts/e2e-report.test.sh
# The expected texts quote markdown: their backticks are literal (SC2016).
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

TITLE="Pruebas de navegador del SaaS en rojo en la pasada nocturna"
RUN=https://github.com/ERPlora/saas/actions/runs/123

mkdir -p "$work/bin"
cat > "$work/bin/gh" <<'FAKE'
#!/usr/bin/env bash
echo "gh $*" >> "$CALLS_LOG"
[ -z "${GH_FAILS:-}" ] || { echo "HTTP 502" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --body-file) cat "$2" >> "$BODIES_LOG"; shift ;;
    --comment|--body) printf '%s\n' "$2" >> "$BODIES_LOG"; shift ;;
  esac
  shift
done
case "$CALL" in *"issue list"*) printf '%s\n' "${OPEN_ISSUES:-[]}" ;; esac
FAKE
# The fake reads its own command line from CALL: a wrapper sets it.
mv "$work/bin/gh" "$work/bin/gh-fake"
cat > "$work/bin/gh" <<'WRAP'
#!/usr/bin/env bash
CALL="$*" exec "$(dirname "$0")/gh-fake" "$@"
WRAP
chmod +x "$work/bin/gh" "$work/bin/gh-fake"
export CALLS_LOG="$work/calls.log" BODIES_LOG="$work/bodies.log"

# A run with a red test inside a describe of a public spec, a timed-out panel test, a passing and a
# skipped one, as Playwright's json reporter writes it (colours in the messages included).
red_report="$work/red.json"
cat > "$red_report" <<'JSON'
{
  "suites": [
    {
      "title": "public-web.spec.ts", "file": "public-web.spec.ts", "line": 0,
      "specs": [
        {"title": "passes", "file": "public-web.spec.ts", "line": 2,
         "tests": [{"projectName": "public", "status": "expected", "results": [{"status": "passed"}]}]}
      ],
      "suites": [
        {
          "title": "PUBLIC-F01 the home", "file": "public-web.spec.ts", "line": 3,
          "specs": [
            {"title": "shows the plans", "file": "public-web.spec.ts", "line": 4,
             "tests": [{"projectName": "public", "status": "unexpected",
                        "results": [{"status": "failed",
                                     "error": {"message": "Error: \u001b[2mexpect(\u001b[22mlocator).toBeVisible()\n\nExpected: visible"}}]}]}
          ]
        }
      ]
    },
    {
      "title": "panel/login.spec.ts", "file": "panel/login.spec.ts", "line": 0,
      "specs": [
        {"title": "skipped one", "file": "panel/login.spec.ts", "line": 2,
         "tests": [{"projectName": "panel", "status": "skipped", "results": [{"status": "skipped"}]}]},
        {"title": "signs in", "file": "panel/login.spec.ts", "line": 9,
         "tests": [{"projectName": "panel", "status": "unexpected",
                    "results": [{"status": "timedOut", "error": {"message": "Test timeout of 120000ms exceeded."}}]}]}
      ]
    }
  ],
  "errors": [],
  "stats": {"expected": 1, "skipped": 1, "unexpected": 2, "flaky": 0, "duration": 1000}
}
JSON

# A run that stopped in globalSetup: no test ran, the error is the run's.
setup_report="$work/setup.json"
cat > "$setup_report" <<'JSON'
{"suites": [], "errors": [{"message": "Error: unapplied migrations (hubs.0042)\n    at globalSetup"}],
 "stats": {"expected": 0, "skipped": 0, "unexpected": 0, "flaky": 0, "duration": 10}}
JSON

# report VAR=value...: runs e2e-report.sh; leaves its calls, bodies and summary in the logs.
report() {
  : > "$CALLS_LOG"
  : > "$BODIES_LOG"
  : > "$work/summary"
  if env PATH="$work/bin:$PATH" GH_REPO=ERPlora/saas GH_TOKEN=fake RUN_URL="$RUN" SHA=0123456789abcdef \
    DAY=2026-11-06 GITHUB_STEP_SUMMARY="$work/summary" PUBLISH=true RESULT=failure REPORT="$red_report" \
    "$@" bash "$here/e2e-report.sh" > "$work/out" 2>&1; then
    echo 0
  else
    echo 1
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
has() { grep -cF -- "$2" "$1" || true; }
writes() { grep -cE '^gh issue (create|comment|close|edit|reopen)' "$CALLS_LOG" || true; }

# --- red, no open issue: one new issue with what came out red ---------------------------------
expect "a red run with no open issue ends well" 0 "$(report)"
expect "it opens one issue, with the title and prio:P1" 1 \
  "$(grep -cF -- "gh issue create --title $TITLE --label prio:P1 --body-file" "$CALLS_LOG" || true)"
expect "it looks for the issue among the open ones only" 1 "$(grep -c '^gh issue list --state open' "$CALLS_LOG" || true)"
expect "it searches the issue by its exact title, not among the latest N issues" 1 \
  "$(grep -cF -- "--search \"$TITLE\" in:title" "$CALLS_LOG" || true)"
expect "the body opens with «## Qué pasa»" "## Qué pasa" "$(head -n 1 "$BODIES_LOG")"
expect "the body lists the red test of a describe: project, file:line and titles" 1 \
  "$(has "$BODIES_LOG" '- `[public] public-web.spec.ts:4` › PUBLIC-F01 the home › shows the plans — Error: expect(locator).toBeVisible()')"
expect "the body lists the timed-out test with its error" 1 \
  "$(has "$BODIES_LOG" '- `[panel] panel/login.spec.ts:9` › signs in — Test timeout of 120000ms exceeded.')"
expect "no colour code reaches the body" 0 "$(grep -c $'\033' "$BODIES_LOG" || true)"
expect "passing and skipped tests are not listed" 0 "$(grep -cE 'passes|skipped one' "$BODIES_LOG" || true)"
expect "the body counts the run" 1 "$(has "$BODIES_LOG" '2 en rojo · 1 bien · 1 saltadas')"
expect "the body reproduces with the run" 1 "$(has "$BODIES_LOG" "- Run: $RUN")"
expect "the body says where it comes from" 1 "$(has "$BODIES_LOG" '- Sale de #296')"
for section in "## Propuesta" "## Detalle técnico" "## Origen" "## Cómo se reproduce" "## Flujo"; do
  expect "the body has «${section}»" 1 "$(grep -cxF -- "${section}" "$BODIES_LOG" || true)"
done
expect "the run's summary lists the red tests too" 1 "$(has "$work/summary" 'panel/login.spec.ts:9')"

# --- red, the issue already open: a comment on it, no second issue -----------------------------
open="[{\"number\": 43, \"title\": \"$TITLE (otra)\"}, {\"number\": 42, \"title\": \"$TITLE\"}]"
expect "a red run with the issue open ends well" 0 "$(report OPEN_ISSUES="$open")"
expect "it comments on the open issue of that exact title" 1 "$(grep -c '^gh issue comment 42 --body-file' "$CALLS_LOG" || true)"
expect "and writes nothing else" 1 "$(writes)"
expect "the comment says the night and the run" 1 "$(has "$BODIES_LOG" "La pasada del 2026-11-06 sigue en rojo: $RUN")"
expect "the comment lists the red tests" 1 "$(has "$BODIES_LOG" 'panel/login.spec.ts:9')"

# --- green: the open issue is closed; nothing to do without one -------------------------------
expect "a green run with the issue open ends well" 0 "$(report OPEN_ISSUES="$open" RESULT=success REPORT=/nonexistent)"
expect "it closes the issue as completed, with the run" 1 \
  "$(grep -c '^gh issue close 42 --reason completed --comment' "$CALLS_LOG" || true)"
expect "the closing comment names the run" 1 "$(has "$BODIES_LOG" "$RUN")"
expect "and writes nothing else" 1 "$(writes)"
expect "a green run with no open issue ends well" 0 "$(report RESULT=success REPORT=/nonexistent)"
expect "and writes no issue" 0 "$(writes)"
expect "its summary says green" 1 "$(grep -cxF '## Pruebas de navegador: en verde' "$work/summary" || true)"

# --- red without a report, or stopped before the specs ----------------------------------------
expect "a red run without a report ends well" 0 "$(report REPORT=/nonexistent RESULT=cancelled)"
expect "it still opens the issue" 1 "$(grep -c '^gh issue create' "$CALLS_LOG" || true)"
expect "saying there is no report and how the run ended" 1 \
  "$(has "$BODIES_LOG" 'La ejecución terminó en `cancelled` sin informe de las pruebas')"
expect "a run stopped in globalSetup ends well" 0 "$(report REPORT="$setup_report")"
expect "it lists the run's own error" 1 "$(has "$BODIES_LOG" '- Error de la ejecución: Error: unapplied migrations (hubs.0042)')"

# --- outside main: the summary only --------------------------------------------------------------
expect "a red run outside main ends well" 0 "$(report PUBLISH=false)"
expect "it never calls gh" 0 "$(wc -l < "$CALLS_LOG" | tr -d ' ')"
expect "its summary lists the red tests" 1 "$(has "$work/summary" 'panel/login.spec.ts:9')"
expect "its summary says no issue was written" 1 "$(has "$work/summary" 'Fuera de main: no se escribe ninguna issue.')"

# --- gh failing is a failure, never a silent green -----------------------------------------------
expect "a gh that fails fails the script" 1 "$(report GH_FAILS=1)"

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
