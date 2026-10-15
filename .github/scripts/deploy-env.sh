#!/usr/bin/env bash
# Picks the environment a deploy or rollback run goes to (plan 2026-10-14-entorno-pre): a run of main
# goes to prod, a run of pre goes to pre, and nothing else deploys. A manual run must name the
# environment of its branch, and releases are prod's (pre deploys the branch's head only). Each
# environment has its own deploy role (gha-deploy-<project> trusts main, gha-deploy-<project>-pre
# trusts pre), its own ECR repository and its own host for /readyz; a missing role variable fails
# instead of falling back to the other environment's.
#
# Writes to $GITHUB_OUTPUT: environment (prod|pre), ecr_repository (erplora/<project>[-pre]),
# readyz_host and role_arn.
#
# Env: PROJECT (hub|saas), GITHUB_REF, GITHUB_EVENT_NAME, GITHUB_OUTPUT, INPUT_ENVIRONMENT (the
#      manual run's input), INPUT_RELEASE (the manual run's release, deploy only), AWS_DEPLOY_ROLE_ARN
#      (prod), AWS_DEPLOY_ROLE_ARN_PRE (pre).
set -euo pipefail

fail() {
  echo "::error::$1" >&2
  exit 1
}

if [ -z "${GITHUB_OUTPUT:-}" ]; then
  fail "GITHUB_OUTPUT is required"
fi
case "${PROJECT:-}" in
  hub | saas) ;;
  *) fail "PROJECT must be hub or saas, not '${PROJECT:-}'" ;;
esac

ref="${GITHUB_REF:-}"
case "$ref" in
  refs/heads/main) environment=prod ;;
  refs/heads/pre) environment=pre ;;
  *) fail "deploys run only from main (prod) or pre (pre), not '$ref'" ;;
esac

requested="${INPUT_ENVIRONMENT:-}"
if [ "${GITHUB_EVENT_NAME:-}" = workflow_dispatch ] || [ -n "$requested" ]; then
  if [ "$requested" != "$environment" ]; then
    fail "the run asks for environment '$requested' on $ref, which deploys to $environment"
  fi
fi

if [ -n "${INPUT_RELEASE:-}" ] && [ "$environment" != prod ]; then
  fail "a release is redeployed to prod only, never to $environment (deploy the pre branch instead)"
fi

if [ "$environment" = prod ]; then
  role_variable=AWS_DEPLOY_ROLE_ARN
  ecr_repository="erplora/$PROJECT"
  domain=erplora.com
else
  role_variable=AWS_DEPLOY_ROLE_ARN_PRE
  ecr_repository="erplora/$PROJECT-pre"
  domain=pre.erplora.com
fi
role_arn="${!role_variable:-}"
if [ -z "$role_arn" ]; then
  fail "$role_variable is empty: the $environment deploy role of $PROJECT (aws-next README)"
fi
if [ "$PROJECT" = hub ]; then
  readyz_host="hubs.$domain"
else
  readyz_host="$domain"
fi

{
  echo "environment=$environment"
  echo "ecr_repository=$ecr_repository"
  echo "readyz_host=$readyz_host"
  echo "role_arn=$role_arn"
} >> "$GITHUB_OUTPUT"
echo "deploying $PROJECT to $environment ($readyz_host) from $ref"
