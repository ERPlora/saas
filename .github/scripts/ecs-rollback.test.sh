#!/usr/bin/env bash
# Tests for ecs-rollback.sh with a fake aws CLI that records every call, answers from fixtures and
# keeps each service's PRIMARY revision as state (update-service moves it), and a fake sleep that
# records the pauses (no test waits for real).
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
  export CALLS_LOG="$work/calls.log" SLEEP_LOG="$work/sleep.log" FIXTURES="$work/fixtures" STATE="$work/state"
  : > "$CALLS_LOG"
  : > "$SLEEP_LOG"

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
  # pre (plan 2026-10-14-entorno-pre): service saas-pre runs erplora-pre-saas:12 in its own cluster
  # (erplora-pre).
  echo "$td/erplora-pre-saas:12" > "$STATE/primary-saas-pre"
  printf '%s\t' "$td/erplora-pre-saas-migrate:11" "$td/erplora-pre-saas:12" "$td/erplora-pre-saas:10" \
    > "$FIXTURES/list-erplora-pre-saas"
  # The app image of a revision: reg.example/erplora/<saas|hub>[-pre]:tag-<revision>, unless listed here.
  : > "$FIXTURES/images"
  # The Environment tag of a revision is its family's environment unless listed here ("none" = no tag),
  # and its roles are erplora-<environment>-<name>-{task,execution} unless another prefix is listed.
  : > "$FIXTURES/environment-tags"
  : > "$FIXTURES/roles"

  # Fails after 500 pauses: a rollout loop that never times out fails its test instead of hanging.
  cat > "$work/bin/sleep" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$SLEEP_LOG"
if [ "$(wc -l < "$SLEEP_LOG")" -gt 500 ]; then
  echo "fake sleep: more than 500 pauses" >&2
  exit 1
