#!/usr/bin/env bash
# Tests of the workflows' shape (deploy.yml, test.yml, ci.yml, rollback.yml, e2e.yml, nightly.yml):
# one push run of a branch at a time, and once its environment is known, its tests and image build
# side by side; a rollback waits only for a deploy; every push runs the e2e the branch touches, and
# every night all of them run on main (saas#296).
#   bash .github/scripts/workflows.test.sh
# Needs python3 with PyYAML (preinstalled on GitHub's ubuntu runners and on macOS).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"

python3 - "$here/../workflows" <<'PYEOF'
import pathlib
import sys

import yaml

folder = pathlib.Path(sys.argv[1])
deploy, test, ci, rollback, e2e, nightly = (
    yaml.safe_load((folder / f"{name}.yml").read_text())
    for name in ("deploy", "test", "ci", "rollback", "e2e", "nightly")
)
failures = 0


def check(name, ok):
    global failures
    print(("ok   - " if ok else "FAIL - ") + name)
    failures += not ok


def needs(job):
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


def steps(job):
    return job.get("steps", [])


def runs(job):
    return "\n".join(str(step.get("run", "")) for step in steps(job))


def index_of(job, needle):
    """The index of the first step whose `run` or `uses` contains needle, or None."""
    for index, step in enumerate(steps(job)):
        if needle in str(step.get("run", "")) or needle in str(step.get("uses", "")):
            return index
    return None


def before(job, first, second):
    a, b = index_of(job, first), index_of(job, second)
    return a is not None and b is not None and a < b


GROUP = "deploy-${{ github.repository }}-${{ github.ref_name }}"
# The push runs of a branch; a manual run (a release redeploy) is a group of its own.
PUSHES = "${{ github.event_name == 'push' && format('deploy-push-{0}-{1}', github.repository, github.ref_name) || github.run_id }}"
jobs = deploy.get("jobs", {})
environment, build, deploy_job = jobs.get("environment", {}), jobs.get("build", {}), jobs.get("deploy", {})
deploy_if, build_if = str(deploy_job.get("if", "")), str(build.get("if", ""))

# --- deploy.yml: one push run of a branch at a time; a rollback waits only for a deploy ---------
# Compared whole: `queue: max` would keep every push waiting, and cancelling would cut a deploy halfway.
check("a push run waits for the one before it of its branch, and a newer push replaces the one waiting",
      deploy.get("concurrency") == {"group": PUSHES, "cancel-in-progress": False})
check("only the deploy job holds a lock", [name for name, job in jobs.items() if "concurrency" in job] == ["deploy"])
check("the deploy job holds the deploy lock of its branch and never cancels a deploy in progress",
      deploy_job.get("concurrency") == {"group": GROUP, "cancel-in-progress": False})
check("rollback.yml shares the deploy lock", (rollback.get("concurrency") or {}).get("group") == GROUP)
rollback_confirm = (((rollback.get(True) or {}).get("workflow_dispatch") or {}).get("inputs") or {}).get("confirm_protected") or {}
check("a rollback may confirm the protected settings it changes, empty by default",
      rollback_confirm.get("type") == "string" and rollback_confirm.get("required") is False
      and rollback_confirm.get("default") == "")
ecs_rollback_env = next((step.get("env") or {} for step in steps((rollback.get("jobs") or {}).get("rollback") or {})
                         if step.get("run") == "python3 .github/scripts/ecs_rollback.py"), {})
check("the runner's python3 runs ecs_rollback.py, which gets that confirmation as CONFIRM_PROTECTED",
      ecs_rollback_env.get("CONFIRM_PROTECTED") == "${{ inputs.confirm_protected }}")

# --- deploy.yml: the environment first, then tests and image build side by side -----------------
check("deploy.yml has the jobs environment, test, build and deploy",
      {"environment", "test", "build", "deploy"} <= set(jobs))
check("environment waits for nothing", not needs(environment))
check("environment picks the branch's environment", "deploy-env.sh" in runs(environment))
check("test runs test.yml", jobs.get("test", {}).get("uses") == "./.github/workflows/test.yml")
check("test and build wait for the environment only",
      needs(jobs.get("test", {})) == ["environment"] and needs(build) == ["environment"])
