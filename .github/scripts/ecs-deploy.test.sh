#!/usr/bin/env bash
# Tests for ecs-deploy.sh with a fake aws CLI that records every call and answers from fixtures,
# and a fake sleep that records the pauses (no test waits for real).
#   bash .github/scripts/ecs-deploy.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0

# A task definition as `describe-task-definition --include TAGS` returns it, with the roles Terraform
# gives it (aws-next modules/ecs-service: <family>-task and <family>-execution) and the Environment
# tag of its family's environment (erplora-<environment>-<name>).
# task_definition <family> <containers JSON> [<Environment tag; empty = none> [<role prefix>]]
task_definition() {
  local environment="${1#erplora-}"
  environment="${environment%%-*}"
  jq -n --arg family "$1" --argjson containers "$2" --arg environment "${3-$environment}" \
    --arg role "arn:aws:iam::123456789012:role/${4:-$1}" '{
    taskDefinition: {
      family: $family, taskDefinitionArn: "arn:td/\($family):1", revision: 1, status: "ACTIVE",
      requiresAttributes: [], compatibilities: ["FARGATE"], registeredAt: "t", registeredBy: "u",
      taskRoleArn: "\($role)-task", executionRoleArn: "\($role)-execution", containerDefinitions: $containers
    },
    tags: ([{key: "Project", value: "erplora"}, {key: "ManagedBy", value: "terraform"}]
      + if $environment == "" then [] else [{key: "Environment", value: $environment}] end)
  }'
}

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin" "$work/fixtures"
  export CALLS_LOG="$work/calls.log" REGISTERED_LOG="$work/registered.log" SLEEP_LOG="$work/sleep.log"
  export FIXTURES="$work/fixtures" POLLS="$work/polls" ROLLOUT_POLLS="$work/rollout-polls"
  : > "$CALLS_LOG"
  : > "$REGISTERED_LOG"
  : > "$SLEEP_LOG"

  # saas, saas-migrate and saas-cron run one container each, on the saas image; the saas fixture
  # also carries containers of other images (the hub's among them), which must stay as they are.
  task_definition erplora-prod-saas '[
    {"name": "saas", "image": "reg.example/erplora/saas:bootstrap"},
    {"name": "log-router", "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
    {"name": "look-alike", "image": "reg.example/erplora/saasx:bootstrap"},
    {"name": "hub-image", "image": "reg.example/erplora/hub:bootstrap"}]' > "$FIXTURES/erplora-prod-saas.json"
  task_definition erplora-prod-saas-migrate '[
    {"name": "saas-migrate", "image": "reg.example/erplora/saas:bootstrap"}]' > "$FIXTURES/erplora-prod-saas-migrate.json"
  task_definition erplora-prod-saas-cron '[
    {"name": "saas-cron", "image": "reg.example/erplora/saas:bootstrap"}]' > "$FIXTURES/erplora-prod-saas-cron.json"
  # The hub's families live in the same cluster: this repo must never read them.
  for family in hub worker hub-migrate db-bootstrap; do
    task_definition "erplora-prod-$family" "[{\"name\": \"$family\", \"image\": \"reg.example/erplora/hub:bootstrap\"}]" \
      > "$FIXTURES/erplora-prod-$family.json"
  done
  # pre (plan 2026-10-14-entorno-pre): its own cluster (erplora-pre), its own families on its own
  # ECR repository (erplora/saas-pre) and no saas-cron. The containers keep the short names.
  task_definition erplora-pre-saas '[
    {"name": "saas", "image": "reg.example/erplora/saas-pre:bootstrap"},
    {"name": "prod-image", "image": "reg.example/erplora/saas:bootstrap"}]' > "$FIXTURES/erplora-pre-saas.json"
  task_definition erplora-pre-saas-migrate '[
    {"name": "saas-migrate", "image": "reg.example/erplora/saas-pre:bootstrap"}]' > "$FIXTURES/erplora-pre-saas-migrate.json"

  # Fails after 500 pauses: a migration loop that never times out fails its test instead of hanging.
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
  "ecs describe-task-definition")
    family="$(value --task-definition)"
    if [ ! -f "$FIXTURES/$family.json" ]; then
      echo "An error occurred (ClientException): Unable to describe task definition." >&2
      exit 254
    fi
    # Tags only come back when asked for.
    if [ "$(value --include)" = TAGS ]; then cat "$FIXTURES/$family.json"; else jq 'del(.tags)' "$FIXTURES/$family.json"; fi
    ;;
  "ecs register-task-definition")
    file="$(value --cli-input-json)"
    file="${file#file://}"
    jq -c . "$file" >> "$REGISTERED_LOG"
    echo "arn:td/$(jq -r .family "$file"):2"
    ;;
  "ecs describe-services")
    service="$(value --services)"
    if [[ "$(value --query)" == *deployments* ]]; then
      # PRIMARY deployment after the wait: successive reads of a service answer the next of
      # FAKE_PRIMARY_REVISIONS and FAKE_ROLLOUT_STATES (the last one repeats); by default the new
      # revision (2), COMPLETED.
      read -ra revisions <<< "${FAKE_PRIMARY_REVISIONS:-2}"
      read -ra states <<< "${FAKE_ROLLOUT_STATES:-COMPLETED}"
      n="$(cat "$ROLLOUT_POLLS.$service" 2> /dev/null || echo 0)"
      echo "$((n + 1))" > "$ROLLOUT_POLLS.$service"
      r="$n" s="$n"
      if [ "$r" -ge "${#revisions[@]}" ]; then r=$((${#revisions[@]} - 1)); fi
      if [ "$s" -ge "${#states[@]}" ]; then s=$((${#states[@]} - 1)); fi
      # Service <name> runs family erplora-prod-<name>; service <name>-pre, erplora-pre-<name>.
      family="erplora-prod-$service"
      if [[ "$service" == *-pre ]]; then family="erplora-pre-${service%-pre}"; fi
      printf '%s\t%s\n' "arn:td/$family:${revisions[r]}" "${states[s]}"
    else
      # Each service's own security group, so the test sees whose configuration the migration got.
      jq -cn --arg sg "sg-$service" '{awsvpcConfiguration: {subnets: ["s"], securityGroups: [$sg], assignPublicIp: "ENABLED"}}'
    fi
    ;;
  "ecs run-task")
    if [ -n "${FAKE_RUN_TASK_FAILURE:-}" ]; then
      jq -n --arg reason "$FAKE_RUN_TASK_FAILURE" '{tasks: [], failures: [{arn: "arn:capacity", reason: $reason}]}'
    else
      jq -n --arg cluster "$(value --cluster)" '{tasks: [{taskArn: "arn:task/\($cluster)/migrate1"}], failures: []}'
    fi
    ;;
  "ecs describe-tasks")
    case "$(value --query)" in
      *lastStatus*)
        # FAKE_TASK_STATUSES: what successive polls answer; the last one repeats.
        read -ra statuses <<< "${FAKE_TASK_STATUSES:-RUNNING STOPPED}"
        n="$(cat "$POLLS" 2> /dev/null || echo 0)"
        echo "$((n + 1))" > "$POLLS"
        if [ "$n" -ge "${#statuses[@]}" ]; then n=$((${#statuses[@]} - 1)); fi
        echo "${statuses[n]}"
        ;;
      *exitCode*) echo "${FAKE_MIGRATE_EXIT:-0}" ;;
      *stoppedReason*) echo "${FAKE_STOPPED_REASON:-Essential container in task exited}" ;;
    esac
    ;;
  *) ;;
esac
FAKE
  chmod +x "$work/bin/aws" "$work/bin/sleep"
}

# run_deploy [VAR=value...]: deploys abc123 to prod with the fakes; the arguments override the
# environment (ENVIRONMENT=pre deploys to pre).
run_deploy() {
  env -u CLUSTER -u PROJECT -u POLL_SECONDS -u MIGRATE_TIMEOUT_SECONDS -u ROLLOUT_TIMEOUT_SECONDS \
    PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 ENVIRONMENT=prod "$@" \
    bash "$here/ecs-deploy.sh" > "$work/out.log" 2>&1
}

# run_deploy_without <VAR>: the same with <VAR> unset.
run_deploy_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 ENVIRONMENT=prod \
    env -u "$1" bash "$here/ecs-deploy.sh" > "$work/out.log" 2>&1
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
count_of() { grep -c -- "$1" "$CALLS_LOG" || true; }
# cluster_is <name>: there are cluster-scoped ecs calls (services, tasks, the wait), every one names
# cluster <name> and no call names another cluster.
cluster_scoped="^ecs (describe-services|update-service|run-task|describe-tasks|wait services-stable) "
cluster_is() {
  grep -Eq -- "$cluster_scoped" "$CALLS_LOG" &&
    ! grep -E -- "$cluster_scoped" "$CALLS_LOG" | grep -qv -- "--cluster $1 " &&
    ! grep -E -- "--cluster" "$CALLS_LOG" | grep -qv -- "--cluster $1 "
}
# registered <family> <jq filter>: evaluates the filter on the revision registered for <family>.
registered() { jq -e --arg family "$1" "select(.family == \$family) | $2" "$REGISTERED_LOG" > /dev/null; }

# --- a deploy that succeeds ---------------------------------------------------
setup
run_deploy && status=0 || status=$?
check "deploy succeeds" '[ "$status" -eq 0 ]'
check "registers a new revision of saas, saas-cron and saas-migrate, and nothing else" \
  '[ "$(jq -r .family "$REGISTERED_LOG" | sort | paste -sd " " -)" = "erplora-prod-saas erplora-prod-saas-cron erplora-prod-saas-migrate" ]'
check "no hub family (hub, worker, hub-migrate, db-bootstrap) is read nor registered" \
  '! grep -Eq -- "--task-definition erplora-prod-(hub|worker|db-bootstrap)" "$CALLS_LOG"'
check "every container of the saas image gets the new image: saas, saas-migrate and saas-cron" \
  'registered erplora-prod-saas "[.containerDefinitions[] | select(.name == \"saas\") | .image] == [\"reg.example/erplora/saas:abc123\"]" &&
   registered erplora-prod-saas-migrate "[.containerDefinitions[].image] == [\"reg.example/erplora/saas:abc123\"]" &&
   registered erplora-prod-saas-cron "[.containerDefinitions[].image] == [\"reg.example/erplora/saas:abc123\"]"'
check "containers of another image keep theirs, the hub's included" \
  'registered erplora-prod-saas "[.containerDefinitions[] | select(.name != \"saas\") | .image] == [\"public.ecr.aws/aws-observability/aws-for-fluent-bit:stable\", \"reg.example/erplora/saasx:bootstrap\", \"reg.example/erplora/hub:bootstrap\"]"'
check "the rest of the definition is kept" \
  'registered erplora-prod-saas ".taskRoleArn == \"arn:aws:iam::123456789012:role/erplora-prod-saas-task\""'
check "read-only fields are stripped before registering" \
  '! jq -e "has(\"taskDefinitionArn\") or has(\"revision\") or has(\"status\") or has(\"requiresAttributes\") or has(\"compatibilities\") or has(\"registeredAt\") or has(\"registeredBy\")" "$REGISTERED_LOG" > /dev/null'
check "the new revision keeps the tags of the one it copies, Environment=prod included" \
  'registered erplora-prod-saas-cron ".tags == [{\"key\": \"Project\", \"value\": \"erplora\"}, {\"key\": \"ManagedBy\", \"value\": \"terraform\"}, {\"key\": \"Environment\", \"value\": \"prod\"}]"'
check "prod moves its service without touching its desired count (autoscaling owns it)" '! grep -q -- "--desired-count" "$CALLS_LOG"'
check "nothing of pre is touched" '! grep -Eq -- "erplora-pre-|/erplora/pre/|saas-pre" "$CALLS_LOG" "$REGISTERED_LOG"'
check "the network configuration of the migration is read from the saas service" \
  'grep -q "describe-services .*--services saas .*--query services\[0\]\.networkConfiguration" "$CALLS_LOG"'
check "the migration runs the new saas-migrate revision with the saas network configuration" \
  'grep -q "run-task .*--task-definition arn:td/erplora-prod-saas-migrate:2 .*--network-configuration {\"awsvpcConfiguration\".*\"sg-saas\"" "$CALLS_LOG"'
check "aws ecs wait tasks-stopped is not used" '! grep -q "wait tasks-stopped" "$CALLS_LOG"'
check "the exit code is read from the migration container, by name" \
  'grep -q "describe-tasks .*containers\[?name==.saas-migrate.\]\.exitCode" "$CALLS_LOG" && ! grep -q "containers\[0\]" "$CALLS_LOG"'
check "the migration finishes before any service changes" \
  '[ "$(last_line_of "describe-tasks")" -lt "$(line_of "update-service")" ]'
check "only the saas service moves, to its new revision" \
  'grep -q "update-service .*--service saas --task-definition arn:td/erplora-prod-saas:2" "$CALLS_LOG" && [ "$(count_of "update-service")" -eq 1 ]'
check "saas-cron and saas-migrate are registered, never run as a service" \
  '! grep -Eq "update-service .*--service saas-(cron|migrate)" "$CALLS_LOG" && ! grep -q "run-task .*saas-cron" "$CALLS_LOG"'
check "the deploy waits for the saas service only" \
  'grep -Eq "wait services-stable .*--services saas$" "$CALLS_LOG"'
check "after the wait, the saas PRIMARY deployment is checked" \
  'n="$(last_line_of "describe-services .*--services saas .*deployments")"; [ -n "$n" ] && [ "$n" -gt "$(line_of "wait services-stable")" ]'
check "the deployed tag is recorded in SSM" \
  'grep -q "^ssm put-parameter --name /erplora/prod/saas/image_tag --value abc123 --type String --overwrite" "$CALLS_LOG"'
check "the tag is recorded only after the services are checked" \
  '[ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services .*deployments")" ]'
check "every aws call names the region" '[ -s "$CALLS_LOG" ] && ! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'
check "prod: every cluster-scoped ecs call names prod's cluster erplora-prod" 'cluster_is erplora-prod'
check "the worker service is neither queried nor updated" '! grep -Eq -- "--services? worker( |$)" "$CALLS_LOG"'
check "nothing of the hub is touched" \
  '! grep -Eq -- "erplora-prod-(hub|worker|db-bootstrap)|/erplora/prod/hub/|--services? hub( |$)" "$CALLS_LOG"'

# --- polling the migration ----------------------------------------------------
setup
run_deploy FAKE_TASK_STATUSES="PROVISIONING PENDING RUNNING STOPPED" && status=0 || status=$?
check "polling: a slow migration still succeeds" '[ "$status" -eq 0 ]'
check "polling: the task is polled until it is STOPPED" '[ "$(count_of "describe-tasks .*lastStatus")" -eq 4 ]'
check "polling: every 15 seconds by default" '[ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15 15" ]'
setup
run_deploy POLL_SECONDS=5 FAKE_TASK_STATUSES="RUNNING STOPPED" && status=0 || status=$?
check "polling: POLL_SECONDS sets the pause" '[ "$status" -eq 0 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "5" ]'

setup
run_deploy MIGRATE_TIMEOUT_SECONDS=0 && status=0 || status=$?
check "timeout 0: a migration that is not STOPPED fails the deploy" '[ "$status" -ne 0 ]'
check "timeout 0: no service changes and no tag is recorded" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "timeout 0: the task is left running" '! grep -q "stop-task" "$CALLS_LOG"'
check "timeout 0: the error names the timeout and the task" \
  'grep -q "::error::.*saas-migrate.*0s.*arn:task/erplora-prod/migrate1" "$work/out.log"'
setup
run_deploy MIGRATE_TIMEOUT_SECONDS=30 FAKE_TASK_STATUSES=RUNNING && status=0 || status=$?
check "timeout 30 s: polls at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(count_of "describe-tasks .*lastStatus")" -eq 3 ] && ! grep -q "update-service" "$CALLS_LOG"'
setup
run_deploy MIGRATE_TIMEOUT_SECONDS=soon && status=0 || status=$?
check "a MIGRATE_TIMEOUT_SECONDS that is not a number fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q MIGRATE_TIMEOUT_SECONDS "$work/out.log"'

# --- a migration that fails ---------------------------------------------------
setup
run_deploy FAKE_MIGRATE_EXIT=1 && status=0 || status=$?
check "a failed migration fails the deploy" '[ "$status" -ne 0 ]'
check "a failed migration changes no service and records no tag" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "the error names the exit code and the log group" \
  'grep -q "::error::saas-migrate .*code 1.*/ecs/erplora-prod-saas-migrate" "$work/out.log"'

setup
run_deploy FAKE_MIGRATE_EXIT=None FAKE_STOPPED_REASON="CannotPullContainerError: pull image manifest has been retried 1 time(s)" &&
  status=0 || status=$?
check "a migration that never ran fails the deploy" '[ "$status" -ne 0 ] && ! grep -q "update-service" "$CALLS_LOG"'
check "its error shows the stoppedReason" \
  'grep -q "::error::saas-migrate .*CannotPullContainerError: pull image manifest has been retried 1 time(s)" "$work/out.log"'

setup
run_deploy FAKE_RUN_TASK_FAILURE="RESOURCE:ENI" && status=0 || status=$?
check "a migration task that cannot start fails the deploy" \
  '[ "$status" -ne 0 ] && ! grep -Eq "describe-tasks|update-service|put-parameter" "$CALLS_LOG"'
check "its error shows the failure reason" 'grep -q "::error::saas-migrate .*RESOURCE:ENI" "$work/out.log"'

# --- a family without the saas image -------------------------------------------
# saas-cron is the scheduled tasks' family: a revision left on the old image would keep it running.
setup
task_definition erplora-prod-saas-cron '[{"name": "saas-cron", "image": "other.example/erplora/saas:bootstrap"}]' \
  > "$FIXTURES/erplora-prod-saas-cron.json"
run_deploy && status=0 || status=$?
check "a family with no container of the saas image fails before the migration" \
  '[ "$status" -ne 0 ] && ! grep -Eq "run-task|update-service|put-parameter" "$CALLS_LOG"'
check "its error names the family" 'grep -q "::error::erplora-prod-saas-cron " "$work/out.log"'
setup
task_definition erplora-prod-saas-migrate '[{"name": "saas-migrate", "image": "reg.example/erplora/hub:bootstrap"}]' \
  > "$FIXTURES/erplora-prod-saas-migrate.json"
run_deploy && status=0 || status=$?
check "a family on the hub image fails before the migration" \
  '[ "$status" -ne 0 ] && ! grep -Eq "run-task|update-service|put-parameter" "$CALLS_LOG" && grep -q "::error::erplora-prod-saas-migrate " "$work/out.log"'

# --- the rollout after services-stable ----------------------------------------
# services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it
# COMPLETED once the old tasks have drained from the ALB, seconds to a minute later.
# FAKE_TASK_STATUSES=STOPPED: the migration needs no pause, so every pause logged is the rollout's.
# reads_of <service>: how many times its PRIMARY deployment was read.
reads_of() { count_of "describe-services .*--services $1 .*deployments"; }
rollback_error() {
  grep -qF "::error::$1 runs arn:td/erplora-prod-$1:1 (COMPLETED), not arn:td/erplora-prod-$1:2; rolled back by the circuit breaker? See the service events" "$work/out.log"
}

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: IN_PROGRESS on the first read and COMPLETED on the second, the deploy succeeds" '[ "$status" -eq 0 ]'
check "rollout: the saas PRIMARY deployment is read again after one pause of POLL_SECONDS" \
  '[ "$(reads_of saas)" -eq 2 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15" ]'
check "rollout: the tag is recorded once the rollout is COMPLETED" \
  'grep -q "^ssm put-parameter --name /erplora/prod/saas/image_tag --value abc123 " "$CALLS_LOG" &&
   [ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services .*deployments")" ]'

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=FAILED && status=0 || status=$?
check "a FAILED rollout fails the deploy at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "a FAILED rollout records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
check "the rollout error names the service and the state" 'grep -q "::error::saas .*FAILED" "$work/out.log"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED" && status=0 || status=$?
check "a rollout that turns FAILED fails the deploy on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 2 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 1 ] && ! grep -q "put-parameter" "$CALLS_LOG"'

# rollback = true: the circuit breaker puts the old revision back and services-stable still succeeds.
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_PRIMARY_REVISIONS=1 && status=0 || status=$?
check "a service rolled back to the old revision fails the deploy at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "the rollback error names the service and both revisions" 'rollback_error saas'
check "a rolled back deploy records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_PRIMARY_REVISIONS="2 1" FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" &&
  status=0 || status=$?
check "a rollout IN_PROGRESS that the circuit breaker rolls back fails the deploy on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 2 ] && rollback_error saas && ! grep -q "put-parameter" "$CALLS_LOG"'

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=IN_PROGRESS ROLLOUT_TIMEOUT_SECONDS=30 && status=0 || status=$?
check "rollout timeout 30 s: reads at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 3 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15" ]'
check "rollout timeout: the error names the service and the limit" \
  'grep -q "::error::rollout of saas did not complete in 30 s" "$work/out.log"'
