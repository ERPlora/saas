#!/usr/bin/env python3
"""Deploys an image tag of the saas to one environment, in that environment's own ECS cluster (erplora-<ENVIRONMENT>),
touching only that environment's saas task families and services:
  prod: cluster erplora-prod, families erplora-prod-{saas,saas-migrate,saas-cron,saas-worker}, services saas and
        saas-worker, image erplora/saas;
  pre:  cluster erplora-pre, families erplora-pre-{saas,saas-migrate,saas-worker} (no saas-cron), services saas-pre
        and saas-worker-pre, image erplora/saas-pre; the containers keep the short names (saas, saas-migrate,
        saas-worker).
  saas-worker (manage.py run_worker: the WhatsApp deliveries and the reconciliations) is created by ERPlora/aws once an
  image with run_worker is out: while its family does not exist the deploy goes on without it and says so
  (::warning::); any other error looking for it or reading it fails the deploy as for the other families.
  0. checks deploy/app-env.json of the commit it deploys (app_env.py check): the saas's settings that are no secret, by
     environment and family. It refuses an unknown environment, family or variable, a value that is no text or not of
     its kind, a name that looks like a secret, and pre or Analytics settings that break the safety rules; reads the
     settings in force (/erplora/<ENVIRONMENT>/saas/app_env) and, in prod, refuses to change
     PLATFORM_INVOICING_ENABLED, AEAT_PRODUCTION_ENABLED or STRIPE_EXPECTED_MODE without CONFIRM_PROTECTED, and to
     charge real money unless the Hub's hub and worker file in the AEAT's production. Then it reads the latest ACTIVE
     revision of every family and refuses them all, registering nothing, unless each one carries the tag
     Environment=<ENVIRONMENT> and the task and execution roles of its environment (role/erplora-<ENVIRONMENT>-…):
     ecs:RegisterTaskDefinition takes no resource, so another environment's deploy role could have left a revision in
     this family;
  1. registers a new revision of each family from that one, with its tags, changing only the image and the family's
     settings of the containers that run the saas image (one per task: the app; app_env.py revision): a setting
     ERPlora/aws gives it as a secret (one owner per variable), or a container left without CACHE_KEY_PREFIX or one of
     the four policies, registers nothing. Terraform owns the rest of the definition; saas-cron is only registered (the
     Scheduler runs its latest);
  2. runs the migration (saas-migrate) on the new revision and polls it until it is STOPPED; if it fails, never ran or
     outlasts MIGRATE_TIMEOUT_SECONDS (the task is left running), the deploy stops before any service changes;
  3. moves the services to the new revisions (in pre also to one task: a push wakes pre up, which its schedule stops
     every evening), waits until they are stable and then polls each one's PRIMARY deployment until it is the new
     revision, COMPLETED: ECS marks it COMPLETED seconds to a minute after services-stable returns, once the old tasks
     drain from the ALB. A FAILED rollout or another revision as PRIMARY (with rollback = true the circuit breaker puts
     the old one back and the wait still succeeds) fails at once; a rollout that outlasts ROLLOUT_TIMEOUT_SECONDS
     fails too;
  4. records the settings in /erplora/<ENVIRONMENT>/saas/app_env and the tag in .../image_tag, so the revisions
     Terraform registers, and with them the scheduled tasks, keep both (ERPlora/aws README).
Never db-bootstrap: the deploy role cannot pass its roles (ERPlora/aws deploy_role.tf).
Rollback: the circuit breaker reverts a broken deploy; back to the previous revisions, the rollback workflow
  (ecs_rollback.py); back to a release, the deploy workflow with that release.

  python3 .github/scripts/ecs_deploy.py   (in the checkout of the repository)

Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA), ENVIRONMENT (prod|pre); optional
     CLUSTER (erplora-<ENVIRONMENT>: each environment has its own cluster), POLL_SECONDS (15), MIGRATE_TIMEOUT_SECONDS
     (3600), ROLLOUT_TIMEOUT_SECONDS (600), CONFIRM_PROTECTED (VAR=value of each protected setting a prod deploy
     changes).
What it shares with the rollback, and how it stops, is ecs_common.py's. Only the standard library: the workflow runs it
with the runner's python3.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ecs_common import (
    PROJECT,
    Release,
    aws,
    described_in_its_environment,
    environment_given,
    exists,
    key,
    main,
    record,
    refusal,
    run_script,
    seconds_given,
    unreadable,
    wait_until_stable,
    watch_rollout,
)

APP_ENV = Path(__file__).resolve().with_name("app_env.py")
MIGRATION = "saas-migrate"
# Families each environment deploys; pre has no scheduled platform tasks (saas-cron).
FAMILIES = {"prod": ("saas", "saas-migrate", "saas-cron"), "pre": ("saas", "saas-migrate")}
# Families that run as a service; the service of family <name> is <name><suffix>.
SERVICES = ("saas",)
# Services that may not exist yet (saas-worker until ERPlora/aws creates it): deployed once their family exists.
NOT_YET = ("saas-worker",)
# The migration runs like the saas service (same subnets, sg-app, public IP; sg-app reaches Aurora and Valkey, and
# nothing listens on 8000 in the migration), never like saas-worker (it may not exist).
NETWORK_SERVICE = "saas"
REQUIRED = ("AWS_REGION", "REGISTRY", "IMAGE_TAG")
SECONDS = {"POLL_SECONDS": "15", "MIGRATE_TIMEOUT_SECONDS": "3600", "ROLLOUT_TIMEOUT_SECONDS": "600"}
UNREGISTERED = "; nothing was registered"
JSON_BLANK = " \t\n\r"


@dataclass
class Deploy(Release):
    registry: str
    image_tag: str
    families: list[str]
    services: list[str] = field(default_factory=lambda: list(SERVICES))
    workdir: str = ""
    arns: dict[str, str] = field(default_factory=dict)

    @property
    def project_image(self) -> str:
        return f"{self.registry}/erplora/{PROJECT}{self.suffix}:"


def configured(env: Mapping[str, str]) -> Deploy:
    """The deploy the environment asks for: a missing setting, an unknown environment or a number of seconds that is
    none is refused before any aws call."""
    for name in REQUIRED:
        if not env.get(name):
            raise refusal(f"{name} is required")
    environment = environment_given(env, "")
    return Deploy(region=env["AWS_REGION"], registry=env["REGISTRY"], image_tag=env["IMAGE_TAG"],
                  environment=environment, cluster=env.get("CLUSTER") or f"erplora-{environment}",
                  seconds=seconds_given(env, SECONDS, ""), families=list(FAMILIES[environment]))


def add_the_ones_that_exist(deploy: Deploy) -> None:
    for name in NOT_YET:
        if exists(deploy, name, UNREGISTERED):
            deploy.families.append(name)
            deploy.services.append(name)


def prepare(deploy: Deploy, name: str) -> None:
    """Reads the latest ACTIVE revision of <name>'s family, refuses one of another environment and writes the new
    revision to register, with the new image."""
    described = described_in_its_environment(deploy, f"{deploy.prefix}-{name}", UNREGISTERED)
    with open(Path(deploy.workdir) / f"{name}.json", "wb") as revision:
        run_script(APP_ENV, "revision", "--workdir", deploy.workdir, "--family", name,
                   "--image", f"{deploy.project_image}{deploy.image_tag}", "--project-image", deploy.project_image,
                   stdin=described.encode("utf-8", "surrogateescape"), stdout=revision)


def register(deploy: Deploy, name: str) -> None:
    deploy.arns[name] = aws("ecs", "register-task-definition", "--cli-input-json",
                            f"file://{deploy.workdir}/{name}.json", "--region", deploy.region,
                            "--query", "taskDefinition.taskDefinitionArn", "--output", "text")
    print(f"registered {deploy.arns[name]}")


def first(value: object) -> object:
    """jq's `.[0]`: null on null or an empty list; anything but a list or null cannot be read through."""
    if isinstance(value, list) or value is None:
        return value[0] if value else None
    raise TypeError(f"cannot index {type(value).__name__} with a number")


