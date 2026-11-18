#!/usr/bin/env bash
# Puts the saas's services of one environment (prod: saas and saas-worker in cluster erplora-prod; pre: saas-pre
# and saas-worker-pre in erplora-pre) back on the ACTIVE revision right before the one each PRIMARY deployment runs.
# saas-worker never blocks saas: while its family does not exist, without an earlier revision or with one of another
# tag than saas's (an image without run_worker would crash-loop), it stays as it is, with a ::warning::; any other
# error looking for it, or a revision of another environment or image, still fails:
#   1. finds each previous revision; nothing changes unless saas has one, each is a revision of this environment
#      (the tag Environment=<ENVIRONMENT> and the roles erplora-<ENVIRONMENT>-*: another environment's deploy role
#      could have registered it) on this environment's image (erplora/saas or erplora/saas-pre), and they all run
#      the same tag;
#   2. checks the settings those revisions run with, with the deploy's rules (app_env_rollback.py check): in prod a
#      protected setting that changes needs CONFIRM_PROTECTED, and the real charge the Hub filing in production;
#   3. moves the services, waits until they are stable and polls each PRIMARY deployment until it is the previous
#      revision, COMPLETED (ECS marks it so once the old tasks drain from the ALB). A FAILED rollout or another
#      revision as PRIMARY (the circuit breaker put back the one it ran) fails at once, and so does a rollout that
#      outlasts ROLLOUT_TIMEOUT_SECONDS;
#   4. only then records their settings in /erplora/<ENVIRONMENT>/saas/app_env and the tag in .../image_tag
#      (ERPlora/aws README), so a failed rollback leaves both as they were.
# Migrations are NOT undone: the previous code must work on the current schema (expand/contract). saas-cron (the
# Scheduler runs its latest revision) and saas-migrate keep the newer image and their settings in app_env until the
# next deploy; to go back everywhere, deploy the previous release.
#
# Env: CONFIRM (exactly ROLLBACK), AWS_REGION, ENVIRONMENT (prod|pre); optional CLUSTER (erplora-<ENVIRONMENT>),
#      POLL_SECONDS (15), ROLLOUT_TIMEOUT_SECONDS (600), CONFIRM_PROTECTED (VAR=value of each protected setting a
#      prod rollback changes).
set -euo pipefail

if [ "${CONFIRM:-}" != ROLLBACK ]; then
  echo "::error::CONFIRM must be exactly ROLLBACK, not '${CONFIRM:-}'; nothing was changed" >&2
  exit 1
fi
if [ -z "${AWS_REGION:-}" ]; then
  echo "::error::AWS_REGION is required" >&2
  exit 1
fi
ENVIRONMENT="${ENVIRONMENT:-}"
if [ "$ENVIRONMENT" != prod ] && [ "$ENVIRONMENT" != pre ]; then
  echo "::error::ENVIRONMENT must be prod or pre, not '$ENVIRONMENT'; nothing was changed" >&2
  exit 1
fi
CLUSTER="${CLUSTER:-erplora-$ENVIRONMENT}"
POLL_SECONDS="${POLL_SECONDS:-15}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-600}"
for var in POLL_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
    echo "::error::$var must be a number of seconds, not '${!var}'; nothing was changed" >&2
    exit 1
  fi
done

# This repo deploys the saas; the hub repo keeps its own copy of this script.
PROJECT=saas
app_env="$(dirname "$0")/app_env_rollback.py"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
# Families that run as a service: the service of family <name> is <name><suffix>, its container <name>.
families=(saas)
suffix=""
if [ "$ENVIRONMENT" = pre ]; then
  suffix=-pre
fi
# Families that may not exist yet; a family prefix also lists longer ones: only <name>'s own family counts.
not_yet=(saas-worker)
# The families of not_yet that exist: they never block the rollback of saas.
optional=()
for name in "${not_yet[@]}"; do
  family="erplora-$ENVIRONMENT-$name"
  if ! arns="$(aws ecs list-task-definitions --family-prefix "$family" --status ACTIVE \
    --region "$AWS_REGION" --query taskDefinitionArns --output text)"; then
    echo "::error::could not look for $family; nothing was changed" >&2
    exit 1
  fi
  read -ra listed <<< "$arns"
  found=0
  for arn in "${listed[@]}"; do
    if [[ "${arn%:*}" == */"$family" ]]; then found=1; fi
  done
  if [ "$found" -eq 1 ]; then
    families+=("$name")
    optional+=("$name")
  else
    echo "::warning::$family does not exist yet: skipped"
  fi
done
repository="erplora/$PROJECT$suffix"
services=()
for name in "${families[@]}"; do
  services+=("$name$suffix")
done

echo "::warning::rolling back ${services[*]} ($ENVIRONMENT) to their previous revisions; migrations are not undone"

# is_optional <name>: whether <name> may stay as it is (it never blocks the rollback of saas).
is_optional() {
  local o
  for o in "${optional[@]}"; do
    if [ "$o" = "$1" ]; then return 0; fi
  done
  return 1
}

# primary <service>: "<task definition ARN> <rollout state>" of its PRIMARY deployment.
primary() {
  aws ecs describe-services --cluster "$CLUSTER" --services "$1" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text
}

