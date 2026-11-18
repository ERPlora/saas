"""Tests of app_env_rollback.py: the checks of the settings a rollback goes back to, and how it records them.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

Only the standard library. How ecs-rollback.sh calls it, with a fake aws CLI, is tested by ecs-rollback.test.sh.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_env
import app_env_rollback
from app_env_test import POLICIES_PRE, POLICIES_PROD, SECRET_VALUE, container, described, settings

TD = "arn:aws:ecs:eu-south-2:123456789012:task-definition"
SAAS = f"{TD}/erplora-prod-saas:10"
WORKER = f"{TD}/erplora-prod-saas-worker:10"


def revision(family: str, environment: dict) -> dict:
    """A revision whose app container, named like the family, runs <environment> next to Terraform's variables."""
    return described(family, [
        container("log-router", "public.ecr.aws/fluent-bit:stable", {"STRIPE_EXPECTED_MODE": "test"}),
        container(family.split("-", 2)[2], "reg.example/erplora/saas:tag-10",
                  {"CACHE_KEY_PREFIX": "saas", "DJANGO_ALLOWED_HOSTS": "erplora.com", **environment},
                  secrets=("STRIPE_SECRET_KEY",)),
    ])


def turned_off(family: str = "saas") -> dict:
    return {**settings()["prod"][family], "PLATFORM_INVOICING_ENABLED": "false"}


class FakeAws:
    """Answers the aws calls of app_env.py from <current> (the app_env in force) and <definitions>, by name or ARN."""

    def __init__(self, current: dict, definitions: dict, put_error: str = ""):
        self.current = current
        self.definitions = definitions
        self.put_error = put_error
        self.calls: list[tuple] = []

    def __call__(self, region: str, *arguments: str) -> str:
        self.calls.append(arguments)
        if arguments[:2] == ("ssm", "get-parameter"):
            return json.dumps(self.current)
        if arguments[:2] == ("ecs", "describe-task-definition"):
            return json.dumps(self.definitions[arguments[arguments.index("--task-definition") + 1]])
        if arguments[:2] == ("ssm", "put-parameter") and self.put_error:
            raise app_env.Refused(f"aws ssm put-parameter failed: {self.put_error}")
        return ""

    def described(self) -> list[str]:
        return [call[call.index("--task-definition") + 1] for call in self.calls if "--task-definition" in call]

    def written(self) -> dict:
        [call] = [call for call in self.calls if call[:2] == ("ssm", "put-parameter")]
        return {"name": call[call.index("--name") + 1], "value": call[call.index("--value") + 1]}


def hub(verifactu: str = "true") -> dict:
    return {f"erplora-prod-{name}": described(f"erplora-prod-{name}", [
        container(name, "reg.example/erplora/hub:tag-3", {"VERIFACTU_PRODUCTION_ENABLED": verifactu})])
        for name in ("hub", "worker")}


class TheFamilyOfATarget(unittest.TestCase):
    def test_the_short_name_of_a_revision_of_the_environment(self):
        self.assertEqual(app_env_rollback.family_of(SAAS, "prod"), "saas")
        self.assertEqual(app_env_rollback.family_of(f"{TD}/erplora-pre-saas-worker:3", "pre"), "saas-worker")

    def test_a_revision_of_another_environment_is_refused(self):
        with self.assertRaises(app_env.Refused) as refused:
            app_env_rollback.family_of(f"{TD}/erplora-pre-saas:10", "prod")
        self.assertIn(f"{TD}/erplora-pre-saas:10 is no revision of a family prod deploys", str(refused.exception))

    def test_a_family_the_environment_does_not_deploy_is_refused(self):
        for arn in (f"{TD}/erplora-pre-saas-cron:4", f"{TD}/erplora-prod-hub:4", "erplora-prod-saas"):
            with self.subTest(arn=arn), self.assertRaises(app_env.Refused):
                app_env_rollback.family_of(arn, "pre" if "-pre-" in arn else "prod")


