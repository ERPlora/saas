#!/usr/bin/env bash
# Tests for ecs-rollback.sh with a fake aws CLI that records every call, answers from fixtures and
# keeps each service's PRIMARY revision as state (update-service moves it).
#   bash .github/scripts/ecs-rollback.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
td="arn:aws:ecs:eu-south-2:123456789012:task-definition"

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin" "$work/fixtures" "$work/state"
  export CALLS_LOG="$work/calls.log" FIXTURES="$work/fixtures" STATE="$work/state"
  : > "$CALLS_LOG"

  # saas runs revision 12. The family prefix of saas also lists saas-migrate and saas-cron, and
  # saas has a newer revision (13) than the one it runs: the previous one is saas:10, not
  # saas-migrate:11 nor saas-cron:11.
  echo "$td/erplora-prod-saas:12" > "$STATE/primary-saas"
  printf '%s\t' "$td/erplora-prod-saas-migrate:14" "$td/erplora-prod-saas-migrate:11" "$td/erplora-prod-saas-cron:11" \
    "$td/erplora-prod-saas:13" "$td/erplora-prod-saas:12" "$td/erplora-prod-saas:10" "$td/erplora-prod-saas:9" \
    > "$FIXTURES/list-erplora-prod-saas"
  # The hub's services live in the same cluster: this repo must never query nor move them.
  echo "$td/erplora-prod-hub:12" > "$STATE/primary-hub"
  echo "$td/erplora-prod-worker:12" > "$STATE/primary-worker"
  printf '%s\t' "$td/erplora-prod-hub:12" "$td/erplora-prod-hub:10" > "$FIXTURES/list-erplora-prod-hub"
  printf '%s\t' "$td/erplora-prod-worker:12" "$td/erplora-prod-worker:10" > "$FIXTURES/list-erplora-prod-worker"
  # The app image of a revision: reg.example/erplora/<saas|hub>:tag-<revision>, unless listed here.
  : > "$FIXTURES/images"

  cat > "$work/bin/aws" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$CALLS_LOG"
args=("$@")
# value <flag>: the argument that follows <flag> in this call.
value() {
  local i
  for ((i = 0; i < ${#args[@]} - 1; i++)); do
    if [ "${args[i]}" = "$1" ]; then
      printf '%s\n' "${args[i + 1]}"
      return
    fi
  done
}
case "$1 $2" in
  "ecs describe-services")
    service="$(value --services)"
    printf '%s\t%s\n' "$(cat "$STATE/primary-$service")" "${FAKE_ROLLOUT_STATE:-COMPLETED}"
    ;;
  "ecs list-task-definitions")
    cat "$FIXTURES/list-$(value --family-prefix)"
    echo
    ;;
  "ecs describe-task-definition")
    arn="$(value --task-definition)"
    image="$(awk -v arn="$arn" '$1 == arn { print $2 }' "$FIXTURES/images")"
    project=saas
    if [[ "$arn" != */erplora-prod-saas:* ]]; then project=hub; fi
    echo "${image:-reg.example/erplora/$project:tag-${arn##*:}}"
    ;;
  "ecs update-service")
    service="$(value --service)"
    # The circuit breaker of FAKE_CIRCUIT_BREAKER's service puts its old revision back.
    if [ "${FAKE_CIRCUIT_BREAKER:-}" != "$service" ]; then
      value --task-definition > "$STATE/primary-$service"
    fi
    ;;
  *) ;;
esac
FAKE
  chmod +x "$work/bin/aws"
}

# run_rollback [VAR=value...]: rolls back with the fake and CONFIRM=ROLLBACK; the arguments override.
run_rollback() {
  env -u CLUSTER PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK "$@" \
    bash "$here/ecs-rollback.sh" > "$work/out.log" 2>&1
}

# run_rollback_without <VAR>: the same with <VAR> unset.
run_rollback_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK \
    env -u "$1" bash "$here/ecs-rollback.sh" > "$work/out.log" 2>&1
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    failures=$((failures + 1))
  fi
}

line_of() { grep -n -- "$1" "$CALLS_LOG" | head -1 | cut -d: -f1; }
last_line_of() { grep -n -- "$1" "$CALLS_LOG" | tail -1 | cut -d: -f1; }