check "rollout timeout: no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=IN_PROGRESS && status=0 || status=$?
check "rollout timeout: 600 seconds by default (41 reads, 40 pauses)" \
  '[ "$status" -ne 0 ] && [ "$(reads_of saas)" -eq 41 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 40 ] &&
   grep -q "::error::rollout of saas did not complete in 600 s" "$work/out.log"'
setup
run_deploy ROLLOUT_TIMEOUT_SECONDS=soon && status=0 || status=$?
check "a ROLLOUT_TIMEOUT_SECONDS that is not a number fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q ROLLOUT_TIMEOUT_SECONDS "$work/out.log"'

# --- pre (plan 2026-10-14-entorno-pre) ---------------------------------------------
setup
run_deploy ENVIRONMENT=pre && status=0 || status=$?
check "pre: the deploy succeeds" '[ "$status" -eq 0 ]'
check "pre: registers only pre families (saas and saas-migrate; no saas-cron in pre)" \
  '[ "$(jq -r .family "$REGISTERED_LOG" | sort | paste -sd " " -)" = "erplora-pre-saas erplora-pre-saas-migrate" ]'
check "pre: the containers of pre's image get the new image from pre's ECR repository" \
  'registered erplora-pre-saas "[.containerDefinitions[] | select(.name == \"saas\") | .image] == [\"reg.example/erplora/saas-pre:abc123\"]" &&
   registered erplora-pre-saas-migrate "[.containerDefinitions[].image] == [\"reg.example/erplora/saas-pre:abc123\"]" &&
   registered erplora-pre-saas "[.containerDefinitions[] | select(.name == \"prod-image\") | .image] == [\"reg.example/erplora/saas:bootstrap\"]"'