class TheSettingsOfATarget(unittest.TestCase):
    def test_the_settings_its_app_container_runs_with(self):
        runs = {**POLICIES_PROD, "GA_MEASUREMENT_ID": "G-CHB9NM1C74"}
        self.assertEqual(app_env_rollback.target_settings(revision("erplora-prod-saas", runs), "saas", SAAS), runs)

    def test_terraform_variables_secrets_and_other_containers_are_left_out(self):
        found = app_env_rollback.target_settings(revision("erplora-prod-saas", {}), "saas", SAAS)
        self.assertEqual(found, {})

    def test_a_revision_without_the_container_of_its_family_is_refused(self):
        with self.assertRaises(app_env.Refused) as refused:
            app_env_rollback.target_settings(revision("erplora-prod-saas", POLICIES_PROD), "saas-worker", WORKER)
        self.assertIn(f"{WORKER} has no container saas-worker", str(refused.exception))


class TheChecks(unittest.TestCase):
    def problems(self, targets: dict, confirm: str = "", environment: str = "prod", current: dict | None = None):
        in_force = settings()[environment] if current is None else current
        return app_env_rollback.problems(environment, targets, in_force, confirm)

    def assertRefused(self, problems: list, *fragments: str) -> None:
        self.assertTrue(problems, "the rollback was accepted")
        for fragment in fragments:
            self.assertTrue(any(fragment in problem for problem in problems), f"no problem says {fragment!r}: {problems}")

    def test_the_settings_in_force_pass(self):
        self.assertEqual(self.problems({"saas": settings()["prod"]["saas"]}), [])
        self.assertEqual(self.problems(dict(settings()["pre"]), environment="pre"), [])

    def test_a_target_without_one_of_the_four_policies_is_refused(self):
        target = settings()["prod"]["saas"]
        del target["STRIPE_EXPECTED_MODE"]
        self.assertRefused(self.problems({"saas": target}), "the revisions it goes back to: prod.saas has no STRIPE")

    def test_pre_never_goes_back_to_a_real_charge(self):
        target = {**POLICIES_PRE, "PLATFORM_INVOICING_ENABLED": "true"}
        self.assertRefused(self.problems({"saas-worker": target}, environment="pre"),
                           "pre.saas-worker.PLATFORM_INVOICING_ENABLED must be false in pre")

    def test_google_analytics_only_in_the_web_of_prod(self):
        target = {**POLICIES_PROD, "GA_MEASUREMENT_ID": "G-CHB9NM1C74"}
        self.assertRefused(self.problems({"saas-worker": target}), "prod.saas-worker.GA_MEASUREMENT_ID only goes in")

    def test_the_families_that_go_back_take_the_same_policies(self):
        problems = self.problems({"saas": turned_off(), "saas-worker": settings()["prod"]["saas-worker"]},
                                 confirm="PLATFORM_INVOICING_ENABLED=false")
        self.assertRefused(problems, "sets PLATFORM_INVOICING_ENABLED to false in saas; true in saas-worker")

    def test_prod_wants_each_protected_change_confirmed(self):
        for variable, old in (("PLATFORM_INVOICING_ENABLED", "true"), ("AEAT_PRODUCTION_ENABLED", "true"),
                              ("STRIPE_EXPECTED_MODE", "live")):
            new = "test" if old == "live" else "false"
            current = settings()["prod"]
            for family in ("saas", "saas-worker"):
                current[family][variable] = new
            with self.subTest(variable=variable):
                [problem] = self.problems({"saas": settings()["prod"]["saas"]}, current=current)
                self.assertIn(f"CONFIRM_PROTECTED {variable}={old}", problem)
                self.assertEqual(self.problems({"saas": settings()["prod"]["saas"]}, f"{variable}={old}", current=current),
                                 [])

    def test_turning_the_real_charge_off_needs_a_confirmation_too(self):
        self.assertRefused(self.problems({"saas": turned_off()}), "prod changes PLATFORM_INVOICING_ENABLED to false")
        self.assertEqual(self.problems({"saas": turned_off()}, "PLATFORM_INVOICING_ENABLED=false"), [])

    def test_a_confirmation_that_does_not_match_the_targets_is_refused(self):
        self.assertRefused(self.problems({"saas": settings()["prod"]["saas"]}, "PLATFORM_INVOICING_ENABLED=false"),
                           "CONFIRM_PROTECTED does not match the revisions it goes back to")

    def test_only_the_families_that_go_back_are_compared(self):
        current = settings()["prod"]
        for family in ("saas-cron", "saas-migrate", "saas-worker"):
            current[family]["PLATFORM_INVOICING_ENABLED"] = "false"
        self.assertEqual(self.problems({"saas": settings()["prod"]["saas"]}, current=current), [])

    def test_a_family_the_app_env_lacks_is_a_change(self):
        current = settings()["prod"]
        del current["saas-worker"]
        self.assertRefused(self.problems({"saas-worker": settings()["prod"]["saas-worker"]}, current=current),
                           "confirm it with CONFIRM_PROTECTED")

    def test_pre_needs_no_confirmation(self):
        current = settings()["pre"]
        current["saas"]["PUBLIC_INDEXING_ENABLED"] = "true"
        self.assertEqual(self.problems({"saas": settings()["pre"]["saas"]}, environment="pre", current=current), [])

    def test_no_problem_repeats_a_value(self):
        target = {**POLICIES_PROD, "GA_MEASUREMENT_ID": SECRET_VALUE, "STRIPE_EXPECTED_MODE": SECRET_VALUE}
        problems = self.problems({"saas": target})
        self.assertTrue(problems)
        self.assertFalse([problem for problem in problems if SECRET_VALUE in problem])