# --- confirmation ---------------------------------------------------------------
setup
run_rollback_without CONFIRM && status=0 || status=$?
check "without CONFIRM it fails before any aws call" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'
check "the error asks for ROLLBACK" 'grep -q "::error::.*ROLLBACK" "$work/out.log"'
setup
run_rollback CONFIRM=rollback && status=0 || status=$?
check "CONFIRM must be exactly ROLLBACK" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'

# --- a rollback that succeeds -------------------------------------------------------
setup
run_rollback && status=0 || status=$?
check "rollback succeeds" '[ "$status" -eq 0 ]'
check "warns that migrations are not undone" 'grep -qi "migrations are not undone" "$work/out.log"'
check "lists the ACTIVE revisions of the saas family, newest first" \
  'grep -q "list-task-definitions --family-prefix erplora-prod-saas --status ACTIVE --sort DESC" "$CALLS_LOG"'
check "saas goes back to the ACTIVE revision right before its PRIMARY one, of its own family" \
  'grep -q "update-service .*--service saas --task-definition $td/erplora-prod-saas:10 " "$CALLS_LOG"'
check "only the saas service moves" '[ "$(grep -c "update-service" "$CALLS_LOG")" -eq 1 ]'
check "the rollback waits for the saas service only" \
  '[ "$(line_of "wait services-stable .*--services saas$")" -gt "$(last_line_of "update-service")" ]'
check "after the wait, the saas PRIMARY deployment is checked" \
  '[ "$(last_line_of "describe-services .*--services saas ")" -gt "$(line_of "wait services-stable")" ]'
check "the image tag is read from the saas container of the restored revision" \
  'grep -q "describe-task-definition --task-definition $td/erplora-prod-saas:10 .*containerDefinitions\[?name==.saas.\]" "$CALLS_LOG"'
check "the restored tag is recorded in SSM" \
  'grep -q "^ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 --type String --overwrite" "$CALLS_LOG"'
check "the tag is recorded only after the services are checked" \
  '[ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services")" ]'
check "every aws call names the region" '[ -s "$CALLS_LOG" ] && ! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'
check "the worker service is neither queried nor rolled back" '! grep -Eq -- "--services? worker( |$)|erplora-prod-worker" "$CALLS_LOG"'
check "nothing of the hub is touched" \
  '! grep -Eq -- "erplora-prod-hub|/erplora/prod/hub/|--services? hub( |$)" "$CALLS_LOG"'

# --- nothing to roll back to ----------------------------------------------------------
setup
printf '%s\t' "$td/erplora-prod-saas-migrate:11" "$td/erplora-prod-saas-cron:11" "$td/erplora-prod-saas:13" \
  "$td/erplora-prod-saas:12" > "$FIXTURES/list-erplora-prod-saas"
run_rollback && status=0 || status=$?
check "without a previous ACTIVE revision it fails" '[ "$status" -ne 0 ]'
check "and changes no service and records no tag" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "its error names the service" 'grep -q "::error::saas " "$work/out.log"'

setup
echo None > "$STATE/primary-saas"
run_rollback && status=0 || status=$?
check "a service without a PRIMARY deployment fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "::error::saas " "$work/out.log"'

# --- a previous revision that does not run the saas image -------------------------------
setup
echo "$td/erplora-prod-saas:10 other.example/thing:1" > "$FIXTURES/images"
run_rollback && status=0 || status=$?
check "a previous revision without the saas image fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "other.example/thing:1" "$work/out.log"'
setup
echo "$td/erplora-prod-saas:10 reg.example/erplora/hub:tag-10" > "$FIXTURES/images"
run_rollback && status=0 || status=$?
check "a previous revision on the hub image fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "::error::.*erplora/saas" "$work/out.log"'

# --- circuit breaker ------------------------------------------------------------
setup
run_rollback FAKE_CIRCUIT_BREAKER=saas && status=0 || status=$?
check "a service the circuit breaker puts back fails the rollback" '[ "$status" -ne 0 ]'
check "its error names the service" 'grep -q "::error::saas " "$work/out.log"'
check "and no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_rollback FAKE_ROLLOUT_STATE=FAILED && status=0 || status=$?
check "a FAILED rollout fails the rollback and records no tag" \
  '[ "$status" -ne 0 ] && ! grep -q "put-parameter" "$CALLS_LOG" && grep -q "::error::saas .*FAILED" "$work/out.log"'

# --- required environment -----------------------------------------------------------
setup
run_rollback_without AWS_REGION && status=0 || status=$?
check "without AWS_REGION it fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q AWS_REGION "$work/out.log"'

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