def started(answer: str) -> tuple[str, str]:
    """The task run-task started and its failures, read as jq's `.tasks[0].taskArn // empty` and `.failures` read
    them: "" for no task, and nothing at all from a blank answer."""
    if not answer.strip(JSON_BLANK):
        return "", ""
    try:
        found = json.loads(answer)
        arn = key(first(key(found, "tasks")), "taskArn")
    except (ValueError, TypeError) as why:
        raise unreadable("the answer of run-task", why) from None
    failures = json.dumps(key(found, "failures"), ensure_ascii=False, separators=(",", ":"))
    if arn is None or arn is False:
        return "", failures
    return (arn if isinstance(arn, str) else json.dumps(arn, indent=2, ensure_ascii=False)).rstrip("\n"), failures


def describe_task(deploy: Deploy, task: str, query: str) -> str:
    return aws("ecs", "describe-tasks", "--cluster", deploy.cluster, "--tasks", task, "--region", deploy.region,
               "--query", query, "--output", "text")


def wait_until_stopped(deploy: Deploy, task: str) -> None:
    waited = 0
    while True:
        status = describe_task(deploy, task, "tasks[0].lastStatus")
        if status == "STOPPED":
            return
        if waited >= deploy.seconds_of("MIGRATE_TIMEOUT_SECONDS"):
            raise refusal(f"{MIGRATION} is still {status} after {deploy.seconds['MIGRATE_TIMEOUT_SECONDS']}s; it was "
                          f"left running ({task}) and no service changed; logs in /ecs/{deploy.prefix}-{MIGRATION}")
        time.sleep(deploy.seconds_of("POLL_SECONDS"))
        waited += deploy.seconds_of("POLL_SECONDS")


