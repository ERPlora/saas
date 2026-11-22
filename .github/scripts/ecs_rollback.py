#!/usr/bin/env python3
"""Puts the saas's services of one environment (prod: saas and saas-worker in cluster erplora-prod; pre: saas-pre and
saas-worker-pre in erplora-pre) back on the ACTIVE revision right before the one each PRIMARY deployment runs.
saas-worker never blocks saas: while its family does not exist, without an earlier revision or with one of another tag
than saas's (an image without run_worker would crash-loop), it stays as it is, with a ::warning::; any other error
looking for it, or a revision of another environment or image, still fails:
  1. finds each previous revision; nothing changes unless saas has one, each is a revision of this environment (the tag
     Environment=<ENVIRONMENT> and the roles erplora-<ENVIRONMENT>-*: another environment's deploy role could have
     registered it) on this environment's image (erplora/saas or erplora/saas-pre), and they all run the same tag;
  2. checks the settings those revisions run with, with the deploy's rules (app_env_rollback.py check): in prod a
     protected setting that changes needs CONFIRM_PROTECTED, and the real charge the Hub filing in production;
  3. moves the services, waits until they are stable and polls each PRIMARY deployment until it is the previous
     revision, COMPLETED (ECS marks it so once the old tasks drain from the ALB). A FAILED rollout or another revision
     as PRIMARY (the circuit breaker put back the one it ran) fails at once, and so does a rollout that outlasts
     ROLLOUT_TIMEOUT_SECONDS;
  4. only then records their settings in /erplora/<ENVIRONMENT>/saas/app_env and the tag in .../image_tag (ERPlora/aws
     README), so a failed rollback leaves both as they were.
Migrations are NOT undone: the previous code must work on the current schema (expand/contract). saas-cron (the
Scheduler runs its latest revision) and saas-migrate keep the newer image and their settings in app_env until the next
deploy; to go back everywhere, deploy the previous release.

  python3 .github/scripts/ecs_rollback.py   (in the checkout of the repository)

Env: CONFIRM (exactly ROLLBACK), AWS_REGION, ENVIRONMENT (prod|pre); optional CLUSTER (erplora-<ENVIRONMENT>),
     POLL_SECONDS (15), ROLLOUT_TIMEOUT_SECONDS (600), CONFIRM_PROTECTED (VAR=value of each protected setting a prod
     rollback changes).
What it shares with the deploy, and how it stops, is ecs_common.py's. Only the standard library: the workflow runs it
with the runner's python3.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ecs_common import (
    PROJECT,
    Release,
    arns_listed,
    aws,
    described_in_its_environment,
    environment_given,
    exists,
    key,
    main,
    primary,
    record,
    refusal,
    run_script,
    seconds_given,
    unreadable,
    wait_until_stable,
    watch_rollout,
)

APP_ENV = Path(__file__).resolve().with_name("app_env_rollback.py")
# Families that run as a service: the service of family <name> is <name><suffix>, its container <name>.
SERVICES = ("saas",)
# Families that may not exist yet; a family prefix also lists longer ones: only <name>'s own family counts.
NOT_YET = ("saas-worker",)
SECONDS = {"POLL_SECONDS": "15", "ROLLOUT_TIMEOUT_SECONDS": "600"}
UNCHANGED = "; nothing was changed"


@dataclass
class Rollback(Release):
    families: list[str] = field(default_factory=lambda: list(SERVICES))
    # The families of NOT_YET that exist: they never block the rollback of saas.
    optional: list[str] = field(default_factory=list)
    workdir: str = ""

    @property
    def repository(self) -> str:
        return f"erplora/{PROJECT}{self.suffix}"


class Previous(NamedTuple):
    """The revision a service goes back to, and the tag of its app image."""

    name: str
    service: str
    revision: str
    tag: str


def configured(env: Mapping[str, str]) -> Rollback:
    """The rollback the environment asks for: without the confirmation, the region, a known environment or numbers of
    seconds it is refused before any aws call."""
    confirm = env.get("CONFIRM", "")
    if confirm != "ROLLBACK":
        raise refusal(f"CONFIRM must be exactly ROLLBACK, not '{confirm}'{UNCHANGED}")
    if not env.get("AWS_REGION"):
        raise refusal("AWS_REGION is required")
    environment = environment_given(env, UNCHANGED)
    seconds = seconds_given(env, SECONDS, UNCHANGED)
    return Rollback(region=env["AWS_REGION"], environment=environment,
                    cluster=env.get("CLUSTER") or f"erplora-{environment}", seconds=seconds)


def current_revision(rollback: Rollback, service: str, family: str) -> str:
    current, _ = primary(rollback, service)
    if not re.search(rf":task-definition/{re.escape(family)}:[0-9]+$", current):
        raise refusal(f"{service} has no PRIMARY deployment of {family} (got '{current}'){UNCHANGED}")
    return current


def previous_revision(rollback: Rollback, family: str, current: str) -> str:
    """Of its own family only (the prefix also lists erplora-prod-saas-migrate), the highest ACTIVE revision below the
    current one; "" when there is none."""
    listed = aws("ecs", "list-task-definitions", "--family-prefix", family, "--status", "ACTIVE", "--sort", "DESC",
                 "--region", rollback.region, "--query", "taskDefinitionArns", "--output", "text")
    own, below = current.rsplit(":", 1)
    previous, best = "", 0
    for arn in arns_listed(listed):
        revision = arn.rsplit(":", 1)[-1]
        if arn.rsplit(":", 1)[0] == own and re.fullmatch("[0-9]+", revision) and best < int(revision) < int(below):
            previous, best = arn, int(revision)
    return previous


def as_jq_writes(text: str) -> str:
    """What jq writes for a string: a character it cannot encode (a byte that is no UTF-8, a lone surrogate) as U+FFFD."""
    return re.sub("[\ud800-\udfff]", "\ufffd", text)


def containers_of(described: str) -> list:
    """jq's `.taskDefinition.containerDefinitions[]`: the values of a list or an object; anything else cannot be
    iterated over."""
    containers = key(key(json.loads(described), "taskDefinition"), "containerDefinitions")
    if isinstance(containers, dict):
        return list(containers.values())
    if isinstance(containers, list):
        return containers
    raise TypeError(f"cannot iterate over {type(containers).__name__}")


def app_image(described: str, name: str, revision: str) -> str:
    """jq -r's `[.taskDefinition.containerDefinitions[] | select(.name == $name) | .image][0] // ""`, as $(…) keeps it:
    without its trailing newlines. A container that cannot be read through ends the rollback, as jq did."""
    try:
        images = [key(container, "image") for container in containers_of(described)
                  if key(container, "name") == name]
    except TypeError as why:
        raise unreadable(revision, why) from None
    image = images[0] if images else None
    if image is None or image is False:
        return ""
    text = image if isinstance(image, str) else json.dumps(image, indent=2, ensure_ascii=False)
    return as_jq_writes(text).rstrip("\n")


def previous_of(rollback: Rollback, name: str) -> Previous | None:
    """The revision <name>'s service goes back to; None for an optional one without an earlier revision."""
    service, family = f"{name}{rollback.suffix}", f"{rollback.prefix}-{name}"
    current = current_revision(rollback, service, family)
    previous = previous_revision(rollback, family, current)
    if not previous:
        if name in rollback.optional:
            print(f"::warning::{service} runs {current} and {family} has no earlier ACTIVE revision: it stays as it is")
            return None
        raise refusal(f"{service} runs {current} and {family} has no earlier ACTIVE revision{UNCHANGED}")
    described = described_in_its_environment(rollback, previous, UNCHANGED)
    image = app_image(described, name, previous)
    if f"/{rollback.repository}:" not in image:
        raise refusal(f"{previous} does not run an {rollback.repository} image ({image}){UNCHANGED}")
    return Previous(name, service, previous, image.rsplit(":", 1)[-1])


