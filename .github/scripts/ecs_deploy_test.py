"""Tests of ecs_deploy.py: the deploy of an image tag of the saas to prod or pre.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The deploy runs as the workflow runs it, in a git checkout of its own whose commit abc123 (a tag) carries the
repository's deploy/app-env.json, with a fake aws CLI first on the PATH that records every call and answers from
fixtures. Inside the deploy's process time.sleep only records the pause, so no test waits for real, and gives up after
500 of them, so a loop that never times out fails its test instead of hanging. The settings of deploy/app-env.json are
tested in ecs_deploy_settings_test.py. Only the standard library.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("ecs_deploy.py")
REPO = Path(__file__).resolve().parents[2]
# Terraform gives every task of the saas image these four (ERPlora/aws stacks/prod/apps.tf).
POLICIES = ("CACHE_KEY_PREFIX", "STRIPE_EXPECTED_MODE", "PUBLIC_INDEXING_ENABLED", "AEAT_PRODUCTION_ENABLED")
SAAS_IMAGE = re.compile(r"/erplora/saas(-pre)?:")
CLUSTER_SCOPED = re.compile(r"^ecs (describe-services|update-service|run-task|describe-tasks|wait services-stable) ")
NOT_INHERITED = ("CLUSTER", "PROJECT", "POLL_SECONDS", "MIGRATE_TIMEOUT_SECONDS", "ROLLOUT_TIMEOUT_SECONDS",
                 "CONFIRM_PROTECTED", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

BOOT = """\
import os, runpy, sys, time

def sleep(seconds):
    with open(os.environ["SLEEP_LOG"], "a", encoding="utf-8") as log:
        log.write(f"{seconds}\\n")
    with open(os.environ["SLEEP_LOG"], encoding="utf-8") as log:
        if len(log.readlines()) > 500:
            sys.exit("fake sleep: more than 500 pauses")

