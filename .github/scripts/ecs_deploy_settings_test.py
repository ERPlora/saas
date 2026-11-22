"""Tests of ecs_deploy.py: the settings of deploy/app-env.json a deploy checks, applies and records (app_env.py).

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes and the checkout are ecs_deploy_test.py's.
"""

from __future__ import annotations

import json
import re
import unittest

from ecs_deploy_test import DeployCase, one


class SettingsCase(DeployCase):
    def env_of(self, family: str, name: str) -> dict:
        """The environment registered for that container."""
        containers = self.registered()[family]["containerDefinitions"]
        return {e["name"]: e["value"] for c in containers if c["name"] == name for e in c["environment"]}

    def file_env(self, environment: str, family: str) -> dict:
        """The file's settings of that family, with the cache prefix the fixtures give."""
        return {**self.file()[environment][family], "CACHE_KEY_PREFIX": "x"}

    def recorded(self, environment: str) -> dict | None:
        """The app_env a deploy wrote, or None."""
        written = self.lines(f"^ssm put-parameter --name /erplora/{environment}/saas/app_env --value ")
        return json.loads(re.search(r" --value (\S*) ", self.calls()[written[0] - 1])[1]) if written else None

    def in_force_now(self, environment: str = "prod") -> dict:
        return json.loads((self.fixtures / f"app_env.{environment}.json").read_text())