check("build does not wait for test", "test" not in needs(build))
check("deploy needs environment, test and build", {"environment", "test", "build"} <= set(needs(deploy_job)))
check("deploy requires the environment to succeed", "needs.environment.result == 'success'" in deploy_if)
check("deploy requires test to succeed", "needs.test.result == 'success'" in deploy_if)
check("deploy requires build to succeed", "needs.build.result == 'success'" in deploy_if)
check("a release redeploy goes on with test and build skipped",
      "inputs.release != ''" in deploy_if and "needs.build.result == 'skipped'" in deploy_if)
check("a release redeploy builds nothing", "inputs.release == ''" in build_if)
check("the deploy job builds nothing",
      "buildx" not in runs(deploy_job) and index_of(deploy_job, "build-push-action") is None)
check("build caches its layers in GitHub's cache",
      any("type=gha" in str((step.get("with") or {}).get("cache-from", ""))
          and "type=gha,mode=max" in str((step.get("with") or {}).get("cache-to", ""))
          for step in steps(build) if "build-push-action" in str(step.get("uses", ""))))
check("build tests the image before it pushes it", before(build, "docker/image.test.sh", "docker push"))
check("the deploy never moves the environment back to an older commit",
      before(deploy_job, "deploy-order.sh", "ecs_deploy.py"))
confirm_input = (((deploy.get(True) or {}).get("workflow_dispatch") or {}).get("inputs") or {}).get("confirm_protected") or {}
check("a manual run may confirm the protected settings it changes, empty by default",
      confirm_input.get("type") == "string" and confirm_input.get("required") is False and confirm_input.get("default") == "")
ecs_deploy_env = next((step.get("env") or {} for step in steps(deploy_job) if step.get("run") == "python3 .github/scripts/ecs_deploy.py"), {})
check("the runner's python3 runs ecs_deploy.py, which gets that confirmation as CONFIRM_PROTECTED",
      ecs_deploy_env.get("CONFIRM_PROTECTED") == "${{ inputs.confirm_protected }}")
deploy_checkout = next((step.get("with") or {} for step in steps(deploy_job) if "actions/checkout" in str(step.get("uses", ""))), {})
check("the deploy checks out the whole history: it reads deploy/app-env.json of the commit it deploys",
      deploy_checkout.get("fetch-depth") == 0)
check("the workflow only reads", deploy.get("permissions") == {"contents": "read"})
check("only build and deploy get an OIDC token",
      sorted(name for name, job in jobs.items() if (job.get("permissions") or {}).get("id-token") == "write")
      == ["build", "deploy"])

# --- test.yml: four independent jobs behind the required check "test / test" -------------------
tjobs = test.get("jobs", {})
TEST_JOBS = ("python", "frontend", "scripts", "e2e")
check("test.yml has the jobs python, frontend, scripts, e2e and test",
      {*TEST_JOBS, "test"} <= set(tjobs))
check("python, frontend, scripts and e2e wait for nothing",
      all(not needs(tjobs.get(name, {})) for name in TEST_JOBS))
check("test (the required check) needs the four jobs",
      set(needs(tjobs.get("test", {}))) == set(TEST_JOBS))
results = str(next((step.get("env") or {} for step in steps(tjobs.get("test", {})) if "RESULTS" in (step.get("env") or {})), {}).get("RESULTS"))
check("test looks at the result of each of the four jobs",
      all(f"{name}=${{{{ needs.{name}.result }}}}" in results for name in TEST_JOBS))
check("test reports a red or skipped job, not a cancelled run", str(tjobs.get("test", {}).get("if", "")) == "${{ !cancelled() }}")
python_runs, frontend_runs, scripts_runs = (runs(tjobs.get(name, {})) for name in ("python", "frontend", "scripts"))
check("python runs pytest over a Postgres service",
      "pytest" in python_runs and "postgres" in (tjobs.get("python", {}).get("services") or {}))
check("pytest runs in parallel (pytest-xdist)", "pytest" in python_runs and " -n " in python_runs)
python_checkout = next((step.get("with") or {} for step in steps(tjobs.get("python", {}))
                        if "actions/checkout" in str(step.get("uses", ""))), {})
check("python checks out the whole history (the size test compares .file-size-allow with main's)",
      python_checkout.get("fetch-depth") == 0)
