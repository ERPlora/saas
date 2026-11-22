"""Tests of ecs_rollback.py: the saas's services of one environment back on their previous revisions.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The rollback runs with a fake aws CLI first on the PATH that records every call, answers from fixtures and keeps each
service's PRIMARY revision as state (update-service moves it). Inside the rollback's process time.sleep only records
the pause (ecs_common_test.BOOT). Only the standard library.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from ecs_common_test import run_script

SCRIPT = Path(__file__).resolve().with_name("ecs_rollback.py")
REPO = Path(__file__).resolve().parents[2]
TD = "arn:aws:ecs:eu-south-2:123456789012:task-definition"
CLUSTER_SCOPED = re.compile(r"^ecs (describe-services|update-service|wait services-stable) ")
NOT_INHERITED = ("CLUSTER", "PROJECT", "POLL_SECONDS", "ROLLOUT_TIMEOUT_SECONDS", "CONFIRM_PROTECTED", "CONFIRM",
                 "ENVIRONMENT", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

# Imports only what each answer needs: the fake answers every aws call of every test, and Python starts slowly.
FAKE_AWS = r'''
import os
import sys

args = sys.argv[1:]
env = os.environ
fixtures, state = env["FIXTURES"], env["STATE"]
with open(env["CALLS_LOG"], "a", encoding="utf-8", errors="surrogateescape") as calls:
    calls.write(" ".join(args) + "\n")


def value(flag):
    return next((args[i + 1] for i in range(len(args) - 1) if args[i] == flag), "")


def path(folder, name):
    return os.path.join(folder, name)


def read(file, default=None):
    if default is not None and not os.path.isfile(file):
        return default
    with open(file, encoding="utf-8") as found:
        return found.read()


def write(file, text):
    with open(file, "w", encoding="utf-8") as written:
        written.write(text)


def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(254)


def nth(answers, n):
    answers = answers.split()
    return answers[min(n, len(answers) - 1)]


def describe_services():
    service = value("--services")
    if "FAKE_PRIMARY_ANSWER" in env:
        sys.stdout.buffer.write(os.environb[b"FAKE_PRIMARY_ANSWER"] + b"\n")
        return
    primary, rollout = read(path(state, f"primary-{service}")).strip(), "COMPLETED"
    if os.path.isfile(path(state, f"moved-{service}")):
        # After update-service, each read answers the next of FAKE_ROLLOUT_STATES and FAKE_PRIMARY_REVISIONS.
        n = int(read(path(state, f"reads-{service}"), "0"))
        write(path(state, f"reads-{service}"), str(n + 1))
        rollout = nth(env.get("FAKE_ROLLOUT_STATES") or "COMPLETED", n)
        if env.get("FAKE_PRIMARY_REVISIONS"):
            primary = f"{primary.rsplit(':', 1)[0]}:{nth(env['FAKE_PRIMARY_REVISIONS'], n)}"
    print(f"{primary}\t{rollout}")


def list_task_definitions():
    if env.get("FAKE_LIST_FAILURE"):
        refuse(f"An error occurred ({env['FAKE_LIST_FAILURE']}) when calling the ListTaskDefinitions operation")
    print(read(path(fixtures, f"list-{value('--family-prefix')}"), ""))


def describe_task_definition():
    import json
    arn = value("--task-definition")
    revision = arn.rsplit("/", 1)[-1]
    if os.path.isfile(path(fixtures, f"describe-{revision}")):
        sys.stdout.buffer.write(open(path(fixtures, f"describe-{revision}"), "rb").read())
        return
    family = revision.rsplit(":", 1)[0]
    environment = family.removeprefix("erplora-").split("-")[0]
    name = family.removeprefix(f"erplora-{environment}-")
    repository = ("erplora/saas" if name.startswith("saas") else "erplora/hub") + ("-pre" if environment == "pre" else "")
    image = json.loads(read(path(fixtures, "images.json"))).get(arn, f"reg.example/{repository}:tag-{arn.rsplit(':', 1)[-1]}")
    tag = json.loads(read(path(fixtures, "tags.json"))).get(arn, environment)
    role = "arn:aws:iam::123456789012:role/" + json.loads(read(path(fixtures, "roles.json"))).get(arn, family)
    hub = {"VERIFACTU_PRODUCTION_ENABLED": env.get("FAKE_HUB_VERIFACTU", "true")}
    in_force = json.loads(read(path(fixtures, f"app_env.{environment}.json")))
    settings = json.loads(read(path(fixtures, f"settings-{revision}"), "null")) or in_force.get(name) or hub
    print(json.dumps({
        "taskDefinition": {"taskRoleArn": f"{role}-task", "executionRoleArn": f"{role}-execution",
                           "containerDefinitions": [
                               {"name": "log-router", "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
                               {"name": name, "image": image,
                                "environment": [{"name": k, "value": v} for k, v in settings.items()]}]},
        "tags": [{"key": "Project", "value": "erplora"}] + ([] if tag == "none" else [{"key": "Environment", "value": tag}]),
    }, indent=2))


def update_service():
    service = value("--service")
    write(path(state, f"moved-{service}"), "")
    # The circuit breaker of FAKE_CIRCUIT_BREAKER's service puts its old revision back.
    if env.get("FAKE_CIRCUIT_BREAKER") != service:
        write(path(state, f"primary-{service}"), value("--task-definition"))


def get_parameter():
    if env.get("FAKE_APP_ENV_FAILURE"):
        refuse(f"An error occurred ({env['FAKE_APP_ENV_FAILURE']}) when calling the GetParameter operation")
    print(read(path(fixtures, f"app_env.{value('--name').removeprefix('/erplora/').split('/')[0]}.json")))


def put_parameter():
    if env.get("FAKE_PUT_FAILURE") and value("--name").endswith(f"/{env['FAKE_PUT_FAILURE']}"):
        refuse("An error occurred (AccessDeniedException) when calling the PutParameter operation")


COMMANDS = {
    "ecs describe-services": describe_services, "ecs list-task-definitions": list_task_definitions,
    "ecs describe-task-definition": describe_task_definition, "ecs update-service": update_service,
    "ssm get-parameter": get_parameter, "ssm put-parameter": put_parameter,
}
command = " ".join(args[:2])
if env.get("FAKE_FAILURE_ON") == command:
    refuse(f"An error occurred (Throttling) when calling {command}")
if env.get("FAKE_KILLED_ON") == command:
    os.kill(os.getpid(), 9)
COMMANDS.get(command, lambda: None)()
'''


class RollbackCase(unittest.TestCase):
    """A fresh fake AWS for each test. saas runs revision 12 in prod and saas-pre runs 12 in pre; the family prefix of
    saas also lists saas-migrate and saas-cron, and saas has a newer revision (13) than the one it runs, so the
    previous one is saas:10. The app image of a revision is reg.example/erplora/<saas|hub>[-pre]:tag-<revision>, its
    Environment tag its family's environment and its roles erplora-<environment>-<name>-{task,execution}, unless the
    test says otherwise; its app container runs its family's settings in the app_env in force, which holds the
    repository's deploy/app-env.json."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.fixtures, self.state = self.work / "fixtures", self.work / "state"
        for folder in (self.work / "bin", self.fixtures, self.state):
            folder.mkdir()
        self.primary("saas", f"{TD}/erplora-prod-saas:12")
        self.listed("erplora-prod-saas", "saas-migrate:14", "saas-migrate:11", "saas-cron:11", "saas:13", "saas:12",
                    "saas:10", "saas:9")
        # The hub's services live in the same cluster: this repo must never query nor move them.
        for name in ("hub", "worker"):
            self.primary(name, f"{TD}/erplora-prod-{name}:12")
            self.listed(f"erplora-prod-{name}", f"{name}:12", f"{name}:10")
        self.primary("saas-pre", f"{TD}/erplora-pre-saas:12")
        self.listed("erplora-pre-saas", "saas-migrate:11", "saas:12", "saas:10", environment="pre")
        for table in ("images", "tags", "roles"):
            (self.fixtures / f"{table}.json").write_text("{}")
        settings = json.loads((REPO / "deploy" / "app-env.json").read_text())
        for environment in ("prod", "pre"):
            (self.fixtures / f"app_env.{environment}.json").write_text(json.dumps(settings[environment]))
        aws = self.work / "bin" / "aws"
        aws.write_text(f"#!{sys.executable} -IS\n{FAKE_AWS}")
        aws.chmod(0o755)

    def primary(self, service: str, arn: str) -> None:
        (self.state / f"primary-{service}").write_text(arn)

    def listed(self, family: str, *revisions: str, environment: str = "prod") -> None:
        """What list-task-definitions answers for the prefix <family>: the ARNs of <revisions> (<name>:<n> of
        <environment>), each followed by a tab, as aws writes them."""
        text = "".join(f"{TD}/erplora-{environment}-{revision}\t" for revision in revisions)
        (self.fixtures / f"list-{family}").write_text(text)

    def given(self, table: str, arn: str, value: str) -> None:
        """Gives revision <arn> its own image, Environment tag ("none": none) or role prefix."""
        path = self.fixtures / f"{table}.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), arn: value}))

    def with_worker(self, environment: str = "prod", suffix: str = "") -> None:
        """saas-worker<suffix> runs erplora-<environment>-saas-worker:12 and has revision 10 before it."""
        self.primary(f"saas-worker{suffix}", f"{TD}/erplora-{environment}-saas-worker:12")
        self.listed(f"erplora-{environment}-saas-worker", "saas-worker:12", "saas-worker:10", environment=environment)

    def runs(self, environment: str, name: str, change) -> None:
        """Revision 10 of erplora-<environment>-<name> runs its family's settings in the app_env in force, changed in
        place by <change>."""
        settings = json.loads((self.fixtures / f"app_env.{environment}.json").read_text())[name]
        change(settings)
        (self.fixtures / f"settings-erplora-{environment}-{name}:10").write_text(json.dumps(settings))

    def in_force(self, environment: str) -> dict:
        return json.loads((self.fixtures / f"app_env.{environment}.json").read_text())

    def rollback(self, *unset: str, apart: bool = False, **env) -> int:
        """Rolls prod back with the fakes and CONFIRM=ROLLBACK; <env> overrides the environment and <unset> takes
        variables out of it. stdout and stderr land together in self.out, or apart in self.stdout and self.stderr.
        The logs start empty; the state goes on from the last rollback."""
        for log in ("calls.log", "sleep.log"):
            (self.work / log).write_text("")
        environ = {key: value for key, value in os.environ.items() if key not in NOT_INHERITED}
        environ.update(PATH=f"{self.work / 'bin'}:{os.environ['PATH']}", AWS_REGION="eu-south-2", CONFIRM="ROLLBACK",
                       ENVIRONMENT="prod", FIXTURES=str(self.fixtures), STATE=str(self.state),
                       CALLS_LOG=str(self.work / "calls.log"), SLEEP_LOG=str(self.work / "sleep.log"),
                       AWS_CONFIG_FILE=os.devnull, AWS_SHARED_CREDENTIALS_FILE=os.devnull)
        environ.update(env)
        for name in unset:
            environ.pop(name, None)
        done = run_script(SCRIPT, self.work, environ, apart)
        self.stdout, self.stderr = done.stdout, done.stderr
        self.out = done.stdout.decode("utf-8", "replace")
        self.status = done.returncode
        return done.returncode

    def calls(self) -> list[str]:
        return (self.work / "calls.log").read_text(errors="replace").splitlines()

    def lines(self, pattern: str) -> list[int]:
        return [n for n, call in enumerate(self.calls(), 1) if re.search(pattern, call)]

    def line_of(self, pattern: str) -> int:
        return self.lines(pattern)[0]

    def last_line_of(self, pattern: str) -> int:
        return self.lines(pattern)[-1]

    def called(self, pattern: str) -> bool:
        return bool(self.lines(pattern))

    def pauses(self) -> list[str]:
        return (self.work / "sleep.log").read_text().split()

    def reads_of(self, service: str) -> int:
        """How many times its PRIMARY deployment was read after the wait."""
        waits = self.lines("wait services-stable")
        return len([n for n in self.lines(f"describe-services .*--services {service} ") if waits and n > waits[0]])

    def recorded(self, environment: str) -> dict | None:
        found = [call for call in self.calls() if call.startswith(f"ssm put-parameter --name /erplora/{environment}/"
                                                                  "saas/app_env --value ")]
        return json.loads(found[0].split(" --value ", 1)[1].split(" --type ", 1)[0]) if found else None

    def cluster_is(self, cluster: str) -> bool:
        """There are cluster-scoped ecs calls, and every call that names a cluster names <cluster>."""
        named = [call for call in self.calls() if "--cluster" in call]
        return any(CLUSTER_SCOPED.search(call) for call in self.calls()) and all(
            f"--cluster {cluster} " in call for call in named)

    def assertNothingChanged(self):
        self.assertNotEqual(0, self.status)
        self.assertFalse(self.called("update-service|put-parameter"))

    def assertFailsBeforeAnyCall(self, *said: str):
        self.assertNotEqual(0, self.status)
        self.assertEqual([], self.calls())
        for line in said:
            self.assertIn(line, self.out)


