#!/usr/bin/env bash
# Deploys an image tag of the saas to one environment, in that environment's own ECS cluster
# (erplora-<ENVIRONMENT>; PLAN-AWS §6; plan 2026-10-14-entorno-pre), touching only that
# environment's saas task families and service:
#   prod: cluster erplora-prod, families erplora-prod-{saas,saas-migrate,saas-cron}, service saas,
#         image erplora/saas;
#   pre:  cluster erplora-pre, families erplora-pre-{saas,saas-migrate} (no saas-cron), service
#         saas-pre, image erplora/saas-pre; the containers keep the short names (saas, saas-migrate).
#   0. reads the latest ACTIVE revision of every family and refuses them all, registering nothing,
#      unless each one carries the tag Environment=<ENVIRONMENT> and the task and execution roles of
#      its environment (role/erplora-<ENVIRONMENT>-…): ecs:RegisterTaskDefinition takes no resource,
#      so another environment's deploy role could have left a revision in this family;
#   1. registers a new revision of each family from that one, with its tags, changing only the image
#      of the containers that run the saas image (one per task: the app); Terraform owns the rest of
#      the definition; saas-cron is only registered (the Scheduler runs its latest);
#   2. runs the migration (saas-migrate) on the new revision and polls it until it is STOPPED; if it
#      fails, never ran or outlasts MIGRATE_TIMEOUT_SECONDS (the task is left running), the deploy
#      stops before any service changes;
#   3. moves the services to the new revisions (in pre also to one task: a push wakes pre up, which
#      its schedule stops every evening), waits until they are stable and then polls each
#      one's PRIMARY deployment until it is the new revision, COMPLETED: ECS marks it COMPLETED
#      seconds to a minute after services-stable returns, once the old tasks drain from the ALB.
#      A FAILED rollout or another revision as PRIMARY (with rollback = true the circuit breaker
#      puts the old one back and the wait still succeeds) fails at once; a rollout that outlasts
#      ROLLOUT_TIMEOUT_SECONDS fails too;
#   4. records the tag in /erplora/<ENVIRONMENT>/saas/image_tag, so the revisions Terraform
#      registers, and with them the scheduled tasks, keep running it (aws-next README, "Imagen").
# Never db-bootstrap: the deploy role cannot pass its roles (aws-next deploy_role.tf).
# Rollback: the circuit breaker reverts a broken deploy; back to the previous revisions, the
#   rollback workflow (ecs-rollback.sh); back to a release, the deploy workflow with that release.
#
# Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA), ENVIRONMENT
#      (prod|pre); optional CLUSTER (erplora-<ENVIRONMENT>: each environment has its own cluster),
#      POLL_SECONDS (15), MIGRATE_TIMEOUT_SECONDS (3600), ROLLOUT_TIMEOUT_SECONDS (600).
set -euo pipefail

for var in AWS_REGION REGISTRY IMAGE_TAG; do
  if [ -z "${!var:-}" ]; then
    echo "::error::$var is required" >&2
    exit 1
  fi
done
ENVIRONMENT="${ENVIRONMENT:-}"
if [ "$ENVIRONMENT" != prod ] && [ "$ENVIRONMENT" != pre ]; then
  echo "::error::ENVIRONMENT must be prod or pre, not '$ENVIRONMENT'" >&2
  exit 1
fi
CLUSTER="${CLUSTER:-erplora-$ENVIRONMENT}"
POLL_SECONDS="${POLL_SECONDS:-15}"
MIGRATE_TIMEOUT_SECONDS="${MIGRATE_TIMEOUT_SECONDS:-3600}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-600}"
for var in POLL_SECONDS MIGRATE_TIMEOUT_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
    echo "::error::$var must be a number of seconds, not '${!var}'" >&2
    exit 1
  fi
done

# This repo deploys the saas; the hub repo keeps its own copy of this script.
PROJECT=saas
migration=saas-migrate
# Families that run as a service; the service of family <name> is <name><suffix>.
services=(saas)
if [ "$ENVIRONMENT" = prod ]; then
  families=(saas saas-migrate saas-cron)
  suffix=""
  # Autoscaling owns prod's desired count.
  wake=()
else
  # pre has no scheduled platform tasks (plan 2026-10-14-entorno-pre, §6).
  families=(saas saas-migrate)
  suffix=-pre
  # Its schedule stops pre every evening: a push starts it again.
  wake=(--desired-count 1)
fi
prefix="erplora-$ENVIRONMENT"
# The saas repo has no worker: the migration runs like the saas service (same subnets, sg-app,
# public IP; sg-app reaches Aurora and Valkey, and nothing listens on 8000 in the migration).
network_service="saas$suffix"