def migrate(deploy: Deploy) -> None:
    """Runs the migration on its new revision with the network of NETWORK_SERVICE and polls it until it is STOPPED;
    its container has the family's name (ERPlora/aws modules/ecs-service)."""
    network = aws("ecs", "describe-services", "--cluster", deploy.cluster, "--services",
                  f"{NETWORK_SERVICE}{deploy.suffix}", "--region", deploy.region,
                  "--query", "services[0].networkConfiguration", "--output", "json")
    answer = aws("ecs", "run-task", "--cluster", deploy.cluster, "--launch-type", "FARGATE",
                 "--task-definition", deploy.arns[MIGRATION], "--network-configuration", network,
                 "--started-by", f"deploy-{deploy.image_tag[:12]}", "--region", deploy.region, "--output", "json")
    task, failures = started(answer)
    if not task:
        raise refusal(f"{MIGRATION} did not start: {failures}")
    print(f"running {MIGRATION}: {task}")
    wait_until_stopped(deploy, task)
    code = describe_task(deploy, task, f"tasks[0].containers[?name=='{MIGRATION}'].exitCode | [0]")
    if code == "None":
        raise refusal(f"{MIGRATION} stopped without running: {describe_task(deploy, task, 'tasks[0].stoppedReason')}")
    if code != "0":
        raise refusal(f"{MIGRATION} exited with code {code}; logs in /ecs/{deploy.prefix}-{MIGRATION}")


def move(deploy: Deploy) -> dict[str, str]:
    """Moves each service to its family's new revision and waits until they are stable; autoscaling owns prod's
    desired count, and pre's schedule stops it every evening, so a deploy starts it again. Returns the revision each
    service must run."""
    wake = [] if deploy.prod else ["--desired-count", "1"]
    targets = {}
    for name in deploy.services:
        service = f"{name}{deploy.suffix}"
        aws("ecs", "update-service", "--cluster", deploy.cluster, "--service", service,
            "--task-definition", deploy.arns[name], *wake, "--region", deploy.region, stdout=subprocess.DEVNULL)
        print(f"updated {service}")
        targets[service] = deploy.arns[name]
    wait_until_stable(deploy, list(targets))
    return targets


def deploy_all(deploy: Deploy) -> None:
    add_the_ones_that_exist(deploy)
    # The settings and every family are checked before any is registered.
    run_script(APP_ENV, "check", "--workdir", deploy.workdir, "--environment", deploy.environment,
               "--region", deploy.region, "--commit", deploy.image_tag)
    for name in deploy.families:
        prepare(deploy, name)
    for name in deploy.families:
        register(deploy, name)
    migrate(deploy)
    watch_rollout(deploy, move(deploy))
    print("services stable on the new revisions")
    record(deploy, APP_ENV, deploy.workdir, deploy.image_tag)


def deploy_from(env: Mapping[str, str]) -> None:
    deploy = configured(env)
    with tempfile.TemporaryDirectory() as workdir:
        deploy.workdir = workdir
        deploy_all(deploy)


if __name__ == "__main__":
    raise SystemExit(main(lambda: deploy_from(os.environ)))
