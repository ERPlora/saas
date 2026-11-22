"""What the saas's deploy (ecs_deploy.py) and its rollback (ecs_rollback.py) share: how they run aws and the settings'
scripts and stop, how they read what they are given and tell a revision of their environment from another's, and how
they finish: watching the services' rollout and recording the image tag.

A refusal exits 1 after its ::error:: line; an aws call or a settings' script that fails ends the run with its own exit
code (128 + N when signal N killed it). What aws answers is written back byte for byte. Only the standard library: the
workflows run them with the runner's python3.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# This repo deploys the saas; the hub repo keeps its own copy of these scripts.
PROJECT = "saas"
ENVIRONMENTS = ("prod", "pre")
PRIMARY_QUERY = "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]"
# An answer that cannot be read through ends the run with jq's code for it, as when jq read it.
UNREADABLE = 5


class Stop(Exception):
    """Ends the run with an exit code; what it had to say is already said."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def error(line: str) -> None:
    print(f"::error::{line}", file=sys.stderr)


def refusal(line: str) -> Stop:
    error(line)
    return Stop(1)


def program() -> str:
    return os.path.basename(sys.argv[0])


def unreadable(what: str, why: Exception) -> Stop:
    print(f"{program()}: {what} cannot be read: {why}", file=sys.stderr)
    return Stop(UNREADABLE)


def run(command: list[str], stdin: bytes | None = None, stdout=subprocess.PIPE) -> str:
    """Runs a command with its stderr passing through; a failure ends the run with its exit code. Returns what it
    wrote without its trailing newlines, when it is read."""
    try:
        done = subprocess.run(command, input=stdin, stdout=stdout, check=False)
    except FileNotFoundError:
        print(f"{program()}: {command[0]}: command not found", file=sys.stderr)
        raise Stop(127) from None
    if done.returncode != 0:
        raise Stop(done.returncode if done.returncode > 0 else 128 - done.returncode)
    return "" if done.stdout is None else done.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def aws(*arguments: str, stdout=subprocess.PIPE) -> str:
    return run(["aws", *arguments], stdout=stdout)


def run_script(script: Path, *arguments: str, stdin: bytes | None = None, stdout=None) -> None:
    """Runs one of the settings' scripts (app_env.py, app_env_rollback.py) with this python3."""
    run([sys.executable, str(script), *arguments], stdin=stdin, stdout=stdout)


@dataclass
class Release:
    """Where a deploy or a rollback works: its region, environment and cluster, and the seconds of its waits as given
    (the messages say them so)."""

    region: str
    environment: str
    cluster: str
    seconds: dict[str, str]

    @property
    def prod(self) -> bool:
        return self.environment == "prod"

    @property
    def suffix(self) -> str:
        return "" if self.prod else "-pre"

    @property
    def prefix(self) -> str:
        return f"erplora-{self.environment}"

    def seconds_of(self, name: str) -> int:
        return int(self.seconds[name])


def environment_given(env: Mapping[str, str], consequence: str) -> str:
    environment = env.get("ENVIRONMENT", "")
    if environment not in ENVIRONMENTS:
        raise refusal(f"ENVIRONMENT must be prod or pre, not '{environment}'{consequence}")
    return environment


def seconds_given(env: Mapping[str, str], defaults: Mapping[str, str], consequence: str) -> dict[str, str]:
    """Each setting of <defaults> as given, or its default when it is missing or empty; one that is not a number of
    seconds is refused."""
    seconds = {name: env.get(name) or default for name, default in defaults.items()}
    for name, value in seconds.items():
        if not re.fullmatch("[0-9]+", value):
            raise refusal(f"{name} must be a number of seconds, not '{value}'{consequence}")
    return seconds


def arns_listed(listed: str) -> list[str]:
    """The ARNs list-task-definitions answered, as bash's `read -a` read them: the words of its first line, apart by
    spaces and tabs."""
    return [arn for arn in re.split("[ \t]+", listed.split("\n", 1)[0]) if arn]


def own_family_listed(listed: str, family: str) -> bool:
    """Whether list-task-definitions listed a revision of <family> itself, as a family prefix also lists longer
    families."""
    return any(arn.rsplit(":", 1)[0].endswith(f"/{family}") for arn in arns_listed(listed))


def exists(release: Release, name: str, consequence: str) -> bool:
    """Whether the family of <name>, which may not exist yet, has an ACTIVE revision; says so when it has none."""
    family = f"{release.prefix}-{name}"
    try:
        listed = aws("ecs", "list-task-definitions", "--family-prefix", family, "--status", "ACTIVE",
                     "--region", release.region, "--query", "taskDefinitionArns", "--output", "text")
    except Stop:
        raise refusal(f"could not look for {family}{consequence}") from None
    if own_family_listed(listed, family):
        return True
    print(f"::warning::{family} does not exist yet: skipped")
    return False