project_image="$REGISTRY/erplora/$PROJECT$suffix:"
image="$project_image$IMAGE_TAG"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# prepare <family>: reads its latest ACTIVE revision, refuses one of another environment and writes
# the new revision to register, with the new image.
prepare() {
  local name="$1"
  aws ecs describe-task-definition --task-definition "$prefix-$name" --include TAGS \
    --region "$AWS_REGION" --output json > "$workdir/$name.base.json"
  if ! jq -e --arg environment "$ENVIRONMENT" '
      any(.tags[]?; .key == "Environment" and .value == $environment)
      and ([.taskDefinition.taskRoleArn, .taskDefinition.executionRoleArn]
           | all(type == "string" and test("^arn:aws[a-z-]*:iam::[0-9]{12}:role/erplora-\($environment)-")))' \
    "$workdir/$name.base.json" > /dev/null; then
    echo "::error::$prefix-$name is not a $ENVIRONMENT revision (it needs the tag Environment=$ENVIRONMENT and the roles erplora-$ENVIRONMENT-*); nothing was registered" >&2
    exit 1
  fi
  jq --arg project_image "$project_image" --arg image "$image" '
      (.tags // []) as $tags
      | .taskDefinition
      | .containerDefinitions |= map(if ((.image // "") | startswith($project_image)) then .image = $image else . end)
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
            .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)
      | if ($tags | length) > 0 then .tags = $tags else . end' \
    "$workdir/$name.base.json" > "$workdir/$name.json"
  if ! jq -e --arg image "$image" 'any(.containerDefinitions[]; .image == $image)' "$workdir/$name.json" > /dev/null; then
    echo "::error::$prefix-$name has no container of the image $project_image<tag>; nothing was registered" >&2
    exit 1
  fi
}

register() {
  local name="$1"
  aws ecs register-task-definition --cli-input-json "file://$workdir/$name.json" \
    --region "$AWS_REGION" --query taskDefinition.taskDefinitionArn --output text > "$workdir/$name.arn"
  echo "registered $(cat "$workdir/$name.arn")"
}

arn_of() { cat "$workdir/$1.arn"; }

# primary <service>: "<task definition ARN> <rollout state>" of its PRIMARY deployment.
primary() {
  aws ecs describe-services --cluster "$CLUSTER" --services "$1" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text
}

# migrate <family>: its container has the family's name (aws-next modules/ecs-service).
migrate() {
  local name="$1" run task status code reason waited=0
  run="$(aws ecs run-task --cluster "$CLUSTER" --launch-type FARGATE \
    --task-definition "$(arn_of "$name")" \
    --network-configuration "$network" \
    --started-by "deploy-${IMAGE_TAG:0:12}" \
    --region "$AWS_REGION" --output json)"
  task="$(jq -r '.tasks[0].taskArn // empty' <<< "$run")"
  if [ -z "$task" ]; then
    echo "::error::$name did not start: $(jq -c '.failures' <<< "$run")" >&2
    exit 1
  fi
  echo "running $name: $task"

  while :; do
    status="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
      --query 'tasks[0].lastStatus' --output text)"
    if [ "$status" = STOPPED ]; then
      break
    fi
    if [ "$waited" -ge "$MIGRATE_TIMEOUT_SECONDS" ]; then
      echo "::error::$name is still $status after ${MIGRATE_TIMEOUT_SECONDS}s; it was left running ($task) and no service changed; logs in /ecs/$prefix-$name" >&2
      exit 1
    fi
    sleep "$POLL_SECONDS"
    waited=$((waited + POLL_SECONDS))
  done

  code="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
    --query "tasks[0].containers[?name=='$name'].exitCode | [0]" --output text)"
  if [ "$code" = None ]; then
    reason="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
      --query 'tasks[0].stoppedReason' --output text)"
    echo "::error::$name stopped without running: $reason" >&2
    exit 1
  fi
  if [ "$code" != 0 ]; then
    echo "::error::$name exited with code $code; logs in /ecs/$prefix-$name" >&2
    exit 1
  fi
}

# Every family is checked before any is registered.
for name in "${families[@]}"; do
  prepare "$name"
done
for name in "${families[@]}"; do
  register "$name"
done

# The migration runs with network_service's network configuration.
network="$(aws ecs describe-services --cluster "$CLUSTER" --services "$network_service" --region "$AWS_REGION" \
  --query 'services[0].networkConfiguration' --output json)"

migrate "$migration"

service_names=()
for name in "${services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "$name$suffix" \
    --task-definition "$(arn_of "$name")" "${wake[@]}" --region "$AWS_REGION" > /dev/null
  echo "updated $name$suffix"
  service_names+=("$name$suffix")
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${service_names[@]}"

# services-stable can return while a PRIMARY deployment is still IN_PROGRESS: poll the services
# (by family) whose rollout has not completed yet, all of them on the same clock.
pending=("${services[@]}")
waited=0
while :; do
  failed=0
  in_progress=()
  for name in "${pending[@]}"; do
    service="$name$suffix"
    out="$(primary "$service")"
    read -r task_definition state <<< "$out"
    if [ "$task_definition" != "$(arn_of "$name")" ] || [ "$state" = FAILED ]; then
      echo "::error::$service runs $task_definition ($state), not $(arn_of "$name"); rolled back by the circuit breaker? See the service events" >&2
      failed=1
    elif [ "$state" != COMPLETED ]; then
      in_progress+=("$name")
    fi
  done
  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
  if [ "${#in_progress[@]}" -eq 0 ]; then
    break
  fi
  if [ "$waited" -ge "$ROLLOUT_TIMEOUT_SECONDS" ]; then
    for name in "${in_progress[@]}"; do
      echo "::error::rollout of $name$suffix did not complete in $ROLLOUT_TIMEOUT_SECONDS s; see the service events" >&2
    done
    exit 1
  fi
  sleep "$POLL_SECONDS"
  waited=$((waited + POLL_SECONDS))
  pending=("${in_progress[@]}")
done
echo "services stable on the new revisions"

aws ssm put-parameter --name "/erplora/$ENVIRONMENT/$PROJECT/image_tag" --value "$IMAGE_TAG" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded $IMAGE_TAG in /erplora/$ENVIRONMENT/$PROJECT/image_tag"