class CommandTestCase(unittest.TestCase):
    def setUp(self):
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        self.workdir = workdir.name
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run_command(self, fake: FakeAws, *argv: str, confirm: str = "") -> int:
        with mock.patch.object(app_env, "aws", fake), mock.patch.dict(os.environ, {"CONFIRM_PROTECTED": confirm}), \
                contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err):
            return app_env_rollback.main([*argv[:1], "--workdir", self.workdir, *argv[1:]])

    def check(self, fake: FakeAws, *targets: str, environment: str = "prod", confirm: str = "") -> int:
        return self.run_command(fake, "check", "--environment", environment, "--region", "eu-south-2", *targets,
                                confirm=confirm)

    def record(self, fake: FakeAws, environment: str = "prod") -> int:
        return self.run_command(fake, "record", "--environment", environment, "--region", "eu-south-2")

    def checked(self) -> Path:
        return Path(self.workdir) / app_env.CHECKED


class TheCheckCommand(CommandTestCase):
    def test_it_reads_the_app_env_in_force_and_each_target(self):
        fake = FakeAws(settings()["prod"], {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]), **hub()})
        self.assertEqual(self.check(fake, SAAS), 0, self.err.getvalue())
        self.assertIn(("ssm", "get-parameter", "--name", "/erplora/prod/saas/app_env", "--query", "Parameter.Value",
                       "--output", "text"), fake.calls)
        self.assertIn(SAAS, fake.described())

    def test_after_the_rollback_the_families_that_go_back_take_their_targets_settings(self):
        current = settings()["prod"]
        for family in current:
            current[family]["PUBLIC_INDEXING_ENABLED"] = "false"
        targets = {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]),
                   WORKER: revision("erplora-prod-saas-worker", settings()["prod"]["saas-worker"])}
        self.assertEqual(self.check(FakeAws(current, {**targets, **hub()}), SAAS, WORKER), 0, self.err.getvalue())
        wanted = json.loads(self.checked().read_text())["wanted"]
        self.assertEqual(wanted, {**current, "saas": settings()["prod"]["saas"],
                                  "saas-worker": settings()["prod"]["saas-worker"]})

    def test_a_family_that_stays_keeps_the_settings_in_force(self):
        current = settings()["prod"]
        current["saas-worker"]["PUBLIC_INDEXING_ENABLED"] = "false"
        fake = FakeAws(current, {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]), **hub()})
        self.assertEqual(self.check(fake, SAAS), 0, self.err.getvalue())
        self.assertEqual(json.loads(self.checked().read_text())["wanted"]["saas-worker"], current["saas-worker"])

    def test_a_refusal_leaves_nothing_to_record(self):
        fake = FakeAws(settings()["prod"], {SAAS: revision("erplora-prod-saas", turned_off()), **hub()})
        self.assertEqual(self.check(fake, SAAS), 1)
        self.assertFalse(self.checked().exists())
        self.assertIn("::error::prod changes PLATFORM_INVOICING_ENABLED to false: confirm it with CONFIRM_PROTECTED "
                      "PLATFORM_INVOICING_ENABLED=false", self.err.getvalue())
        self.assertIn("; nothing was changed", self.err.getvalue())

    def test_the_confirmation_comes_from_confirm_protected(self):
        fake = FakeAws(settings()["prod"], {SAAS: revision("erplora-prod-saas", turned_off()), **hub()})
        self.assertEqual(self.check(fake, SAAS, confirm="PLATFORM_INVOICING_ENABLED=false"), 0, self.err.getvalue())
        self.assertIn("prod changes PLATFORM_INVOICING_ENABLED to false, as confirmed", self.out.getvalue())

    def test_a_real_charge_in_prod_reads_the_hubs_latest_revisions(self):
        fake = FakeAws(settings()["prod"], {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]), **hub()})
        self.assertEqual(self.check(fake, SAAS), 0, self.err.getvalue())
        self.assertEqual(sorted(name for name in fake.described() if "-hub" in name or "-worker" in name),
                         ["erplora-prod-hub", "erplora-prod-worker"])

    def test_a_real_charge_while_the_hub_does_not_file_in_production_is_refused(self):
        fake = FakeAws(settings()["prod"], {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]),
                                            **hub("false")})
        self.assertEqual(self.check(fake, SAAS), 1)
        self.assertFalse(self.checked().exists())
        self.assertIn("::error::prod charges real money", self.err.getvalue())

    def test_without_the_real_charge_the_hub_is_not_read(self):
        current = settings()["prod"]
        for family in current:
            current[family]["PLATFORM_INVOICING_ENABLED"] = "false"
        fake = FakeAws(current, {SAAS: revision("erplora-prod-saas", current["saas"])})
        self.assertEqual(self.check(fake, SAAS), 0, self.err.getvalue())
        self.assertEqual(fake.described(), [SAAS])

    def test_pre_never_reads_the_hub(self):
        target = f"{TD}/erplora-pre-saas:10"
        fake = FakeAws(settings()["pre"], {target: revision("erplora-pre-saas", settings()["pre"]["saas"])})
        self.assertEqual(self.check(fake, target, environment="pre"), 0, self.err.getvalue())
        self.assertEqual(fake.described(), [target])

    def test_an_app_env_in_force_that_is_no_object_of_families_is_refused(self):
        fake = FakeAws([], {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"])})
        self.assertEqual(self.check(fake, SAAS), 1)
        self.assertIn("::error::/erplora/prod/saas/app_env is no JSON object of families", self.err.getvalue())


class TheRecordCommand(CommandTestCase):
    def checked_rollback(self, current: dict) -> None:
        fake = FakeAws(current, {SAAS: revision("erplora-prod-saas", settings()["prod"]["saas"]), **hub()})
        self.assertEqual(self.check(fake, SAAS), 0, self.err.getvalue())

    def test_it_writes_what_the_check_passed_compact_with_sorted_keys(self):
        current = settings()["prod"]
        current["saas-cron"]["PUBLIC_INDEXING_ENABLED"] = "false"
        self.checked_rollback(current)
        fake = FakeAws({}, {})
        self.assertEqual(self.record(fake), 0, self.err.getvalue())
        expected = {**current, "saas": settings()["prod"]["saas"]}
        self.assertEqual(fake.written(), {"name": "/erplora/prod/saas/app_env",
                                          "value": json.dumps(expected, sort_keys=True, separators=(",", ":"))})
        self.assertIn("recorded the settings of the revisions it went back to in /erplora/prod/saas/app_env",
                      self.out.getvalue())

    def test_a_failure_to_write_says_the_services_already_went_back(self):
        self.checked_rollback(settings()["prod"])
        self.assertEqual(self.record(FakeAws({}, {}, put_error="AccessDeniedException")), 1)
        self.assertIn("::error::the services run the previous revisions, but /erplora/prod/saas/app_env was not "
                      "written (aws ssm put-parameter failed: AccessDeniedException)", self.err.getvalue())

    def test_without_a_check_nothing_is_written(self):
        fake = FakeAws({}, {})
        with self.assertRaises(FileNotFoundError):
            self.record(fake)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