class SucceedingRollbackTest(RollbackCase):
    def test_prod_goes_back_to_the_revision_right_before_the_one_it_runs(self):
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called("list-task-definitions --family-prefix erplora-prod-saas --status ACTIVE --sort DESC"))
        self.assertEqual(self.lines("update-service"), self.lines(
            f"update-service .*--service saas --task-definition {TD}/erplora-prod-saas:10 "))
        self.assertGreater(self.line_of(r"wait services-stable .*--services saas$"), self.last_line_of("update-service"))
        self.assertGreater(self.last_line_of("describe-services .*--services saas "), self.line_of("wait services"))
        self.assertTrue(self.called(f"describe-task-definition --task-definition {TD}/erplora-prod-saas:10 --include TAGS"))
        self.assertTrue(self.called(
            "^ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 --type String --overwrite"))
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services"))
        self.assertTrue(all("--region eu-south-2" in call for call in self.calls()))
        self.assertTrue(self.cluster_is("erplora-prod"))

    def test_it_touches_neither_the_hub_nor_pre(self):
        self.rollback()
        others = [call for call in self.calls() if not call.startswith("ecs describe-task-definition ")]
        self.assertFalse([call for call in others if re.search(
            "--services? (hub|worker)( |$)|erplora-prod-(hub|worker)|/erplora/prod/hub/", call)])
        self.assertFalse(self.called("erplora-pre-|/erplora/pre/|saas-pre"))

    def test_what_the_rollback_says_and_where(self):
        self.assertEqual(0, self.rollback(apart=True))
        self.assertEqual(
            "::warning::erplora-prod-saas-worker does not exist yet: skipped\n"
            "::warning::rolling back saas (prod) to their previous revisions; migrations are not undone\n"
            "the prod settings of the revisions it goes back to pass every check\n"
            f"rolling back saas to {TD}/erplora-prod-saas:10\n"
            "services stable on the previous revisions\n"
            "recorded the settings of the revisions it went back to in /erplora/prod/saas/app_env\n"
            "recorded tag-10 in /erplora/prod/saas/image_tag\n", self.stdout.decode())
        self.assertEqual(b"", self.stderr)

    def test_the_aws_calls_of_a_rollback_with_saas_worker_one_by_one(self):
        self.with_worker()
        self.assertEqual(0, self.rollback())
        region, cluster = "--region eu-south-2", "--cluster erplora-prod"
        primary = "--query services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState] --output text"
        listing = f"{region} --query taskDefinitionArns --output text"
        self.assertEqual([
            f"ecs list-task-definitions --family-prefix erplora-prod-saas-worker --status ACTIVE {listing}",
            f"ecs describe-services {cluster} --services saas {region} {primary}",
            f"ecs list-task-definitions --family-prefix erplora-prod-saas --status ACTIVE --sort DESC {listing}",
            f"ecs describe-task-definition --task-definition {TD}/erplora-prod-saas:10 --include TAGS {region} --output json",
            f"ecs describe-services {cluster} --services saas-worker {region} {primary}",
            f"ecs list-task-definitions --family-prefix erplora-prod-saas-worker --status ACTIVE --sort DESC {listing}",
            f"ecs describe-task-definition --task-definition {TD}/erplora-prod-saas-worker:10 --include TAGS {region} "
            "--output json",
            f"ssm get-parameter --name /erplora/prod/saas/app_env --query Parameter.Value --output text {region}",
            f"ecs describe-task-definition --task-definition {TD}/erplora-prod-saas:10 --output json {region}",
            f"ecs describe-task-definition --task-definition {TD}/erplora-prod-saas-worker:10 --output json {region}",
            f"ecs describe-task-definition --task-definition erplora-prod-hub --output json {region}",
            f"ecs describe-task-definition --task-definition erplora-prod-worker --output json {region}",
            f"ecs update-service {cluster} --service saas --task-definition {TD}/erplora-prod-saas:10 {region}",
            f"ecs update-service {cluster} --service saas-worker --task-definition {TD}/erplora-prod-saas-worker:10 "
            f"{region}",
            f"ecs wait services-stable {cluster} {region} --services saas saas-worker",
            f"ecs describe-services {cluster} --services saas {region} {primary}",
            f"ecs describe-services {cluster} --services saas-worker {region} {primary}",
            f"ssm put-parameter --name /erplora/prod/saas/app_env --value SETTINGS --type String --overwrite {region}",
            f"ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 --type String --overwrite {region}",
        ], [re.sub(r"--value \{\S*\} ", "--value SETTINGS ", call) for call in self.calls()])

    def test_pre_goes_back_in_its_own_cluster_and_parameters(self):
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertTrue(self.called("list-task-definitions --family-prefix erplora-pre-saas --status ACTIVE --sort DESC"))
        self.assertEqual(self.lines("update-service"), self.lines(
            f"update-service .*--service saas-pre --task-definition {TD}/erplora-pre-saas:10 "))
        self.assertTrue(self.called(r"wait services-stable .*--services saas-pre$"))
        self.assertGreaterEqual(self.reads_of("saas-pre"), 1)
        self.assertTrue(self.called(
            "^ssm put-parameter --name /erplora/pre/saas/image_tag --value tag-10 --type String --overwrite"))
        self.assertFalse(self.called("erplora-prod-|/erplora/prod/|--services? saas( |$)"))
        self.assertTrue(self.cluster_is("erplora-pre"))

    def test_an_explicit_cluster_wins_in_both_environments(self):
        for environment in ("prod", "pre"):
            self.setUp()
            self.assertEqual(0, self.rollback(ENVIRONMENT=environment, CLUSTER="custom-cluster"))
            self.assertTrue(self.cluster_is("custom-cluster"))
            self.setUp()
            self.assertEqual(0, self.rollback(ENVIRONMENT=environment, CLUSTER=""))
            self.assertTrue(self.cluster_is(f"erplora-{environment}"))


if __name__ == "__main__":
    unittest.main()