def kept(rollback: Rollback, moving: list[Previous]) -> dict[str, str]:
    """The services that go back, each to its revision: saas comes first and is never skipped, and the others go back
    only to its tag."""
    targets = {}
    for previous in moving:
        if previous.tag != moving[0].tag:
            if previous.name in rollback.optional:
                print(f"::warning::{previous.service}: its previous revision {previous.revision} runs {previous.tag}, "
                      f"not {moving[0].tag} as {moving[0].service}'s: it stays as it is")
                continue
            tags = " ".join(each.tag for each in moving)
            raise refusal(f"the previous revisions run different tags ({tags}){UNCHANGED}")
        targets[previous.service] = previous.revision
    return targets


def roll_back(rollback: Rollback) -> None:
    for name in NOT_YET:
        if exists(rollback, name, UNCHANGED):
            rollback.families.append(name)
            rollback.optional.append(name)
    services = " ".join(f"{name}{rollback.suffix}" for name in rollback.families)
    print(f"::warning::rolling back {services} ({rollback.environment}) to their previous revisions; migrations are "
          "not undone")
    moving = [previous for previous in (previous_of(rollback, name) for name in rollback.families) if previous]
    targets = kept(rollback, moving)
    run_script(APP_ENV, "check", "--workdir", rollback.workdir, "--environment", rollback.environment,
               "--region", rollback.region, *targets.values())
    for service, revision in targets.items():
        aws("ecs", "update-service", "--cluster", rollback.cluster, "--service", service, "--task-definition",
            revision, "--region", rollback.region, stdout=subprocess.DEVNULL)
        print(f"rolling back {service} to {revision}")
    wait_until_stable(rollback, list(targets))
    watch_rollout(rollback, targets)
    print("services stable on the previous revisions")
    record(rollback, APP_ENV, rollback.workdir, moving[0].tag)


def roll_back_from(env: Mapping[str, str]) -> None:
    rollback = configured(env)
    with tempfile.TemporaryDirectory() as workdir:
        rollback.workdir = workdir
        roll_back(rollback)


if __name__ == "__main__":
    raise SystemExit(main(lambda: roll_back_from(os.environ)))