check("frontend runs lint, typecheck, Vitest and the build",
      all(f"pnpm {task}" in frontend_runs for task in ("lint", "typecheck", "test", "build")))
check("scripts runs actionlint, shellcheck and the script tests",
      all(needle in scripts_runs for needle in ("actionlint", "shellcheck", ".test.sh")))
check("scripts runs the tests of the Python scripts with the runner's python3, as the deploy does",
      "python3 -m unittest discover -s .github/scripts -p '*_test.py'" in scripts_runs)
check("e2e runs e2e.yml on the specs the branch changes (and the doors' spec)",
      tjobs.get("e2e", {}).get("uses") == "./.github/workflows/e2e.yml"
      and (tjobs.get("e2e", {}).get("with") or {}).get("specs") == "changed")

# --- e2e.yml: the e2e on a stack of the runner's own, for test.yml and nightly.yml --------------
e2e_on = e2e.get(True) or {}
check("e2e.yml is only called, never triggered on its own", set(e2e_on) == {"workflow_call"})
e2e_input = ((e2e_on.get("workflow_call") or {}).get("inputs") or {}).get("specs") or {}
check("e2e.yml asks which specs to run", e2e_input.get("required") is True and e2e_input.get("type") == "string")
check("e2e.yml only reads", e2e.get("permissions") == {"contents": "read"})
ejobs = e2e.get("jobs", {})
check("e2e.yml has the jobs pick and e2e", list(ejobs) == ["pick", "e2e"])
ejob, pick = ejobs.get("e2e", {}), ejobs.get("pick", {})
ejob_runs = runs(ejob)
check("e2e runs over a Postgres service", "postgres" in (ejob.get("services") or {}))
checkout = next((step.get("with") or {} for step in steps(ejob) if "actions/checkout" in str(step.get("uses", ""))), {})
check("e2e clones the submodules (the panel's Vite needs packages/ui)", checkout.get("submodules") == "recursive")
check("e2e checks out the whole history (the specs a branch changes since main)", checkout.get("fetch-depth") == 0)
check("e2e has its .env and its database migrated before the specs",
      before(ejob, "cp .env.example .env", "manage.py migrate") and before(ejob, "manage.py migrate", "pnpm e2e:ci"))
check("e2e builds the SPA before the specs (the public project serves the build)", before(ejob, "pnpm build", "pnpm e2e:ci"))
check("e2e renders the system's font with Arial's metrics (Liberation Sans), as a phone, before the specs",
      before(ejob, "Liberation Sans", "pnpm e2e:ci") and "fc-match" in ejob_runs)
run_step = next((step for step in steps(ejob) if "pnpm e2e:ci" in str(step.get("run", ""))), {})
check("e2e passes the input on to the step that runs the specs",
      (run_step.get("env") or {}).get("SPECS") == "${{ inputs.specs }}")
check("e2e picks the changed specs with e2e-specs.sh against main, and every spec with `all`",
      "e2e-specs.sh origin/main" in str(run_step.get("run", "")) and '[ "$SPECS" != all ]' in str(run_step.get("run", "")))
check("e2e writes a JSON report beside the list",
      "--reporter=list,json" in str(run_step.get("run", ""))
      and "PLAYWRIGHT_JSON_OUTPUT_FILE" in (run_step.get("env") or {}))
uploads = [step for step in steps(ejob) if "actions/upload-artifact" in str(step.get("uses", ""))]
check("e2e keeps the JSON report and the traces of a red run",
      {(step.get("with") or {}).get("name") for step in uploads} == {"e2e-report", "e2e-test-results"}
      and all(str(step.get("if", "")) == "failure()" for step in uploads))
check("e2e uploads the traces from under tests/e2e/.artifacts/, a hidden folder, saying so",
      any((step.get("with") or {}).get("name") == "e2e-test-results"
          and (step.get("with") or {}).get("include-hidden-files") is True for step in uploads))

# A job's timeout is fixed before it starts: pick counts the specs in a job before e2e.
check("e2e waits for pick", needs(ejob) == ["pick"])
check("pick only reads", pick.get("permissions") == {"contents": "read"})
pick_checkout = next((step.get("with") or {} for step in steps(pick)
                      if "actions/checkout" in str(step.get("uses", ""))), {})