class FileSettingsTest(SettingsCase):
    def test_each_family_gets_its_settings_and_they_are_recorded_after_the_rollout(self):
        self.assertEqual(0, self.deploy())
        self.assertTrue(self.called("^ssm get-parameter --name /erplora/prod/saas/app_env --query Parameter.Value "
                                    "--output text --region eu-south-2$"))
        self.assertLess(self.line_of("ssm get-parameter"), self.line_of("register-task-definition"))
        for family in ("saas", "saas-cron", "saas-migrate"):
            self.assertEqual(self.file_env("prod", family), self.env_of(f"erplora-prod-{family}", family))
        self.assertEqual("G-CHB9NM1C74", self.env_of("erplora-prod-saas", "saas")["GA_MEASUREMENT_ID"])
        cron = self.env_of("erplora-prod-saas-cron", "saas-cron")
        self.assertFalse({"GA_MEASUREMENT_ID", "MICROSOFT_STORE_APP_ID"} & set(cron))
        containers = self.registered()["erplora-prod-saas"]["containerDefinitions"]
        self.assertEqual([False, False, False], ["environment" in c for c in containers if c["name"] != "saas"])
        self.assertEqual(self.file()["prod"], self.recorded("prod"))
        app_env = self.line_of("/erplora/prod/saas/app_env --value")
        self.assertGreater(app_env, self.last_line_of("describe-services .*deployments"))
        self.assertLess(app_env, self.line_of("/erplora/prod/saas/image_tag"))
        self.assertIn("recorded the prod settings of deploy/app-env.json in /erplora/prod/saas/app_env", self.out)

    def test_the_file_is_the_deployed_commits_and_a_plain_setting_needs_no_confirmation(self):
        self.settings(lambda s: [family.update(PUBLIC_INDEXING_ENABLED="false") for family in s["prod"].values()])
        self.assertEqual(0, self.deploy())
        self.assertEqual("false", self.env_of("erplora-prod-saas", "saas")["PUBLIC_INDEXING_ENABLED"])
        self.assertEqual("false", self.recorded("prod")["saas"]["PUBLIC_INDEXING_ENABLED"])
        self.git("tag", "-f", "abc123", "HEAD~1")
        self.assertEqual(0, self.deploy())
        self.assertEqual("true", self.env_of("erplora-prod-saas-cron", "saas-cron")["PUBLIC_INDEXING_ENABLED"])

    def test_a_commit_from_before_the_file_keeps_the_settings_in_force(self):
        self.git("rm", "-q", "deploy/app-env.json")
        self.commit_settings()
        in_force = self.in_force_now()
        for family in in_force.values():
            family["PUBLIC_INDEXING_ENABLED"] = "false"
        self.in_force("prod", in_force)
        self.assertEqual(0, self.deploy())
        self.assertEqual("false", self.env_of("erplora-prod-saas", "saas")["PUBLIC_INDEXING_ENABLED"])
        self.assertEqual(in_force, self.recorded("prod"))
        self.assertIn("::warning::abc123 has no deploy/app-env.json: the deploy keeps the settings in force", self.out)
        del in_force["saas-cron"]
        self.in_force("prod", in_force)
        self.deploy()
        self.assertNothingRegistered()
        self.assertIn("::error::abc123 has no deploy/app-env.json and the settings in force (/erplora/prod/saas/app_env) "
                      "do not pass its checks", self.out)

    def test_a_file_that_breaks_a_rule_deploys_nothing(self):
        for change, error in (
                (lambda s: s["pre"]["saas"].update(GA_MEASUREMENT_ID="G-CHB9NM1C74"),
                 "deploy/app-env.json: pre.saas.GA_MEASUREMENT_ID only goes in prod.saas; nothing was registered"),
                (lambda s: s["prod"]["saas"].update(STRIPE_SECRET_KEY="never-print-this-value-0451"),
                 "deploy/app-env.json: prod.saas.STRIPE_SECRET_KEY looks like a secret"),
                (lambda s: s["prod"]["saas-cron"].update(PUBLIC_INDEXING_ENABLED=True),
                 "deploy/app-env.json: prod.saas-cron.PUBLIC_INDEXING_ENABLED must be text"),
                (lambda s: s["prod"].update(hub=s["prod"]["saas-cron"]),
                 "deploy/app-env.json: prod.hub is no family prod deploys")):
            self.setUp()
            self.settings(change)
            self.deploy()
            self.assertNothingRegistered()
            self.assertIn(f"::error::{error}", self.out)
            self.assertNotIn("never-print-this-value-0451", self.out)
        self.setUp()
        self.settings(lambda s: s["pre"]["saas"].update(STRIPE_EXPECTED_MODE="live"))
        self.deploy(ENVIRONMENT="pre")
        self.assertNothingRegistered()
        self.assertIn("::error::deploy/app-env.json: pre.saas.STRIPE_EXPECTED_MODE must be test in pre", self.out)

    def test_a_commit_or_a_file_it_cannot_read_deploys_nothing(self):
        self.deploy(IMAGE_TAG="fedcba9")
        self.assertNothingRegistered()
        self.assertIn("::error::fedcba9 is no commit of this checkout; nothing was registered", self.out)
        (self.repo / "deploy" / "app-env.json").write_text('{"prod": ')
        self.commit_settings()
        self.deploy()
        self.assertNothingRegistered()
        self.assertIn("::error::deploy/app-env.json of abc123 is no JSON", self.out)

    def test_settings_in_force_it_cannot_read_deploy_nothing(self):
        self.deploy(FAKE_APP_ENV_FAILURE="AccessDeniedException")
        self.assertNothingRegistered()
        self.assertRegex(self.out, "::error::aws ssm get-parameter failed: .*AccessDeniedException.*; nothing was "
                                   "registered")
        self.in_force("prod", [])
        self.deploy()
        self.assertNothingRegistered()
        self.assertIn("::error::/erplora/prod/saas/app_env is no JSON object of families", self.out)

    def test_an_app_env_that_cannot_be_written_fails_after_the_rollout_and_records_no_tag(self):
        self.assertNotEqual(0, self.deploy(FAKE_PUT_FAILURE="/app_env"))
        self.assertFalse(self.called("image_tag"))
        self.assertIn("::error::the services run the new revisions, but /erplora/prod/saas/app_env was not written",
                      self.out)

    def test_pre_reads_and_records_its_own_settings(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        self.assertTrue(self.called("^ssm get-parameter --name /erplora/pre/saas/app_env "))
        self.assertEqual(self.file()["pre"], self.recorded("pre"))
        self.assertEqual(self.file_env("pre", "saas"), self.env_of("erplora-pre-saas", "saas"))


class OneOwnerTest(SettingsCase):
    """ERPlora/aws passes the settings on from app_env and never sets them itself, so one the latest revision has and
    the app_env in force lacks was left by a rollback, or by a deploy that failed after registering."""

    def after_rollback(self) -> None:
        store = [{"name": "CACHE_KEY_PREFIX", "value": "saas"}, {"name": "MICROSOFT_STORE_APP_ID", "value": "9P5C0XP1GS69"}]
        self.fixture("erplora-prod-saas", one("saas", "saas:bootstrap", environment=store))
        in_force = self.in_force_now()
        del in_force["saas"]["MICROSOFT_STORE_APP_ID"]
        self.in_force("prod", in_force)

    def test_the_file_decides_after_a_rollback(self):
        self.after_rollback()
        self.assertEqual(0, self.deploy())
        self.assertEqual("9P5C0XP1GS69", self.env_of("erplora-prod-saas", "saas")["MICROSOFT_STORE_APP_ID"])
        self.assertEqual("9P5C0XP1GS69", self.recorded("prod")["saas"]["MICROSOFT_STORE_APP_ID"])
        self.setUp()
        self.after_rollback()
        self.settings(lambda s: s["prod"]["saas"].pop("MICROSOFT_STORE_APP_ID"))
        self.assertEqual(0, self.deploy())
        self.assertNotIn("MICROSOFT_STORE_APP_ID", self.env_of("erplora-prod-saas", "saas"))
        self.assertNotIn("MICROSOFT_STORE_APP_ID", self.recorded("prod")["saas"])

    def test_a_setting_erplora_aws_gives_as_a_secret_deploys_nothing(self):
        self.fixture("erplora-prod-saas", one("saas", "saas:bootstrap", environment=[
            {"name": "CACHE_KEY_PREFIX", "value": "saas"}], secrets=[
            {"name": "MICROSOFT_STORE_APP_ID", "valueFrom": "arn:secret:store"}]))
        self.deploy()
        self.assertNothingRegistered()
        self.assertIn("::error::erplora-prod-saas: ERPlora/aws sets MICROSOFT_STORE_APP_ID", self.out)


class ProtectedSettingsTest(SettingsCase):
    """Changing the real charge, the AEAT's production or Stripe's mode in prod needs CONFIRM_PROTECTED (the deploy
    workflow's confirm_protected), the exact VAR=value of the file; without it nothing is registered."""

    def change_all(self, variable: str, new: str) -> None:
        self.settings(lambda s: [family.update({variable: new}) for family in s["prod"].values()])

    def test_a_protected_change_needs_its_exact_confirmation(self):
        for change in ("PLATFORM_INVOICING_ENABLED=false", "AEAT_PRODUCTION_ENABLED=false", "STRIPE_EXPECTED_MODE=test"):
            variable, new = change.split("=")
            self.setUp()
            self.change_all(variable, new)
            self.deploy()
            self.assertNothingRegistered()
            self.assertIn(f"::error::prod changes {variable} to {new}: confirm it with CONFIRM_PROTECTED {change} ",
                          self.out)
            self.assertEqual(0, self.deploy(CONFIRM_PROTECTED=change))
            self.assertIn(f"prod changes {variable} to {new}, as confirmed", self.out)
            self.assertEqual(new, self.env_of("erplora-prod-saas-cron", "saas-cron")[variable])
            self.assertEqual(new, self.recorded("prod")["saas-cron"][variable])

    def test_another_value_confirmed_deploys_nothing_and_no_real_charge_reads_no_hub(self):
        self.change_all("PLATFORM_INVOICING_ENABLED", "false")
        self.deploy(CONFIRM_PROTECTED="PLATFORM_INVOICING_ENABLED=true")
        self.assertNothingRegistered()
        self.assertIn("::error::CONFIRM_PROTECTED does not match deploy/app-env.json, which sets "
                      "PLATFORM_INVOICING_ENABLED=false", self.out)
        self.assertEqual(0, self.deploy(CONFIRM_PROTECTED="PLATFORM_INVOICING_ENABLED=false"))
        self.assertFalse(self.called("erplora-prod-hub"))


class RealChargeTest(SettingsCase):
    def test_prod_charges_real_money_only_with_the_hub_filing_in_production(self):
        for family in ("hub", "worker"):
            self.setUp()
            off = [{"name": "VERIFACTU_PRODUCTION_ENABLED", "value": "false"}]
            self.fixture(f"erplora-prod-{family}", one(family, "hub:bootstrap", environment=off))
            self.deploy()
            self.assertNothingRegistered()
            self.assertRegex(self.out, f"::error::prod charges real money .*the latest revision of erplora-prod-{family}"
                                       f" has no VERIFACTU_PRODUCTION_ENABLED=true in its {family} container")
        self.setUp()
        self.deploy(FAKE_DESCRIBE_DENIED="erplora-prod-hub")
        self.assertNothingRegistered()
        self.assertRegex(self.out, "::error::aws ecs describe-task-definition failed: .*AccessDeniedException.*; "
                                   "nothing was registered")


if __name__ == "__main__":
    unittest.main()