check "pre: the new revisions keep Environment=pre" \
  'registered erplora-pre-saas "any(.tags[]; .key == \"Environment\" and .value == \"pre\")"'
check "pre: the migration runs pre's saas-migrate with the network of the saas-pre service" \
  'grep -q "describe-services .*--services saas-pre .*--query services\[0\]\.networkConfiguration" "$CALLS_LOG" &&
   grep -q "run-task .*--task-definition arn:td/erplora-pre-saas-migrate:2 .*\"sg-saas-pre\"" "$CALLS_LOG"'
check "pre: the exit code is read from the saas-migrate container, by its short name" \
  'grep -q "describe-tasks .*containers\[?name==.saas-migrate.\]\.exitCode" "$CALLS_LOG"'
check "pre: only the saas-pre service moves, to pre's new revision" \
  'grep -q "update-service .*--service saas-pre --task-definition arn:td/erplora-pre-saas:2 " "$CALLS_LOG" && [ "$(count_of "update-service")" -eq 1 ]'
check "pre: a push wakes pre up (desired count 1)" \
  'grep -q "update-service .*--service saas-pre .*--desired-count 1 " "$CALLS_LOG"'
check "pre: the deploy waits for saas-pre and checks its PRIMARY deployment" \
  'grep -Eq "wait services-stable .*--services saas-pre$" "$CALLS_LOG" &&
   [ "$(last_line_of "describe-services .*--services saas-pre .*deployments")" -gt "$(line_of "wait services-stable")" ]'