check("pick checks out the whole history (the specs a branch changes since main)", pick_checkout.get("fetch-depth") == 0)
count_step = next((step for step in steps(pick) if "e2e-specs.sh" in str(step.get("run", ""))), {})
check("pick tells whether the branch picks many specs with e2e-specs.sh --many against main",
      'e2e-specs.sh --many origin/main >> "$GITHUB_OUTPUT"' in str(count_step.get("run", ""))
      and (pick.get("outputs") or {}).get("many") == f"${{{{ steps.{count_step.get('id')}.outputs.many }}}}")
check("a branch that picks many specs gets the timeout of every spec; a few specs keep the short one",
      ejob.get("timeout-minutes") == "${{ (inputs.specs == 'all' || needs.pick.outputs.many == 'true') && 120 || 30 }}")

# --- nightly.yml: every spec, every night on main, with an issue for what comes out red ---------
nightly_on = nightly.get(True) or {}
check("nightly.yml runs on a schedule and by hand only, never on a push or a PR",
      set(nightly_on) == {"schedule", "workflow_dispatch"})
check("nightly.yml has a cron", any("cron" in entry for entry in nightly_on.get("schedule") or []))
check("nightly.yml only reads, at the workflow's level", nightly.get("permissions") == {"contents": "read"})
check("two nightlies never run at once (a dispatch near the cron would write the issue twice); none is cancelled",
      (nightly.get("concurrency") or {}).get("group") == "nightly-${{ github.repository }}"
      and (nightly.get("concurrency") or {}).get("cancel-in-progress") is False)
njobs = nightly.get("jobs", {})
check("nightly.yml has the jobs e2e and report", set(njobs) == {"e2e", "report"})
check("nightly's e2e runs e2e.yml on every spec",
      njobs.get("e2e", {}).get("uses") == "./.github/workflows/e2e.yml"
      and (njobs.get("e2e", {}).get("with") or {}).get("specs") == "all")
report = njobs.get("report", {})
check("report waits for e2e and runs whatever its result, unless the run was cancelled by hand",
      needs(report) == ["e2e"] and str(report.get("if", "")) == "${{ !cancelled() }}")
check("only report may write issues",
      [name for name, job in njobs.items() if (job.get("permissions") or {}).get("issues") == "write"] == ["report"]
      and report.get("permissions") == {"contents": "read", "issues": "write"})
check("report downloads the JSON report before e2e_report.py reads it",
      before(report, "actions/download-artifact", "e2e_report.py"))
report_step = next((step for step in steps(report) if "e2e_report.py" in str(step.get("run", ""))), {})
check("report runs e2e_report.py with the runner's python3",
      report_step.get("run") == "python3 .github/scripts/e2e_report.py")
report_env = report_step.get("env") or {}
check("e2e_report.py gets e2e's result and the run",
      report_env.get("RESULT") == "${{ needs.e2e.result }}" and "RUN_URL" in report_env and "GH_TOKEN" in report_env)
check("e2e_report.py only writes issues for main",
      report_env.get("PUBLISH") == "${{ github.ref == 'refs/heads/main' }}")

setup_uv = [step for job in [*tjobs.values(), *ejobs.values()] for step in steps(job)
            if "astral-sh/setup-uv" in str(step.get("uses", ""))]
check("setup-uv is used", bool(setup_uv))
check("setup-uv caches by uv.lock",
      bool(setup_uv) and all(str((step.get("with") or {}).get("enable-cache")).lower() == "true"
                             and (step.get("with") or {}).get("cache-dependency-glob") == "uv.lock"
                             for step in setup_uv))

# --- ci.yml: a newer push supersedes the run of the older one -----------------------------------
check("ci.yml runs test.yml", (ci.get("jobs", {}).get("test") or {}).get("uses") == "./.github/workflows/test.yml")
ci_lock = ci.get("concurrency") or {}
check("ci.yml cancels the run of an older push to the same branch",
      ci_lock.get("group") == "ci-${{ github.repository }}-${{ github.ref_name }}"
      and ci_lock.get("cancel-in-progress") is True)

print()
if failures:
    print(f"{failures} test(s) failed")
    sys.exit(1)
print("all tests passed")
PYEOF
