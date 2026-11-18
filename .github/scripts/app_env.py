#!/usr/bin/env python3
"""Checks the saas's deploy/app-env.json and applies it to the task definitions a deploy registers.

deploy/app-env.json holds the saas's settings that are no secret, by environment and family:
{"prod": {"saas": {"VAR": "text"}, ...}, "pre": {...}}. ERPlora/aws keeps everything else, the secrets included,
and its revisions read back what the last deploy wrote to /erplora/<environment>/saas/app_env. ecs-deploy.sh runs:

  check     before anything is registered: reads the file of the commit it deploys, checks it, reads the app_env
            in force and, in prod, wants a confirmation for every protected setting that changes, and the Hub
            filing in the AEAT's production before the saas charges real money;
  revision  for each family: the revision to register, from the latest ACTIVE one (stdin), with the new image
            and the family's settings;
  record    once the services run the new revisions: writes the settings to app_env.

A refusal exits 1 with ::error:: lines. No message repeats a value of the file: only names, and values a check has
already found to be one of a few known words.

A commit from before the file (an older release, deployed again) keeps the settings in force.

Only the standard library: the deploy runs it with the runner's python3, or with the one of the machine that deploys.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = "saas"
FILE = "deploy/app-env.json"
# The families each environment deploys (ERPlora/aws deploy_projects); pre has no saas-cron.
FAMILIES = {
    "prod": ("saas", "saas-cron", "saas-migrate", "saas-worker"),
    "pre": ("saas", "saas-migrate", "saas-worker"),
}
BOOLEAN = (re.compile(r"true|false"), "true or false")
# Every setting the file may carry, with the values it takes.
SETTINGS = {
    "AEAT_PRODUCTION_ENABLED": BOOLEAN,
    "PLATFORM_INVOICING_ENABLED": BOOLEAN,
    "PUBLIC_INDEXING_ENABLED": BOOLEAN,
    "STRIPE_EXPECTED_MODE": (re.compile(r"live|test"), "live or test"),
    "GA_MEASUREMENT_ID": (re.compile(r"G-[0-9A-Z]{4,16}"), "a measurement ID of Google Analytics (G-...)"),
    "MICROSOFT_STORE_APP_ID": (re.compile(r"[0-9A-Z]{12}"), "the 12-character product ID of the Store listing"),
}
# Explicit in every family, with one value per environment.
POLICIES = ("AEAT_PRODUCTION_ENABLED", "PLATFORM_INVOICING_ENABLED", "PUBLIC_INDEXING_ENABLED", "STRIPE_EXPECTED_MODE")
# Only the web renders the public pages: Analytics measures prod's visits alone.
ONLY_IN = {
    "GA_MEASUREMENT_ID": {("prod", "saas")},
    "MICROSOFT_STORE_APP_ID": {("prod", "saas"), ("pre", "saas")},
}
# pre never charges real money, never files in the AEAT's production and stays out of the search engines.
PRE_POLICIES = {
    "AEAT_PRODUCTION_ENABLED": "false",
    "PLATFORM_INVOICING_ENABLED": "false",
    "PUBLIC_INDEXING_ENABLED": "false",
    "STRIPE_EXPECTED_MODE": "test",
}
# In prod, changing one of these needs CONFIRM_PROTECTED (confirm_protected of the deploy and rollback workflows).
PROTECTED = ("AEAT_PRODUCTION_ENABLED", "PLATFORM_INVOICING_ENABLED", "STRIPE_EXPECTED_MODE")
# What every container of the saas image has once merged: without a cache prefix or a Stripe mode the saas refuses to
# start outside DEBUG (config/settings/core.py). CACHE_KEY_PREFIX comes from ERPlora/aws.
REQUIRED = ("CACHE_KEY_PREFIX", *POLICIES)
# The Hub's families that seal and send ERPlora's invoices, each in a container of the family's name.
HUB_FAMILIES = ("hub", "worker")
NAME = re.compile(r"[A-Z][A-Z0-9_]*")
SECRET_NAME = re.compile(r"SECRET|PASSW|TOKEN|PRIVATE|CREDENTIAL|(^|_)KEY$")
CONFIRMATION = re.compile(r"([A-Z][A-Z0-9_]*)=(\S+)")
READ_ONLY = ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt",
             "registeredBy", "deregisteredAt")
CHECKED = "app-env.json"


class Refused(Exception):
    """Why the deploy goes no further."""

    def __init__(self, *problems: str):
        super().__init__("; ".join(problems))
        self.problems = problems


def file_errors(settings: object) -> list[str]:
    """Everything wrong with the file, in both environments: a deploy to one also checks the other."""
    if not isinstance(settings, dict):
        return [f"{FILE} must be an object of the environments {' and '.join(FAMILIES)}"]
    problems = [f"{FILE}: {name} is no environment ({' or '.join(FAMILIES)})" for name in settings if name not in FAMILIES]
    for environment in FAMILIES:
        if environment in settings:
            problems += environment_errors(environment, settings[environment])
        else:
            problems.append(f"{FILE} has no {environment}: it lists every environment")
    return problems


def environment_errors(environment: str, families: object) -> list[str]:
    expected = FAMILIES[environment]
    if not isinstance(families, dict):
        return [f"{FILE}: {environment} must be an object of its families ({', '.join(expected)})"]
    problems = [f"{FILE}: {environment}.{name} is no family {environment} deploys ({', '.join(expected)})"
                for name in families if name not in expected]
    for family in expected:
        if family in families:
            problems += family_errors(environment, family, families[family])
        else:
            problems.append(f"{FILE}: {environment} has no {family}: it lists every family {environment} deploys")
    return problems + agreement_errors(environment, families)


def family_errors(environment: str, family: str, variables: object, source: str = FILE) -> list[str]:
    where = f"{source}: {environment}.{family}"
    if not isinstance(variables, dict):
        return [f"{where} must be an object of variables"]
    problems = [f"{where} has no {policy}: the four policies are explicit in every family"
                for policy in POLICIES if policy not in variables]
    for name, value in variables.items():
        problem = name_problem(environment, family, name) or value_problem(environment, name, value)
        if problem:
            problems.append(f"{where}.{name} {problem}")
    return problems


def name_problem(environment: str, family: str, name: str) -> str | None:
    if not NAME.fullmatch(name):
        return "is no environment variable name (A-Z, 0-9 and _)"
    if SECRET_NAME.search(name):
        return "looks like a secret: secrets stay in ERPlora/aws, never in this public file"
    if name not in SETTINGS:
        return f"is no setting of the saas's deploy ({', '.join(SETTINGS)}); the rest belongs to ERPlora/aws"
    places = ONLY_IN.get(name, {(environment, family)})
    if (environment, family) not in places:
        return f"only goes in {' and '.join(f'{e}.{f}' for e, f in sorted(places))}"
    return None


def value_problem(environment: str, name: str, value: object) -> str | None:
    if not isinstance(value, str):
        return "must be text"
    pattern, description = SETTINGS[name]
    if not pattern.fullmatch(value):
        return f"must be {description}"
    if environment == "pre" and PRE_POLICIES.get(name, value) != value:
        return f"must be {PRE_POLICIES[name]} in pre, which never charges, files in production nor is indexed"
    return None


def valid(name: str, value: object) -> bool:
    return isinstance(value, str) and name in SETTINGS and SETTINGS[name][0].fullmatch(value) is not None


def agreement_errors(environment: str, families: dict, source: str = FILE) -> list[str]:
    """A policy takes one value in every family of an environment (its valid values only: they are known words)."""
    problems = []
    for policy in POLICIES:
        found: dict[str, list[str]] = {}
        for family, variables in families.items():
            value = variables.get(policy) if isinstance(variables, dict) else None
            if family in FAMILIES[environment] and valid(policy, value):
                found.setdefault(value, []).append(family)
        if len(found) > 1:
            where = "; ".join(f"{value} in {', '.join(names)}" for value, names in sorted(found.items()))
            problems.append(f"{source}: {environment} sets {policy} to {where}: every family takes the same value")
    return problems


def protected_settings(wanted: dict) -> dict[str, str]:
    """The value the file gives each protected setting: the same in every family, once the file is checked."""
    return {name: variables[name] for variables in wanted.values() for name in PROTECTED if name in variables}


def protected_changes(wanted: dict, current: dict) -> dict[str, str]:
    """The protected settings whose value in the file differs from the app_env in force in some family."""
    return {name: value for name, value in protected_settings(wanted).items()
            if any(current.get(family, {}).get(name) != value for family in wanted)}


def confirmation_errors(environment: str, wanted: dict, current: dict, confirm: str, source: str = FILE) -> list[str]:
    """CONFIRM_PROTECTED: VAR=value pairs, by commas or spaces, each one a protected setting at the wanted value."""
    setting = protected_settings(wanted)
    confirmed = {}
    problems = []
    for entry in filter(None, re.split(r"[\s,]+", confirm)):
        pair = CONFIRMATION.fullmatch(entry)
        if not pair:
            problems.append("CONFIRM_PROTECTED takes VAR=value pairs, separated by commas or spaces")
        elif pair[1] not in PROTECTED:
            problems.append(f"CONFIRM_PROTECTED names {pair[1]}, which is no protected setting ({', '.join(PROTECTED)})")
        elif pair[2] != setting.get(pair[1]):
            problems.append(f"CONFIRM_PROTECTED does not match {source}, which sets {pair[1]}={setting.get(pair[1])}")
        else:
            confirmed[pair[1]] = pair[2]
    if environment == "prod":
        problems += [f"prod changes {name} to {value}: confirm it with CONFIRM_PROTECTED {name}={value} "
                     "(the workflow's confirm_protected)"
                     for name, value in protected_changes(wanted, current).items() if confirmed.get(name) != value]
    return problems


def names_of(container: dict) -> set[str]:
    return {variable["name"] for variable in container.get("environment", []) + container.get("secrets", [])}


def merged(family: str, container: dict, wanted: dict, current: dict) -> list[dict]:
    """The container's environment with the family's settings: those of the app_env in force go, the file's come."""
    secrets = {secret["name"] for secret in container.get("secrets", [])}
    terraform = (names_of(container) - set(current)) | secrets
    theirs = sorted(set(wanted) & terraform)
    if theirs:
        raise Refused(f"{family}: ERPlora/aws sets {', '.join(theirs)} in this family (its revision has it and the "
                      f"app_env in force does not): one owner per variable, so take it out of {FILE} or out of "
                      "ERPlora/aws first")
    kept = [variable for variable in container.get("environment", [])
            if variable["name"] not in current and variable["name"] not in wanted]
    added = [{"name": name, "value": value} for name, value in wanted.items()]
    return sorted(kept + added, key=lambda variable: variable["name"])