check "pre: records its own image tag" \
  'grep -q "^ssm put-parameter --name /erplora/pre/saas/image_tag --value abc123 --type String --overwrite" "$CALLS_LOG"'
check "pre: a pre run never names prod (families, parameters, services, ECR repository)" \
  '! grep -Eq -- "erplora-prod-|/erplora/prod/|--services? saas( |$)|erplora/saas:abc123" "$CALLS_LOG" "$REGISTERED_LOG"'
check "pre: every aws call names the region" '! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'
check "pre: every cluster-scoped ecs call names pre's own cluster erplora-pre, never erplora-prod" \
  'cluster_is erplora-pre'
setup
run_deploy ENVIRONMENT=pre FAKE_MIGRATE_EXIT=1 && status=0 || status=$?
check "pre: a failed migration names pre's log group and changes nothing" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" &&
   grep -q "::error::saas-migrate .*code 1.*/ecs/erplora-pre-saas-migrate" "$work/out.log"'

# --- the guard: only revisions of the deploy's own environment are copied -----------------
# The pre deploy role can register a revision in any family (ecs:RegisterTaskDefinition takes no
# resource), so a base revision without the Environment tag of this run, or with another
# environment's roles, is refused before anything is registered (plan 2026-10-14-entorno-pre, A3).
setup
task_definition erplora-prod-saas-cron '[{"name": "saas-cron", "image": "reg.example/erplora/saas:bootstrap"}]' "" \
  > "$FIXTURES/erplora-prod-saas-cron.json"