fi
FAKE

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
    primary="$(cat "$STATE/primary-$service")"
    state=COMPLETED
    if [ -f "$STATE/moved-$service" ]; then
      # After update-service, successive reads of a service answer the next of FAKE_ROLLOUT_STATES
      # and, if set, FAKE_PRIMARY_REVISIONS (revision numbers of its family); the last one repeats.
      n="$(cat "$STATE/reads-$service" 2> /dev/null || echo 0)"
      echo "$((n + 1))" > "$STATE/reads-$service"
      read -ra states <<< "${FAKE_ROLLOUT_STATES:-COMPLETED}"
      s="$n"
      if [ "$s" -ge "${#states[@]}" ]; then s=$((${#states[@]} - 1)); fi
      state="${states[s]}"
      if [ -n "${FAKE_PRIMARY_REVISIONS:-}" ]; then
        read -ra revisions <<< "$FAKE_PRIMARY_REVISIONS"
        r="$n"
        if [ "$r" -ge "${#revisions[@]}" ]; then r=$((${#revisions[@]} - 1)); fi
        primary="${primary%:*}:${revisions[r]}"
      fi
    fi
    printf '%s\t%s\n' "$primary" "$state"
    ;;
  "ecs list-task-definitions")
    cat "$FIXTURES/list-$(value --family-prefix)"
    echo
    ;;
  "ecs describe-task-definition")
    # As `--include TAGS --output json` returns it; another container before the app's.
    arn="$(value --task-definition)"
    family="${arn##*/}"
    family="${family%:*}"
    environment="${family#erplora-}"
    environment="${environment%%-*}"
    name="${family#erplora-"$environment"-}"
    repository=erplora/hub
    if [[ "$name" == saas* ]]; then repository=erplora/saas; fi
    if [ "$environment" = pre ]; then repository="$repository-pre"; fi
    image="$(awk -v arn="$arn" '$1 == arn { print $2 }' "$FIXTURES/images")"
    tag="$(awk -v arn="$arn" '$1 == arn { print $2 }' "$FIXTURES/environment-tags")"
    role="$(awk -v arn="$arn" '$1 == arn { print $2 }' "$FIXTURES/roles")"
    jq -n --arg name "$name" --arg image "${image:-reg.example/$repository:tag-${arn##*:}}" \
      --arg tag "${tag:-$environment}" --arg role "arn:aws:iam::123456789012:role/${role:-$family}" '{
      taskDefinition: {
        taskRoleArn: "\($role)-task", executionRoleArn: "\($role)-execution",
        containerDefinitions: [
          {name: "log-router", image: "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
          {name: $name, image: $image}]
      },
      tags: ([{key: "Project", value: "erplora"}]
        + if $tag == "none" then [] else [{key: "Environment", value: $tag}] end)
    }'
    ;;
  "ecs update-service")
    service="$(value --service)"
    : > "$STATE/moved-$service"
    # The circuit breaker of FAKE_CIRCUIT_BREAKER's service puts its old revision back.
    if [ "${FAKE_CIRCUIT_BREAKER:-}" != "$service" ]; then
      value --task-definition > "$STATE/primary-$service"
    fi
    ;;
  *) ;;
esac
FAKE
  chmod +x "$work/bin/aws" "$work/bin/sleep"
}

# run_rollback [VAR=value...]: rolls back prod with the fake and CONFIRM=ROLLBACK; the arguments
# override (ENVIRONMENT=pre rolls back pre).
run_rollback() {
  env -u CLUSTER -u POLL_SECONDS -u ROLLOUT_TIMEOUT_SECONDS \
    PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK ENVIRONMENT=prod "$@" \
    bash "$here/ecs-rollback.sh" > "$work/out.log" 2>&1
}

# run_rollback_without <VAR>: the same with <VAR> unset.
run_rollback_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK ENVIRONMENT=prod \
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
# cluster_is <name>: there are cluster-scoped ecs calls (services and the wait), every one names
# cluster <name> and no call names another cluster.
cluster_scoped="^ecs (describe-services|update-service|wait services-stable) "
cluster_is() {
  grep -Eq -- "$cluster_scoped" "$CALLS_LOG" &&
    ! grep -E -- "$cluster_scoped" "$CALLS_LOG" | grep -qv -- "--cluster $1 " &&
    ! grep -E -- "--cluster" "$CALLS_LOG" | grep -qv -- "--cluster $1 "
}
# reads_of <service>: how many times its PRIMARY deployment was read after the wait.
reads_of() {
  local from
  from="$(line_of "wait services-stable")"
  if [ -z "$from" ]; then
    echo 0
    return
  fi
  tail -n "+$from" "$CALLS_LOG" | grep -c -- "describe-services .*--services $1 " || true
}

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
check "the restored revision is read with its tags" \
  'grep -q "describe-task-definition --task-definition $td/erplora-prod-saas:10 --include TAGS" "$CALLS_LOG"'
check "the image tag is read from the saas container of the restored revision, not from another one" \
  'grep -q "^ssm put-parameter .*--value tag-10 " "$CALLS_LOG" && ! grep -q "put-parameter .*--value stable" "$CALLS_LOG"'
check "the restored tag is recorded in SSM" \
  'grep -q "^ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 --type String --overwrite" "$CALLS_LOG"'
check "the tag is recorded only after the services are checked" \
  '[ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services")" ]'
check "every aws call names the region" '[ -s "$CALLS_LOG" ] && ! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'
check "prod: every cluster-scoped ecs call names prod's cluster erplora-prod" 'cluster_is erplora-prod'
check "the worker service is neither queried nor rolled back" '! grep -Eq -- "--services? worker( |$)|erplora-prod-worker" "$CALLS_LOG"'
check "nothing of the hub is touched" \
  '! grep -Eq -- "erplora-prod-hub|/erplora/prod/hub/|--services? hub( |$)" "$CALLS_LOG"'
check "nothing of pre is touched" '! grep -Eq -- "erplora-pre-|/erplora/pre/|saas-pre" "$CALLS_LOG"'

# --- pre (plan 2026-10-14-entorno-pre) --------------------------------------------------
setup
run_rollback ENVIRONMENT=pre && status=0 || status=$?
check "pre: the rollback succeeds" '[ "$status" -eq 0 ]'
check "pre: lists the ACTIVE revisions of pre's saas family" \
  'grep -q "list-task-definitions --family-prefix erplora-pre-saas --status ACTIVE --sort DESC" "$CALLS_LOG"'
check "pre: rolls back only the saas-pre service, to pre's previous revision" \
  'grep -q "update-service .*--service saas-pre --task-definition $td/erplora-pre-saas:10 " "$CALLS_LOG" &&
   [ "$(grep -c "update-service" "$CALLS_LOG")" -eq 1 ]'
check "pre: waits for saas-pre and checks its PRIMARY deployment" \
  'grep -Eq "wait services-stable .*--services saas-pre$" "$CALLS_LOG" && [ "$(reads_of saas-pre)" -ge 1 ]'
check "pre: records the restored tag in pre's parameter" \
  'grep -q "^ssm put-parameter --name /erplora/pre/saas/image_tag --value tag-10 --type String --overwrite" "$CALLS_LOG"'
check "pre: a pre rollback never names prod" \
  '! grep -Eq -- "erplora-prod-|/erplora/prod/|--services? saas( |$)" "$CALLS_LOG"'
check "pre: every cluster-scoped ecs call names pre's own cluster erplora-pre, never erplora-prod" \
  'cluster_is erplora-pre'
setup
echo "$td/erplora-pre-saas:10 reg.example/erplora/saas:tag-10" > "$FIXTURES/images"
run_rollback ENVIRONMENT=pre && status=0 || status=$?
check "pre: a previous revision on prod's image fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "::error::.*erplora/saas-pre" "$work/out.log"'

# --- the guard: only revisions of the rollback's own environment are restored ---------------
for case in "prod-tagged-pre:$td/erplora-prod-saas:10 pre:environment-tags:prod" \
  "prod-untagged:$td/erplora-prod-saas:10 none:environment-tags:prod" \
  "prod-with-pre-roles:$td/erplora-prod-saas:10 erplora-pre-saas:roles:prod" \
  "pre-tagged-prod:$td/erplora-pre-saas:10 prod:environment-tags:pre"; do
  name="${case%%:*}"
  rest="${case#*:}"
  environment="${rest##*:}"
  rest="${rest%:*}"
  setup
  echo "${rest%:*}" > "$FIXTURES/${rest##*:}"
  run_rollback ENVIRONMENT="$environment" && status=0 || status=$?
  check "guard ($name): a target revision of another environment is refused without changing anything" \
    '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" &&
     grep -q "::error::.*erplora-$environment-saas:10 is not a $environment revision" "$work/out.log"'
done

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

# --- the rollout after services-stable ----------------------------------------
# services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it
# COMPLETED once the old tasks have drained from the ALB, seconds to a minute later.
# rollback_error: the error of the saas service when the circuit breaker put back revision 12.
rollback_error() {
  grep -qF "::error::saas runs $td/erplora-prod-saas:12 (COMPLETED), not $td/erplora-prod-saas:10; rolled back by the circuit breaker? See the service events" "$work/out.log"
}

setup
run_rollback FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: IN_PROGRESS on the first read and COMPLETED on the second, the rollback succeeds" '[ "$status" -eq 0 ]'
check "rollout: the saas PRIMARY deployment is read again after one pause of POLL_SECONDS" \
  '[ "$(reads_of saas)" -eq 2 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15" ]'
check "rollout: the restored tag is recorded once the rollout is COMPLETED" \
  'grep -q "^ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 " "$CALLS_LOG" &&
   [ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services")" ]'
setup
run_rollback POLL_SECONDS=5 FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: POLL_SECONDS sets the pause" '[ "$status" -eq 0 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "5" ]'

setup
run_rollback FAKE_ROLLOUT_STATES=FAILED && status=0 || status=$?
check "a FAILED rollout fails the rollback at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "a FAILED rollout records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
check "the rollout error names the service and the state" 'grep -q "::error::saas .*FAILED" "$work/out.log"'
setup
run_rollback FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED" && status=0 || status=$?
check "a rollout that turns FAILED fails the rollback on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 2 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 1 ] && ! grep -q "put-parameter" "$CALLS_LOG"'

# The circuit breaker puts back the revision the service ran (12), and services-stable still succeeds.
setup
run_rollback FAKE_CIRCUIT_BREAKER=saas && status=0 || status=$?
check "a service the circuit breaker puts back fails the rollback at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "its error names the service and both revisions" 'rollback_error'
check "and no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_rollback FAKE_PRIMARY_REVISIONS="10 12" FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "a rollout IN_PROGRESS that the circuit breaker puts back fails the rollback on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 2 ] && rollback_error && ! grep -q "put-parameter" "$CALLS_LOG"'