def revision(base: dict, wanted: dict, current: dict, image: str, project_image: str) -> dict:
    """The revision to register from the latest ACTIVE one: new image and settings in the containers of the image."""
    definition = copy.deepcopy(base["taskDefinition"])
    family = definition.get("family", "")
    ours = [c for c in definition.get("containerDefinitions", []) if str(c.get("image") or "").startswith(project_image)]
    if not ours:
        raise Refused(f"{family} has no container of the image {project_image}<tag>")
    for container in ours:
        container["image"] = image
        container["environment"] = merged(family, container, wanted, current)
    missing = sorted({name for container in ours for name in REQUIRED if name not in names_of(container)})
    if missing:
        raise Refused(f"{family} has no {' '.join(missing)} in the environment or secrets of its saas container "
                      "(apply ERPlora/aws first)")
    for field in READ_ONLY:
        definition.pop(field, None)
    if base.get("tags"):
        definition["tags"] = base["tags"]
    return definition


def files_in_production(definition: dict, name: str) -> bool:
    """Whether the container named <name> runs with VERIFACTU_PRODUCTION_ENABLED=true in its environment."""
    return any(
        container.get("name") == name
        and any(variable.get("name") == "VERIFACTU_PRODUCTION_ENABLED" and variable.get("value") == "true"
                for variable in container.get("environment", []))
        for container in definition["taskDefinition"].get("containerDefinitions", []))


