#!/usr/bin/env python3
"""Checks the settings of the revisions the saas's rollback goes back to, and records them in app_env.

ecs-rollback.sh puts services back on earlier revisions, which run with the settings they were registered with, not
with deploy/app-env.json. So the rollback checks those settings with the deploy's own rules (app_env.py) and runs:

  check   before any service moves, with the ARN of each revision it goes back to: reads the settings of the
          revision's app container (the one named like its family), refuses them as a deploy refuses the file
          (pre's rules, Analytics only in prod's web, one value per policy in the families that go back), wants in
          prod a confirmation (CONFIRM_PROTECTED) for every protected setting that changes against the app_env in
          force, and the Hub filing in the AEAT's production before the saas charges real money;
  record  once the services run those revisions: writes app_env with their settings in the families that went back
          and the settings in force in the rest (saas-cron and saas-migrate keep their revisions).

A refusal exits 1 with ::error:: lines; no message repeats a value. Only the standard library, as app_env.py.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import app_env

SOURCE = "the revisions it goes back to"


def family_of(arn: str, environment: str) -> str:
    """The short family name of a revision ARN (.../erplora-<environment>-<name>:<revision>)."""
    family = arn.rsplit("/", 1)[-1].rsplit(":", 1)[0] if "/" in arn else ""
    name = family[len(f"erplora-{environment}-"):] if family.startswith(f"erplora-{environment}-") else ""
    if name not in app_env.FAMILIES[environment]:
        raise app_env.Refused(f"{arn} is no revision of a family {environment} deploys")
    return name


def target_settings(definition: dict, family: str, arn: str) -> dict[str, str]:
    """The settings of deploy/app-env.json that the revision's app container runs with."""
    containers = [c for c in definition["taskDefinition"].get("containerDefinitions", []) if c.get("name") == family]
    if not containers:
        raise app_env.Refused(f"{arn} has no container {family}")
    return {variable["name"]: variable.get("value") for variable in containers[0].get("environment", [])
            if variable.get("name") in app_env.SETTINGS}


def problems(environment: str, targets: dict, current: dict, confirm: str) -> list[str]:
    """Why the rollback goes no further: the deploy's checks on the families that go back, then the confirmation."""
    found = [problem for family, settings in targets.items()
             for problem in app_env.family_errors(environment, family, settings, SOURCE)]
    found += app_env.agreement_errors(environment, targets, SOURCE)
    return found or app_env.confirmation_errors(environment, targets, current, confirm, SOURCE)


def check(arguments: argparse.Namespace) -> None:
    environment, region = arguments.environment, arguments.region
    parameter = app_env.parameter_of(environment)
    current = app_env.parse_current(app_env.aws(region, "ssm", "get-parameter", "--name", parameter,
                                                "--query", "Parameter.Value", "--output", "text"), parameter)
    targets = {}
    for arn in arguments.targets:
        family = family_of(arn, environment)
        definition = json.loads(app_env.aws(region, "ecs", "describe-task-definition", "--task-definition", arn,
                                            "--output", "json"))
        targets[family] = target_settings(definition, family, arn)
    refused = problems(environment, targets, current, os.environ.get("CONFIRM_PROTECTED", ""))
    if refused:
        raise app_env.Refused(*refused)
    if environment == "prod" and any(s.get("PLATFORM_INVOICING_ENABLED") == "true" for s in targets.values()):
        app_env.check_hub(region)
    (Path(arguments.workdir) / app_env.CHECKED).write_text(json.dumps({"wanted": {**current, **targets},
                                                                      "current": current}))
    if environment == "prod":
        for name, value in app_env.protected_changes(targets, current).items():
            print(f"prod changes {name} to {value}, as confirmed")
    print(f"the {environment} settings of {SOURCE} pass every check")


def record(arguments: argparse.Namespace) -> None:
    parameter = app_env.parameter_of(arguments.environment)
    try:
        app_env.put_settings(arguments.region, parameter, app_env.checked(arguments.workdir)["wanted"])
    except app_env.Refused as refusal:
        raise app_env.Refused(f"the services run the previous revisions, but {parameter} was not written ({refusal}): "
                              "until it is, the revisions ERPlora/aws registers keep the settings from before the "
                              "rollback") from None
    print(f"recorded the settings of the revisions it went back to in {parameter}")


def parser() -> argparse.ArgumentParser:
    main_parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = main_parser.add_subparsers(required=True)
    for name, command, suffix in (("check", check, "; nothing was changed"), ("record", record, "")):
        sub = commands.add_parser(name)
        sub.set_defaults(command=command, suffix=suffix)
        sub.add_argument("--workdir", required=True)
        sub.add_argument("--environment", required=True, choices=sorted(app_env.FAMILIES))
        sub.add_argument("--region", required=True)
        if name == "check":
            sub.add_argument("targets", nargs="+", metavar="ARN")
    return main_parser


def main(argv: list[str] | None = None) -> int:
    return app_env.run(parser(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