moving=()
targets=()
tags=()
names=()
for i in "${!services[@]}"; do
  service="${services[i]}"
  name="${families[i]}"
  family="erplora-$ENVIRONMENT-$name"
  out="$(primary "$service")"
  read -r current _ <<< "$out"
  if ! [[ "$current" =~ :task-definition/$family:[0-9]+$ ]]; then
    echo "::error::$service has no PRIMARY deployment of $family (got '$current'); nothing was changed" >&2
    exit 1
  fi

  # Of its own family only (the prefix also lists erplora-prod-saas-migrate), the highest below the current one.
  arns="$(aws ecs list-task-definitions --family-prefix "$family" --status ACTIVE --sort DESC \
    --region "$AWS_REGION" --query taskDefinitionArns --output text)"
  read -ra listed <<< "$arns"
  previous="" best=0
  for arn in "${listed[@]}"; do
    revision="${arn##*:}"
    if [ "${arn%:*}" = "${current%:*}" ] && [ "$revision" -lt "${current##*:}" ] && [ "$revision" -gt "$best" ]; then
      previous="$arn" best="$revision"
    fi
  done
  if [ -z "$previous" ]; then
    if is_optional "$name"; then
      echo "::warning::$service runs $current and $family has no earlier ACTIVE revision: it stays as it is"
      continue
    fi
    echo "::error::$service runs $current and $family has no earlier ACTIVE revision; nothing was changed" >&2
    exit 1
  fi

  definition="$(aws ecs describe-task-definition --task-definition "$previous" --include TAGS \
    --region "$AWS_REGION" --output json)"
  if ! jq -e --arg environment "$ENVIRONMENT" '
      any(.tags[]?; .key == "Environment" and .value == $environment)
      and ([.taskDefinition.taskRoleArn, .taskDefinition.executionRoleArn]
           | all(type == "string" and test("^arn:aws[a-z-]*:iam::[0-9]{12}:role/erplora-\($environment)-")))' \
    <<< "$definition" > /dev/null; then
    echo "::error::$previous is not a $ENVIRONMENT revision (it needs the tag Environment=$ENVIRONMENT and the roles erplora-$ENVIRONMENT-*); nothing was changed" >&2
    exit 1
  fi
  image="$(jq -r --arg name "$name" '[.taskDefinition.containerDefinitions[] | select(.name == $name) | .image][0] // ""' \
    <<< "$definition")"
  if [[ "$image" != */$repository:* ]]; then
    echo "::error::$previous does not run an $repository image ($image); nothing was changed" >&2
    exit 1
  fi
  moving+=("$service")
  targets+=("$previous")
  tags+=("${image##*:}")
  names+=("$name")
done

# saas comes first and is never skipped: the others go back only to its tag.
kept_services=()
kept_targets=()
for i in "${!moving[@]}"; do
  if [ "${tags[i]}" != "${tags[0]}" ]; then
    if is_optional "${names[i]}"; then
      echo "::warning::${moving[i]}: its previous revision ${targets[i]} runs ${tags[i]}, not ${tags[0]} as ${moving[0]}'s: it stays as it is"
      continue
    fi
    echo "::error::the previous revisions run different tags (${tags[*]}); nothing was changed" >&2
    exit 1
  fi
  kept_services+=("${moving[i]}")
  kept_targets+=("${targets[i]}")
done
services=("${kept_services[@]}")
targets=("${kept_targets[@]}")

python3 "$app_env" check --workdir "$workdir" --environment "$ENVIRONMENT" --region "$AWS_REGION" "${targets[@]}"

for i in "${!services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "${services[i]}" \
    --task-definition "${targets[i]}" --region "$AWS_REGION" > /dev/null
  echo "rolling back ${services[i]} to ${targets[i]}"
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${services[@]}"

# services-stable can return while a PRIMARY deployment is IN_PROGRESS: poll those not COMPLETED, on one clock.
pending=("${!services[@]}")
waited=0
while :; do
  failed=0
  in_progress=()
  for i in "${pending[@]}"; do
    out="$(primary "${services[i]}")"
    read -r task_definition state <<< "$out"
    if [ "$task_definition" != "${targets[i]}" ] || [ "$state" = FAILED ]; then
      echo "::error::${services[i]} runs $task_definition ($state), not ${targets[i]}; rolled back by the circuit breaker? See the service events" >&2
      failed=1
    elif [ "$state" != COMPLETED ]; then
      in_progress+=("$i")
    fi
  done
  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
  if [ "${#in_progress[@]}" -eq 0 ]; then
    break
  fi
  if [ "$waited" -ge "$ROLLOUT_TIMEOUT_SECONDS" ]; then
    for i in "${in_progress[@]}"; do
      echo "::error::rollout of ${services[i]} did not complete in $ROLLOUT_TIMEOUT_SECONDS s; see the service events" >&2
    done
    exit 1
  fi
  sleep "$POLL_SECONDS"
  waited=$((waited + POLL_SECONDS))
  pending=("${in_progress[@]}")
done
echo "services stable on the previous revisions"

python3 "$app_env" record --workdir "$workdir" --environment "$ENVIRONMENT" --region "$AWS_REGION"
aws ssm put-parameter --name "/erplora/$ENVIRONMENT/$PROJECT/image_tag" --value "${tags[0]}" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded ${tags[0]} in /erplora/$ENVIRONMENT/$PROJECT/image_tag"