def parse_current(text: str, parameter: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        value = None
    if not (isinstance(value, dict) and all(
            isinstance(variables, dict) and all(isinstance(v, str) for v in variables.values())
            for variables in value.values())):
        raise Refused(f"{parameter} is no JSON object of families with text settings: write back its last good value")
    return value


def aws(region: str, *arguments: str) -> str:
    result = subprocess.run(["aws", *arguments, "--region", region], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise Refused(f"aws {' '.join(arguments[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def read_file(commit: str) -> dict | None:
    """The checked file of the commit; None when the commit is from before the file."""
    result = subprocess.run(["git", "cat-file", "blob", f"{commit}:{FILE}"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        known = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True, check=False)
        if known.returncode != 0:
            raise Refused(f"{commit} is no commit of this checkout")
        return None
    try:
        settings = json.loads(result.stdout)
    except ValueError as error:
        raise Refused(f"{FILE} of {commit} is no JSON ({error.msg}, line {error.lineno})") from error
    problems = file_errors(settings)
    if problems:
        raise Refused(*problems)
    return settings


def check_hub(region: str) -> None:
    problems = []
    for name in HUB_FAMILIES:
        family = f"erplora-prod-{name}"
        definition = json.loads(aws(region, "ecs", "describe-task-definition", "--task-definition", family,
                                    "--output", "json"))
        if not files_in_production(definition, name):
            problems.append(f"prod charges real money (PLATFORM_INVOICING_ENABLED=true) only while the Hub files in "
                            f"the AEAT's production, and the latest revision of {family} has no "
                            f"VERIFACTU_PRODUCTION_ENABLED=true in its {name} container: deploy the Hub with it first")
    if problems:
        raise Refused(*problems)


def parameter_of(environment: str) -> str:
    return f"/erplora/{environment}/{PROJECT}/app_env"


def check(arguments: argparse.Namespace) -> None:
    environment = arguments.environment
    settings = read_file(arguments.commit)
    parameter = parameter_of(environment)
    current = parse_current(aws(arguments.region, "ssm", "get-parameter", "--name", parameter,
                                "--query", "Parameter.Value", "--output", "text"), parameter)
    if settings is None:
        if environment_errors(environment, current):
            raise Refused(f"{arguments.commit} has no {FILE} and the settings in force ({parameter}) do not pass its "
                          "checks: deploy a commit that has the file")
        print(f"::warning::{arguments.commit} has no {FILE}: the deploy keeps the settings in force", file=sys.stderr)
    wanted = settings[environment] if settings else current
    problems = confirmation_errors(environment, wanted, current, os.environ.get("CONFIRM_PROTECTED", ""))
    if problems:
        raise Refused(*problems)
    if environment == "prod" and any(v.get("PLATFORM_INVOICING_ENABLED") == "true" for v in wanted.values()):
        check_hub(arguments.region)
    (Path(arguments.workdir) / CHECKED).write_text(json.dumps({"wanted": wanted, "current": current}))
    if environment == "prod":
        for name, value in protected_changes(wanted, current).items():
            print(f"prod changes {name} to {value}, as confirmed")
    print(f"{FILE} of {arguments.commit}: the {environment} settings pass every check")


def checked(workdir: str) -> dict:
    return json.loads((Path(workdir) / CHECKED).read_text())


def revise(arguments: argparse.Namespace) -> None:
    settings = checked(arguments.workdir)
    base = json.load(sys.stdin)
    new = revision(base, settings["wanted"][arguments.family], settings["current"].get(arguments.family, {}),
                   arguments.image, arguments.project_image)
    json.dump(new, sys.stdout)


def put_settings(region: str, parameter: str, wanted: dict) -> None:
    """Writes <wanted> to app_env as ERPlora/aws reads it: compact JSON with its keys sorted."""
    value = json.dumps(wanted, sort_keys=True, separators=(",", ":"))
    aws(region, "ssm", "put-parameter", "--name", parameter, "--value", value, "--type", "String", "--overwrite")


def record(arguments: argparse.Namespace) -> None:
    parameter = parameter_of(arguments.environment)
    try:
        put_settings(arguments.region, parameter, checked(arguments.workdir)["wanted"])
    except Refused as refusal:
        raise Refused(f"the services run the new revisions, but {parameter} was not written ({refusal}): run the "
                      "deploy again, or the revisions ERPlora/aws registers keep the settings in force before") from None
    print(f"recorded the {arguments.environment} settings of {FILE} in {parameter}")


def command_parser(doc: str, commands: tuple) -> tuple[argparse.ArgumentParser, dict]:
    """A command line of subcommands, from (name, function, suffix of its errors): each takes --workdir."""
    main_parser = argparse.ArgumentParser(description=doc.splitlines()[0])
    subparsers = main_parser.add_subparsers(required=True)
    subs = {}
    for name, command, suffix in commands:
        subs[name] = subparsers.add_parser(name)
        subs[name].set_defaults(command=command, suffix=suffix)
        subs[name].add_argument("--workdir", required=True)
    return main_parser, subs


def add_target(sub: argparse.ArgumentParser) -> None:
    """The environment and the region a subcommand reads or writes."""
    sub.add_argument("--environment", required=True, choices=sorted(FAMILIES))
    sub.add_argument("--region", required=True)


def parser() -> argparse.ArgumentParser:
    main_parser, subs = command_parser(__doc__, (("check", check, "; nothing was registered"),
                                                 ("revision", revise, "; nothing was registered"),
                                                 ("record", record, "")))
    for name in ("family", "image", "project-image"):
        subs["revision"].add_argument(f"--{name}", required=True)
    add_target(subs["check"])
    add_target(subs["record"])
    subs["check"].add_argument("--commit", required=True)
    return main_parser


def run(main_parser: argparse.ArgumentParser, argv: list[str] | None) -> int:
    """Runs the command of <argv>: a refusal prints its ::error:: lines, each with the command's suffix."""
    arguments = main_parser.parse_args(argv)
    try:
        arguments.command(arguments)
    except Refused as refusal:
        for problem in refusal.problems:
            print(f"::error::{problem}{arguments.suffix}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
