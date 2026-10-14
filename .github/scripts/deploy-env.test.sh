#!/usr/bin/env bash
# Tests for deploy-env.sh: which environment a deploy or rollback run goes to (plan
# 2026-10-14-entorno-pre, §2.3 H-4): main -> prod, pre -> pre, nothing else.
#   bash .github/scripts/deploy-env.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
prod_role="arn:aws:iam::123456789012:role/gha-deploy-saas"
pre_role="arn:aws:iam::123456789012:role/gha-deploy-saas-pre"

# run_env [VAR=value...]: a push of the saas to main with both role variables set; the arguments
# override the environment.
run_env() {
  work="$(mktemp -d)"
  out="$work/github_output"
  : > "$out"
  env -i PATH="$PATH" HOME="$HOME" GITHUB_OUTPUT="$out" PROJECT=saas GITHUB_REF=refs/heads/main \
    GITHUB_EVENT_NAME=push INPUT_ENVIRONMENT="" INPUT_RELEASE="" \
    AWS_DEPLOY_ROLE_ARN="$prod_role" AWS_DEPLOY_ROLE_ARN_PRE="$pre_role" "$@" \
    bash "$here/deploy-env.sh" > "$work/out.log" 2>&1
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

# output <name>: the value deploy-env.sh wrote for <name> in GITHUB_OUTPUT.
output() { grep "^$1=" "$out" | cut -d= -f2-; }
outputs_are() {
  [ "$(output environment)" = "$1" ] && [ "$(output ecr_repository)" = "$2" ] &&
    [ "$(output readyz_host)" = "$3" ] && [ "$(output role_arn)" = "$4" ]
}

# --- the two branches -----------------------------------------------------------
run_env && status=0 || status=$?
check "a push to main deploys to prod" \
  '[ "$status" -eq 0 ] && outputs_are prod erplora/saas erplora.com "$prod_role"'
run_env GITHUB_REF=refs/heads/pre && status=0 || status=$?
check "a push to pre deploys to pre, with its own ECR repository, host and role" \
  '[ "$status" -eq 0 ] && outputs_are pre erplora/saas-pre pre.erplora.com "$pre_role"'
run_env PROJECT=hub AWS_DEPLOY_ROLE_ARN=arn:hub GITHUB_REF=refs/heads/main && status=0 || status=$?
check "the hub's prod is hubs.erplora.com" '[ "$status" -eq 0 ] && outputs_are prod erplora/hub hubs.erplora.com arn:hub'
run_env PROJECT=hub AWS_DEPLOY_ROLE_ARN_PRE=arn:hub-pre GITHUB_REF=refs/heads/pre && status=0 || status=$?
check "the hub's pre is hubs.pre.erplora.com" \
  '[ "$status" -eq 0 ] && outputs_are pre erplora/hub-pre hubs.pre.erplora.com arn:hub-pre'
run_env GITHUB_REF=refs/heads/main && status=0 || status=$?
check "each output is written once" '[ "$(grep -c "" "$out")" -eq 4 ]'

for ref in refs/heads/feature refs/heads/main-old refs/heads/pre/x refs/tags/saas-v2026.10.14.1 ""; do
  run_env GITHUB_REF="$ref" && status=0 || status=$?
  check "'$ref' deploys nowhere and writes no output" \
    '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*main.*pre" "$work/out.log"'
done

# --- a manual run must name the environment of its branch --------------------------
run_env GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=prod && status=0 || status=$?
check "a manual run of main for prod deploys to prod" '[ "$status" -eq 0 ] && [ "$(output environment)" = prod ]'
run_env GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=pre && status=0 || status=$?
check "a manual run of pre for pre deploys to pre" '[ "$status" -eq 0 ] && [ "$(output environment)" = pre ]'
run_env GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=pre && status=0 || status=$?
check "a manual run of main for pre is refused" \
  '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*pre.*refs/heads/main" "$work/out.log"'
run_env GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=prod && status=0 || status=$?
check "a manual run of pre for prod is refused" \
  '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*prod.*refs/heads/pre" "$work/out.log"'
run_env GITHUB_EVENT_NAME=workflow_dispatch && status=0 || status=$?
check "a manual run without an environment is refused" '[ "$status" -ne 0 ] && [ ! -s "$out" ]'

# --- releases are prod's ------------------------------------------------------------
run_env GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=prod INPUT_RELEASE=saas-v2026.10.14.1 && status=0 || status=$?
check "a release is redeployed to prod" '[ "$status" -eq 0 ] && [ "$(output environment)" = prod ]'
run_env GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=pre \
  INPUT_RELEASE=saas-v2026.10.14.1 && status=0 || status=$?
check "a release is never deployed to pre" \
  '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*release" "$work/out.log"'

# --- the deploy role of the environment, never the other's ----------------------------
run_env GITHUB_REF=refs/heads/pre AWS_DEPLOY_ROLE_ARN_PRE="" && status=0 || status=$?
check "pre without AWS_DEPLOY_ROLE_ARN_PRE fails naming it, and never takes prod's role" \
  '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*AWS_DEPLOY_ROLE_ARN_PRE" "$work/out.log"'
run_env AWS_DEPLOY_ROLE_ARN="" && status=0 || status=$?
check "prod without AWS_DEPLOY_ROLE_ARN fails naming it, and never takes pre's role" \
  '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*AWS_DEPLOY_ROLE_ARN " "$work/out.log"'

# --- usage ---------------------------------------------------------------------------
run_env PROJECT=worker && status=0 || status=$?
check "an unknown project fails" '[ "$status" -ne 0 ] && [ ! -s "$out" ] && grep -q "::error::.*PROJECT" "$work/out.log"'
run_env GITHUB_OUTPUT="" && status=0 || status=$?
check "without GITHUB_OUTPUT it fails" '[ "$status" -ne 0 ] && grep -q "::error::.*GITHUB_OUTPUT" "$work/out.log"'

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