setup
run_rollback FAKE_ROLLOUT_STATES=IN_PROGRESS ROLLOUT_TIMEOUT_SECONDS=30 && status=0 || status=$?
check "rollout timeout 30 s: reads at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 3 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15" ]'
check "rollout timeout: the error names the service and the limit" \
  'grep -q "::error::rollout of saas did not complete in 30 s" "$work/out.log"'
check "rollout timeout: no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_rollback FAKE_ROLLOUT_STATES=IN_PROGRESS && status=0 || status=$?
check "rollout timeout: 600 seconds by default (41 reads, 40 pauses)" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 41 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 40 ] &&
   grep -q "::error::rollout of saas did not complete in 600 s" "$work/out.log"'
for var in POLL_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  setup
  run_rollback "$var=soon" && status=0 || status=$?
  check "a $var that is not a number fails before any aws call" \
    '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::$var" "$work/out.log"'
done

# --- an explicit CLUSTER ------------------------------------------------------------
# Without CLUSTER each environment rolls back in its own cluster (erplora-<ENVIRONMENT>); CLUSTER wins.
for environment in prod pre; do
  setup
  run_rollback ENVIRONMENT="$environment" CLUSTER=custom-cluster && status=0 || status=$?
  check "$environment with CLUSTER=custom-cluster: the rollback succeeds" '[ "$status" -eq 0 ]'
  check "$environment with CLUSTER=custom-cluster: every cluster-scoped ecs call names custom-cluster" \
    'cluster_is custom-cluster'
done

# --- required environment -----------------------------------------------------------
setup
run_rollback_without AWS_REGION && status=0 || status=$?
check "without AWS_REGION it fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q AWS_REGION "$work/out.log"'
setup
run_rollback_without ENVIRONMENT && status=0 || status=$?
check "without ENVIRONMENT it fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::ENVIRONMENT.*prod.*pre" "$work/out.log"'
for environment in staging Prod; do
  setup
  run_rollback ENVIRONMENT="$environment" && status=0 || status=$?
  check "ENVIRONMENT '$environment' fails before any aws call" \
    '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::ENVIRONMENT.*prod.*pre" "$work/out.log"'
done

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