run_deploy && status=0 || status=$?
check "guard: a prod revision without the Environment tag is refused and nothing is registered" \
  '[ "$status" -ne 0 ] && [ ! -s "$REGISTERED_LOG" ] && ! grep -Eq "register-task-definition|run-task|update-service|put-parameter" "$CALLS_LOG"'
check "guard: the error names the family and the environment" \
  'grep -q "::error::erplora-prod-saas-cron is not a prod revision" "$work/out.log"'
setup
task_definition erplora-pre-saas '[{"name": "saas", "image": "reg.example/erplora/saas-pre:bootstrap"}]' prod \
  > "$FIXTURES/erplora-pre-saas.json"
run_deploy ENVIRONMENT=pre && status=0 || status=$?
check "guard: a pre family tagged Environment=prod is refused and nothing is registered" \
  '[ "$status" -ne 0 ] && [ ! -s "$REGISTERED_LOG" ] && grep -q "::error::erplora-pre-saas is not a pre revision" "$work/out.log"'
setup
task_definition erplora-prod-saas-migrate '[{"name": "saas-migrate", "image": "reg.example/erplora/saas:bootstrap"}]' prod \
  erplora-pre-saas-migrate > "$FIXTURES/erplora-prod-saas-migrate.json"
run_deploy && status=0 || status=$?
check "guard: a prod revision with pre's roles is refused and nothing is registered" \
  '[ "$status" -ne 0 ] && [ ! -s "$REGISTERED_LOG" ] && grep -q "::error::erplora-prod-saas-migrate is not a prod revision" "$work/out.log"'
