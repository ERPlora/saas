#!/usr/bin/env bash
# Deploys an image tag of the saas to one environment, in that environment's own ECS cluster
# (erplora-<ENVIRONMENT>; PLAN-AWS §6; plan 2026-10-14-entorno-pre), touching only that
# environment's saas task families and services:
#   prod: cluster erplora-prod, families erplora-prod-{saas,saas-migrate,saas-cron,saas-worker},
#         services saas and saas-worker, image erplora/saas;
#   pre:  cluster erplora-pre, families erplora-pre-{saas,saas-migrate,saas-worker} (no saas-cron),
#         services saas-pre and saas-worker-pre, image erplora/saas-pre; the containers keep the
#         short names (saas, saas-migrate, saas-worker).
#   saas-worker (saas#305: manage.py run_worker, the WhatsApp deliveries and the reconciliations)
#   is created by ERPlora/aws (aws#59) once an image with run_worker is out: while its family does
#   not exist the deploy goes on without it and says so (::warning::); any other error looking for
#   it or reading it fails the deploy as for the other families.
#   0. reads the latest ACTIVE revision of every family and refuses them all, registering nothing,
#      unless each one carries the tag Environment=<ENVIRONMENT> and the task and execution roles of
#      its environment (role/erplora-<ENVIRONMENT>-…): ecs:RegisterTaskDefinition takes no resource,
#      so another environment's deploy role could have left a revision in this family; and unless the
#      container of the saas image has the policies the saas refuses to start without outside DEBUG
#      (REQUIRED_ENV, config/settings.py; PLAN-SAAS §43): ERPlora/aws gives them, and a revision from
#      before that apply would register saas-cron's (the Scheduler's latest) and only fail at step 2;
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
# What every container of the saas image must be given in its environment (step 0).
REQUIRED_ENV='["CACHE_KEY_PREFIX", "STRIPE_EXPECTED_MODE"]'
migration=saas-migrate
# Families that run as a service; the service of family <name> is <name><suffix>.
services=(saas)
# Services that may not exist yet (saas-worker until aws#59 is applied): deployed once their
# family exists.
not_yet=(saas-worker)
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
# The migration runs like the saas service (same subnets, sg-app, public IP; sg-app reaches Aurora
# and Valkey, and nothing listens on 8000 in the migration), never like saas-worker (it may not exist).
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
  local missing
  missing="$(jq -r --arg project_image "$project_image" --argjson required "$REQUIRED_ENV" '
      [.taskDefinition.containerDefinitions[] | select((.image // "") | startswith($project_image))
       | [.environment[]?.name] as $names | $required[] | select(. as $n | $names | index($n) | not)]
      | unique | join(" ")' "$workdir/$name.base.json")"
  if [ -n "$missing" ]; then
    echo "::error::$prefix-$name has no $missing in the environment of its saas container (apply ERPlora/aws first); nothing was registered" >&2
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

# A family prefix also lists longer families: only a revision of <name>'s own family counts.
for name in "${not_yet[@]}"; do
  if ! arns="$(aws ecs list-task-definitions --family-prefix "$prefix-$name" --status ACTIVE \
    --region "$AWS_REGION" --query taskDefinitionArns --output text)"; then
    echo "::error::could not look for $prefix-$name; nothing was registered" >&2
    exit 1
  fi
  read -ra listed <<< "$arns"
  found=0
  for arn in "${listed[@]}"; do
    if [[ "${arn%:*}" == */"$prefix-$name" ]]; then found=1; fi
  done
  if [ "$found" -eq 1 ]; then
    families+=("$name")
    services+=("$name")
  else
    echo "::warning::$prefix-$name does not exist yet (aws#59 not applied): skipped"
  fi
done

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