time.sleep = sleep
runpy.run_path(sys.argv[1], run_name="__main__")
"""

# Imports only what each answer needs: the fake answers every aws call of every test, and Python starts slowly.
FAKE_AWS = r'''
import os
import sys

args = sys.argv[1:]
env = os.environ
fixtures = env["FIXTURES"]
with open(env["CALLS_LOG"], "a", encoding="utf-8", errors="surrogateescape") as calls:
    calls.write(" ".join(args) + "\n")


def value(flag):
    return next((args[i + 1] for i in range(len(args) - 1) if args[i] == flag), "")


def fixture(name):
    return os.path.join(fixtures, name)


def read(path):
    with open(path, encoding="utf-8") as found:
        return found.read()


def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(254)


def answer(name, default):
    sys.stdout.buffer.write(os.environb.get(name.encode(), default.encode()) + b"\n")


def nth(counter, answers):
    # The next of a list of answers, counted per counter; the last one repeats.
    path = os.path.join(os.path.dirname(fixtures), f"polls.{counter}")
    n = int(read(path)) if os.path.exists(path) else 0
    with open(path, "w", encoding="utf-8") as polls:
        polls.write(str(n + 1))
    answers = answers.split()
    return answers[min(n, len(answers) - 1)]


def describe_task_definition():
    family = value("--task-definition")
    if env.get("FAKE_DESCRIBE_DENIED") == family:
        refuse("An error occurred (AccessDeniedException) when calling the DescribeTaskDefinition operation")
    if not os.path.isfile(fixture(f"{family}.json")):
        refuse("An error occurred (ClientException): Unable to describe task definition.")
    if value("--include") == "TAGS":
        sys.stdout.write(read(fixture(f"{family}.json")))
        return
    import json
    definition = json.loads(read(fixture(f"{family}.json")))
    definition.pop("tags", None)
    print(json.dumps(definition, indent=4))


def list_task_definitions():
    if env.get("FAKE_LIST_FAILURE"):
        refuse(f"An error occurred ({env['FAKE_LIST_FAILURE']}) when calling the ListTaskDefinitions operation")
    family = value("--family-prefix")
    if "FAKE_LIST_ANSWER" in env:
        answer("FAKE_LIST_ANSWER", "")
    elif os.path.isfile(fixture(f"{family}.json")):
        print(f"arn:td/{family}-longer:3\tarn:td/{family}:1")
    elif os.path.isfile(fixture(f"{family}-longer.json")):
        print(f"arn:td/{family}-longer:3")
    else:
        print("None")


def get_parameter():
    environment = value("--name").removeprefix("/erplora/").split("/")[0]
    path = fixture(f"app_env.{environment}.json")
    if env.get("FAKE_APP_ENV_FAILURE") or not os.path.isfile(path):
        error = env.get("FAKE_APP_ENV_FAILURE") or "ParameterNotFound"
        refuse(f"An error occurred ({error}) when calling the GetParameter operation")
    print(read(path))


def put_parameter():
    if env.get("FAKE_PUT_FAILURE") and value("--name").endswith(env["FAKE_PUT_FAILURE"]):
        refuse("An error occurred (AccessDeniedException) when calling the PutParameter operation")
    print('{"Version": 2, "Tier": "Standard"}')


def update_service():
    print(f'{{"service": {{"serviceName": "{value("--service")}"}}}}')


def register_task_definition():
    import json
    revision = read(value("--cli-input-json").removeprefix("file://"))
    with open(env["REGISTERED_LOG"], "a", encoding="utf-8") as registered:
        registered.write(revision.strip() + "\n")
    print(f"arn:td/{json.loads(revision)['family']}:2")


def describe_services():
    service = value("--services")
    if "deployments" not in value("--query"):
        print(f'{{"awsvpcConfiguration": {{"subnets": ["s"], "securityGroups": ["sg-{service}"], '
              '"assignPublicIp": "ENABLED"}}')
    elif "FAKE_PRIMARY_ANSWER" in env:
        answer("FAKE_PRIMARY_ANSWER", "")
    else:
        states = env.get("FAKE_ROLLOUT_STATES") or "COMPLETED"
        if "FAKE_ROLLOUT_STATES_OF" in env:
            import json
            states = json.loads(env["FAKE_ROLLOUT_STATES_OF"]).get(service, states)
        revision = nth(f"revision.{service}", env.get("FAKE_PRIMARY_REVISIONS", "2"))
        state = nth(f"state.{service}", states)
        name = service.removesuffix("-pre")
        family = f"erplora-pre-{name}" if service.endswith("-pre") else f"erplora-prod-{name}"
        print(f"arn:td/{family}:{revision}\t{state}")


def run_task():
    if "FAKE_RUN_TASK_ANSWER" in env:
        answer("FAKE_RUN_TASK_ANSWER", "")
    elif env.get("FAKE_RUN_TASK_FAILURE"):
        import json
        print(json.dumps({"tasks": [], "failures": [{"arn": "arn:capacity", "reason": env["FAKE_RUN_TASK_FAILURE"]}]}))
    else:
        print(f'{{"tasks": [{{"taskArn": "arn:task/{value("--cluster")}/migrate1"}}], "failures": []}}')


def describe_tasks():
    query = value("--query")
    if "lastStatus" in query:
        print(nth("status", env.get("FAKE_TASK_STATUSES", "RUNNING STOPPED")))
    elif "exitCode" in query:
        print(env.get("FAKE_MIGRATE_EXIT") or "0")
    elif "stoppedReason" in query:
        answer("FAKE_STOPPED_REASON", "Essential container in task exited")


COMMANDS = {
    "ecs describe-task-definition": describe_task_definition, "ecs list-task-definitions": list_task_definitions,
    "ssm get-parameter": get_parameter, "ssm put-parameter": put_parameter,
    "ecs register-task-definition": register_task_definition, "ecs describe-services": describe_services,
    "ecs run-task": run_task, "ecs describe-tasks": describe_tasks, "ecs update-service": update_service,
}
command = " ".join(args[:2])
if env.get("FAKE_KILLED_ON") == command:
    os.kill(os.getpid(), 9)
COMMANDS.get(command, lambda: None)()
'''


def task_definition(family: str, containers: list, environment: str | None = None, role: str = "") -> dict:
    """A task definition as `describe-task-definition --include TAGS` returns it, with the roles Terraform gives its
    family (<family>-task and <family>-execution, or <role>-…) and the Environment tag of the family's environment ("":
    none). A container of the saas image without an environment of its own gets the four policies."""
    environment = family.removeprefix("erplora-").split("-")[0] if environment is None else environment
    arn = f"arn:aws:iam::123456789012:role/{role or family}"
    given = [{"name": name, "value": "x"} for name in POLICIES]
    containers = [c if "environment" in c or not SAAS_IMAGE.search(c.get("image", "")) else {**c, "environment": given}
                  for c in containers]
    tags = [{"key": "Project", "value": "erplora"}, {"key": "ManagedBy", "value": "terraform"}]
    return {
        "taskDefinition": {
            "family": family, "taskDefinitionArn": f"arn:td/{family}:1", "revision": 1, "status": "ACTIVE",
            "requiresAttributes": [], "compatibilities": ["FARGATE"], "registeredAt": "t", "registeredBy": "u",
            "taskRoleArn": f"{arn}-task", "executionRoleArn": f"{arn}-execution", "containerDefinitions": containers,
        },
        "tags": tags + ([{"key": "Environment", "value": environment}] if environment else []),
    }


def one(name: str, image: str, **more) -> list:
    return [{"name": name, "image": f"reg.example/erplora/{image}", **more}]


class DeployCase(unittest.TestCase):
    """A fresh fake AWS and checkout for each test: prod and pre each with their families on their own image, the
    Hub's families (which file in the AEAT's production) beside prod's, and the settings in force equal to the file."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.fixtures = self.work / "fixtures"
        self.repo = self.work / "repo"
        for folder in (self.work / "bin", self.fixtures, self.repo / "deploy"):
            folder.mkdir(parents=True)
        self.fixture("erplora-prod-saas", one("saas", "saas:bootstrap") + [
            {"name": "log-router", "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
            {"name": "look-alike", "image": "reg.example/erplora/saasx:bootstrap"},
            {"name": "hub-image", "image": "reg.example/erplora/hub:bootstrap"}])
        for name in ("saas-migrate", "saas-cron"):
            self.fixture(f"erplora-prod-{name}", one(name, "saas:bootstrap"))
        for name in ("hub", "worker", "hub-migrate", "db-bootstrap"):
            filing = [{"name": "VERIFACTU_PRODUCTION_ENABLED", "value": "true"}]
            self.fixture(f"erplora-prod-{name}", one(name, "hub:bootstrap", environment=filing))
        self.fixture("erplora-pre-saas", one("saas", "saas-pre:bootstrap") + one("prod-image", "saas:bootstrap"))
        self.fixture("erplora-pre-saas-migrate", one("saas-migrate", "saas-pre:bootstrap"))
        shutil.copy(REPO / "deploy" / "app-env.json", self.repo / "deploy" / "app-env.json")
        self.git("init", "-q")
        self.commit_settings()
        for environment in ("prod", "pre"):
            self.in_force(environment, self.file()[environment])
        aws = self.work / "bin" / "aws"
        aws.write_text(f"#!{sys.executable} -IS\n{FAKE_AWS}")
        aws.chmod(0o755)

    def fixture(self, family: str, containers: list, *rest) -> None:
        (self.fixtures / f"{family}.json").write_text(json.dumps(task_definition(family, containers, *rest)))

    def in_force(self, environment: str, settings: object) -> None:
        (self.fixtures / f"app_env.{environment}.json").write_text(json.dumps(settings))

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=test", "-c", "user.email=test@example.com",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    def commit_settings(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "settings")
        self.git("tag", "-f", "abc123")

    def file(self) -> dict:
        return json.loads((self.repo / "deploy" / "app-env.json").read_text())

    def settings(self, change) -> None:
        """Changes deploy/app-env.json of abc123 with <change>, a function that edits the settings in place."""
        settings = self.file()
        change(settings)
        (self.repo / "deploy" / "app-env.json").write_text(json.dumps(settings))
        self.commit_settings()

    def environ(self, unset: tuple, env: dict) -> dict:
        environ = {key: value for key, value in os.environ.items() if key not in NOT_INHERITED}
        environ.update(PATH=f"{self.work / 'bin'}:{os.environ['PATH']}", AWS_REGION="eu-south-2",
                       REGISTRY="reg.example", IMAGE_TAG="abc123", ENVIRONMENT="prod", FIXTURES=str(self.fixtures),
                       CALLS_LOG=str(self.work / "calls.log"), REGISTERED_LOG=str(self.work / "registered.log"),
                       SLEEP_LOG=str(self.work / "sleep.log"), AWS_CONFIG_FILE=os.devnull,
                       AWS_SHARED_CREDENTIALS_FILE=os.devnull)
        environ.update(env)
        for name in unset:
            environ.pop(name, None)
        return environ

    def deploy(self, *unset: str, apart: bool = False, **env) -> int:
        """Deploys abc123 to prod with the fakes, in the checkout; <env> overrides the environment and <unset> takes
        variables out of it. stdout and stderr land together in self.out, or apart in self.stdout and self.stderr. The
        logs and the fake's counters start empty."""
        for log in ("calls.log", "registered.log", "sleep.log"):
            (self.work / log).write_text("")
        for counter in self.work.glob("polls.*"):
            counter.unlink()
        done = subprocess.run([sys.executable, "-c", BOOT, str(SCRIPT)], cwd=self.repo, env=self.environ(unset, env),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE if apart else subprocess.STDOUT,
                              timeout=120, check=False)
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

    def registered(self) -> dict:
        lines = (self.work / "registered.log").read_text().splitlines()
        return {revision["family"]: revision for revision in map(json.loads, lines)}

    def images(self, family: str, name: str | None = None) -> list[str]:
        containers = self.registered()[family]["containerDefinitions"]
        return [c["image"] for c in containers if name is None or c["name"] == name]

    def cluster_is(self, cluster: str) -> bool:
        """There are cluster-scoped ecs calls, and every call that names a cluster names <cluster>."""
        named = [call for call in self.calls() if "--cluster" in call]
        return any(CLUSTER_SCOPED.search(call) for call in self.calls()) and all(
            f"--cluster {cluster} " in call for call in named)

    def assertNothingRegistered(self):
        self.assertNotEqual(0, self.status)
        self.assertEqual({}, self.registered())
        self.assertFalse(self.called("register-task-definition|run-task|update-service|put-parameter"))

    def assertFailsBeforeAnyCall(self, *names: str):
        self.assertNotEqual(0, self.status)
        self.assertEqual([], self.calls())
        for name in names:
            self.assertIn(name, self.out)


class SucceedingDeployTest(DeployCase):
    def test_prod_registers_migrates_moves_and_records(self):
        self.assertEqual(0, self.deploy())
        self.assertEqual(["erplora-prod-saas", "erplora-prod-saas-cron", "erplora-prod-saas-migrate"],
                         sorted(self.registered()))
        self.assertEqual(["erplora-prod-hub", "erplora-prod-worker"], sorted(re.findall(
            r"--task-definition (erplora-prod-(?:hub|worker|hub-migrate|db-bootstrap))(?: |$)", "\n".join(self.calls()),
            re.M)))
        self.assertEqual(["reg.example/erplora/saas:abc123"], self.images("erplora-prod-saas", "saas"))
        for family in ("erplora-prod-saas-migrate", "erplora-prod-saas-cron"):
            self.assertEqual(["reg.example/erplora/saas:abc123"], self.images(family))
        self.assertTrue(self.called(r"run-task .*--task-definition arn:td/erplora-prod-saas-migrate:2 "
                                    r'.*--network-configuration \{"awsvpcConfiguration".*"sg-saas"'))
        self.assertTrue(self.called(r"describe-services .*--services saas .*--query services\[0\]\.networkConfiguration"))
        self.assertTrue(self.called(r"describe-tasks .*containers\[\?name=='saas-migrate'\]\.exitCode"))
        self.assertFalse(self.called(r"containers\[0\]|wait tasks-stopped|--desired-count"))
        self.assertLess(self.last_line_of("describe-tasks"), self.line_of("update-service"))
        self.assertEqual(self.lines("update-service"), self.lines(
            "update-service .*--service saas --task-definition arn:td/erplora-prod-saas:2 "))
        self.assertTrue(self.called(r"wait services-stable .*--services saas$"))
        self.assertGreater(self.last_line_of(r"describe-services .*--services saas .*deployments"),
                           self.line_of("wait services-stable"))
        self.assertTrue(self.called(
            "^ssm put-parameter --name /erplora/prod/saas/image_tag --value abc123 --type String --overwrite"))
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services .*deployments"))
        self.assertTrue(all("--region eu-south-2" in call for call in self.calls()))
        self.assertTrue(self.cluster_is("erplora-prod"))

    def test_prod_keeps_the_rest_of_each_definition_and_touches_nothing_else(self):
        self.deploy()
        saas = self.registered()["erplora-prod-saas"]
        self.assertEqual(["public.ecr.aws/aws-observability/aws-for-fluent-bit:stable",
                          "reg.example/erplora/saasx:bootstrap", "reg.example/erplora/hub:bootstrap"],
                         [c["image"] for c in saas["containerDefinitions"] if c["name"] != "saas"])
        self.assertEqual("arn:aws:iam::123456789012:role/erplora-prod-saas-task", saas["taskRoleArn"])
        read_only = {"taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
                     "registeredAt", "registeredBy"}
        self.assertFalse(any(read_only & set(revision) for revision in self.registered().values()))
        self.assertEqual(task_definition("erplora-prod-saas-cron", [])["tags"],
                         self.registered()["erplora-prod-saas-cron"]["tags"])
        registered = (self.work / "registered.log").read_text()
        self.assertFalse(re.search("erplora-pre-|/erplora/pre/|saas-pre", "\n".join(self.calls()) + registered))
        self.assertFalse(self.called(r"update-service .*--service saas-(cron|migrate)|run-task .*saas-cron"))
        self.assertFalse(self.called("--services? worker( |$)"))
        self.assertFalse([call for call in self.calls() if not call.startswith("ecs describe-task-definition ")
                          and re.search("erplora-prod-(hub|worker|db-bootstrap)|/erplora/prod/hub/|--services? hub( |$)",
                                        call)])

    def test_what_the_deploy_says_and_where(self):
        self.assertEqual(0, self.deploy(apart=True))
        self.assertEqual(
            b"::warning::erplora-prod-saas-worker does not exist yet: skipped\n"
            b"deploy/app-env.json of abc123: the prod settings pass every check\n"
            b"registered arn:td/erplora-prod-saas:2\nregistered arn:td/erplora-prod-saas-migrate:2\n"
            b"registered arn:td/erplora-prod-saas-cron:2\nrunning saas-migrate: arn:task/erplora-prod/migrate1\n"
            b"updated saas\nservices stable on the new revisions\n"
            b"recorded the prod settings of deploy/app-env.json in /erplora/prod/saas/app_env\n"
            b"recorded abc123 in /erplora/prod/saas/image_tag\n", self.stdout)
        self.assertEqual(b"", self.stderr)
        self.assertNotEqual(0, self.deploy(apart=True, FAKE_MIGRATE_EXIT="1"))
        self.assertEqual(b"::error::saas-migrate exited with code 1; logs in /ecs/erplora-prod-saas-migrate\n",
                         self.stderr)

    def test_its_lines_come_in_order_with_what_app_env_and_aws_say(self):
        self.deploy(FAKE_APP_ENV_FAILURE="AccessDeniedException")
        self.assertTrue(self.out.startswith("::warning::erplora-prod-saas-worker does not exist yet: skipped\n"
                                            "::error::aws ssm get-parameter failed: "), self.out)
        self.deploy(FAKE_LIST_FAILURE="Throttling")
        self.assertEqual("An error occurred (Throttling) when calling the ListTaskDefinitions operation\n"
                         "::error::could not look for erplora-prod-saas-worker; nothing was registered\n", self.out)

    def test_the_aws_calls_of_a_deploy_with_saas_worker_one_by_one(self):
        self.fixture("erplora-prod-saas-worker", one("saas-worker", "saas:bootstrap"))
        self.assertEqual(0, self.deploy())
        region, cluster = "--region eu-south-2", "--cluster erplora-prod"
        network = ('{"awsvpcConfiguration": {"subnets": ["s"], "securityGroups": ["sg-saas"], '
                   '"assignPublicIp": "ENABLED"}}')
        task = f"describe-tasks {cluster} --tasks arn:task/erplora-prod/migrate1 {region} --query tasks[0]."
        primary = "--query services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState] --output text"
        families = ("saas", "saas-migrate", "saas-cron", "saas-worker")
        self.assertEqual([
            f"ecs list-task-definitions --family-prefix erplora-prod-saas-worker --status ACTIVE {region} --query "
            "taskDefinitionArns --output text",
            f"ssm get-parameter --name /erplora/prod/saas/app_env --query Parameter.Value --output text {region}",
            f"ecs describe-task-definition --task-definition erplora-prod-hub --output json {region}",
            f"ecs describe-task-definition --task-definition erplora-prod-worker --output json {region}",
            *(f"ecs describe-task-definition --task-definition erplora-prod-{name} --include TAGS {region} --output json"
              for name in families),
            *(f"ecs register-task-definition --cli-input-json file://WORKDIR/{name}.json {region} --query "
              "taskDefinition.taskDefinitionArn --output text" for name in families),
            f"ecs describe-services {cluster} --services saas {region} --query services[0].networkConfiguration --output json",
            f"ecs run-task {cluster} --launch-type FARGATE --task-definition arn:td/erplora-prod-saas-migrate:2 "
            f"--network-configuration {network} --started-by deploy-abc123 {region} --output json",
            f"ecs {task}lastStatus --output text", f"ecs {task}lastStatus --output text",
            f"ecs {task}containers[?name=='saas-migrate'].exitCode | [0] --output text",
            f"ecs update-service {cluster} --service saas --task-definition arn:td/erplora-prod-saas:2 {region}",
            f"ecs update-service {cluster} --service saas-worker --task-definition arn:td/erplora-prod-saas-worker:2 "
            f"{region}",
            f"ecs wait services-stable {cluster} {region} --services saas saas-worker",
            f"ecs describe-services {cluster} --services saas {region} {primary}",
            f"ecs describe-services {cluster} --services saas-worker {region} {primary}",
            f"ssm put-parameter --name /erplora/prod/saas/app_env --value SETTINGS --type String --overwrite {region}",
            f"ssm put-parameter --name /erplora/prod/saas/image_tag --value abc123 --type String --overwrite {region}",
        ], [re.sub(r"--value \{\S*\} ", "--value SETTINGS ", re.sub(r"file://\S*/", "file://WORKDIR/", call))
            for call in self.calls()])


if __name__ == "__main__":
    unittest.main()