def key(value: object, name: str) -> object:
    """jq's `.name`: null on null; anything but an object or null cannot be read through."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    raise TypeError(f"cannot index {type(value).__name__} with {name!r}")


def tagged(found: dict, environment: str) -> bool:
    """jq's `any(.tags[]?; .key == "Environment" and .value == $environment)`: a tag that is neither an object nor null,
    met before the one that matches, could not be read and refuses the revision."""
    tags = found.get("tags")
    tags = list(tags.values()) if isinstance(tags, dict) else tags if isinstance(tags, list) else []
    for tag in tags:
        if tag is None:
            continue
        if not isinstance(tag, dict):
            return False
        if tag.get("key") == "Environment" and tag.get("value") == environment:
            return True
    return False


def of_its_environment(described: str, environment: str) -> bool:
    """Whether a described revision carries the tag Environment=<environment> and the task and execution roles of
    that environment; an answer that is not one JSON object is not."""
    try:
        found = json.loads(described)
    except ValueError:
        return False
    if not isinstance(found, dict) or not tagged(found, environment):
        return False
    definition = found.get("taskDefinition")
    role = re.compile(rf"^arn:aws[a-z-]*:iam::[0-9]{{12}}:role/erplora-{environment}-")
    return isinstance(definition, dict) and all(
        isinstance(arn, str) and role.search(arn) is not None
        for arn in (definition.get("taskRoleArn"), definition.get("executionRoleArn")))


def described_in_its_environment(release: Release, revision: str, consequence: str) -> str:
    """Reads <revision> (an ARN or a family's latest) with its tags and refuses one of another environment:
    ecs:RegisterTaskDefinition takes no resource, so another environment's deploy role could have left it."""
    described = aws("ecs", "describe-task-definition", "--task-definition", revision, "--include", "TAGS",
                    "--region", release.region, "--output", "json")
    if not of_its_environment(described, release.environment):
        environment = release.environment
        raise refusal(f"{revision} is not a {environment} revision (it needs the tag Environment={environment} and "
                      f"the roles erplora-{environment}-*){consequence}")
    return described


def primary(release: Release, service: str) -> tuple[str, str]:
    """The task definition and the rollout state of the service's PRIMARY deployment, split from aws's line as bash's
    `read` split it: the first word, and the rest of the line."""
    line = aws("ecs", "describe-services", "--cluster", release.cluster, "--services", service,
               "--region", release.region, "--query", PRIMARY_QUERY, "--output", "text").split("\n", 1)[0]
    words = re.split("[ \t]+", line.strip(" \t"), maxsplit=1)
    return words[0], words[1] if len(words) > 1 else ""


def wait_until_stable(release: Release, services: list[str]) -> None:
    aws("ecs", "wait", "services-stable", "--cluster", release.cluster, "--region", release.region,
        "--services", *services, stdout=None)


def still_rolling_out(release: Release, pending: list[str], targets: dict[str, str]) -> list[str]:
    """The services of <pending> whose rollout is still in progress; one that runs another revision, or whose rollout
    FAILED, ends the run once every service was read."""
    in_progress, failed = [], False
    for service in pending:
        task_definition, state = primary(release, service)
        if task_definition != targets[service] or state == "FAILED":
            error(f"{service} runs {task_definition} ({state}), not {targets[service]}; rolled back by the circuit "
                  "breaker? See the service events")
            failed = True
        elif state != "COMPLETED":
            in_progress.append(service)
    if failed:
        raise Stop(1)
    return in_progress


def watch_rollout(release: Release, targets: dict[str, str]) -> None:
    """services-stable can return while a PRIMARY deployment is still IN_PROGRESS: polls the services whose rollout
    has not completed yet (<targets>: service -> the revision it must run), all of them on the same clock."""
    pending = list(targets)
    waited = 0
    while True:
        pending = still_rolling_out(release, pending, targets)
        if not pending:
            return
        if waited >= release.seconds_of("ROLLOUT_TIMEOUT_SECONDS"):
            for service in pending:
                error(f"rollout of {service} did not complete in {release.seconds['ROLLOUT_TIMEOUT_SECONDS']} s; see "
                      "the service events")
            raise Stop(1)
        time.sleep(release.seconds_of("POLL_SECONDS"))
        waited += release.seconds_of("POLL_SECONDS")


def record(release: Release, settings_script: Path, workdir: str, image_tag: str) -> None:
    """Records the checked settings in /erplora/<environment>/saas/app_env and the tag in .../image_tag, so the
    revisions Terraform registers, and with them the scheduled tasks, keep both (ERPlora/aws README)."""
    run_script(settings_script, "record", "--workdir", workdir, "--environment", release.environment,
               "--region", release.region)
    parameter = f"/erplora/{release.environment}/{PROJECT}/image_tag"
    aws("ssm", "put-parameter", "--name", parameter, "--value", image_tag, "--type", "String", "--overwrite",
        "--region", release.region, stdout=subprocess.DEVNULL)
    print(f"recorded {image_tag} in {parameter}")


def main(work: Callable[[], None]) -> int:
    """Runs <work> and returns its exit code. Each line goes out as it is written, among what aws and the settings'
    scripts write, and as the bytes it was given."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape", line_buffering=True)
    try:
        work()
    except Stop as stop:
        return stop.code
    return 0