setup
jq 'del(.taskDefinition.taskRoleArn, .taskDefinition.executionRoleArn)' "$FIXTURES/erplora-prod-saas.json" > "$work/no-roles.json"
mv "$work/no-roles.json" "$FIXTURES/erplora-prod-saas.json"
run_deploy && status=0 || status=$?
check "guard: a revision without roles is refused and nothing is registered" \
  '[ "$status" -ne 0 ] && [ ! -s "$REGISTERED_LOG" ] && grep -q "::error::erplora-prod-saas is not a prod revision" "$work/out.log"'

# --- an explicit CLUSTER ----------------------------------------------------------
# Without CLUSTER each environment deploys to its own cluster (erplora-<ENVIRONMENT>); CLUSTER wins.
for environment in prod pre; do
  setup
  run_deploy ENVIRONMENT="$environment" CLUSTER=custom-cluster && status=0 || status=$?
  check "$environment with CLUSTER=custom-cluster: the deploy succeeds" '[ "$status" -eq 0 ]'
  check "$environment with CLUSTER=custom-cluster: every cluster-scoped ecs call names custom-cluster" \
    'cluster_is custom-cluster'
done

# --- required environment -----------------------------------------------------
for environment in staging Prod ""; do
  setup
  run_deploy ENVIRONMENT="$environment" && status=0 || status=$?
  check "ENVIRONMENT '$environment' fails before any aws call, naming prod and pre" \
    '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::ENVIRONMENT.*prod.*pre" "$work/out.log"'
done
for var in AWS_REGION REGISTRY IMAGE_TAG ENVIRONMENT; do
  setup
  run_deploy_without "$var" && status=0 || status=$?
  check "without $var it fails before any aws call" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'
  check "the error names $var" 'grep -q "$var" "$work/out.log"'
done

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
