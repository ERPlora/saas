"""Tests of ecs_rollback.py: the settings of the revisions it goes back to (app_env_rollback.py check and record).

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes are ecs_rollback_test.py's; what app_env_rollback.py decides is tested by app_env_rollback_test.py.
"""

from __future__ import annotations

import unittest

from ecs_rollback_test import TD, RollbackCase

SAAS = f"{TD}/erplora-prod-saas"


def setting(name: str, value: str):
    return lambda settings: settings.update({name: value})


class SettingsTest(RollbackCase):
    def test_they_are_checked_before_any_service_moves_and_recorded_before_the_tag(self):
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called("^ssm get-parameter --name /erplora/prod/saas/app_env --query Parameter.Value "
                                    "--output text --region eu-south-2$"))
        self.assertLess(self.line_of("ssm get-parameter"), self.line_of("update-service"))
        self.assertLess(self.line_of(f"describe-task-definition --task-definition {SAAS}:10 --output json"),
                        self.line_of("update-service"))
        # With the real charge on, only the latest revisions of the hub's hub and worker are read.
        self.assertEqual(["erplora-prod-hub", "erplora-prod-worker"], sorted(
            call.split()[3] for call in self.calls() if " erplora-prod-hub " in call or " erplora-prod-worker " in call))
        self.assertEqual(self.in_force("prod"), self.recorded("prod"))
        self.assertGreater(self.line_of("/erplora/prod/saas/app_env --value"), self.last_line_of("describe-services"))
        self.assertLess(self.line_of("/erplora/prod/saas/app_env --value"), self.line_of("/erplora/prod/saas/image_tag"))

    def test_prod_goes_back_to_another_real_charge_only_with_its_confirmation(self):
        self.runs("prod", "saas", setting("PLATFORM_INVOICING_ENABLED", "false"))
        self.rollback()
        self.assertNothingChanged()
        self.assertIn("::error::prod changes PLATFORM_INVOICING_ENABLED to false: confirm it with CONFIRM_PROTECTED "
                      "PLATFORM_INVOICING_ENABLED=false (the workflow's confirm_protected); nothing was changed\n",
                      self.out)
        self.assertEqual(0, self.rollback(CONFIRM_PROTECTED="PLATFORM_INVOICING_ENABLED=false"))
        self.assertTrue(self.called(f"update-service .*--service saas --task-definition {SAAS}:10 "))
        in_force = self.in_force("prod")
        in_force["saas"]["PLATFORM_INVOICING_ENABLED"] = "false"
        self.assertEqual(in_force, self.recorded("prod"))
        self.assertIn("prod changes PLATFORM_INVOICING_ENABLED to false, as confirmed\n", self.out)
        self.assertFalse(self.called("erplora-prod-hub"))

    def test_saas_and_saas_worker_go_back_together_with_their_own_settings(self):
        self.with_worker()
        self.runs("prod", "saas", setting("AEAT_PRODUCTION_ENABLED", "false"))
        self.runs("prod", "saas-worker", setting("AEAT_PRODUCTION_ENABLED", "false"))
        self.assertEqual(0, self.rollback(CONFIRM_PROTECTED="AEAT_PRODUCTION_ENABLED=false"))
        in_force = self.in_force("prod")
        for name in ("saas", "saas-worker"):
            in_force[name]["AEAT_PRODUCTION_ENABLED"] = "false"
        self.assertEqual(in_force, self.recorded("prod"))

    def test_saas_and_saas_worker_on_different_policies_change_nothing(self):
        self.with_worker()
        self.runs("prod", "saas-worker", setting("AEAT_PRODUCTION_ENABLED", "false"))
        self.rollback(CONFIRM_PROTECTED="AEAT_PRODUCTION_ENABLED=false")
        self.assertNothingChanged()
        self.assertIn("::error::the revisions it goes back to: prod sets AEAT_PRODUCTION_ENABLED to false in "
                      "saas-worker; true in saas", self.out)

    def test_a_saas_worker_that_stays_keeps_its_settings_in_force(self):
        self.with_worker()
        self.given("images", f"{TD}/erplora-prod-saas-worker:10", "reg.example/erplora/saas:tag-other")
        self.runs("prod", "saas-worker", setting("AEAT_PRODUCTION_ENABLED", "false"))
        self.assertEqual(0, self.rollback())
        self.assertFalse(self.called(f"describe-task-definition --task-definition {TD}/erplora-prod-saas-worker:10 "
                                     "--output json"))
        self.assertEqual(self.in_force("prod"), self.recorded("prod"))

    def test_prod_does_not_charge_real_money_while_the_hub_does_not_file_in_production(self):
        self.rollback(FAKE_HUB_VERIFACTU="false")
        self.assertNothingChanged()
        self.assertRegex(self.out, "::error::prod charges real money .*erplora-prod-hub has no "
                                   "VERIFACTU_PRODUCTION_ENABLED=true in its hub container: deploy the Hub with it "
                                   "first; nothing was changed")

    def test_pre_refuses_a_real_charge_and_records_its_own_parameter(self):
        self.runs("pre", "saas", setting("PLATFORM_INVOICING_ENABLED", "true"))
        self.rollback(ENVIRONMENT="pre")
        self.assertNothingChanged()
        self.assertIn("::error::the revisions it goes back to: pre.saas.PLATFORM_INVOICING_ENABLED must be false in pre",
                      self.out)
        self.setUp()
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertEqual(self.in_force("pre"), self.recorded("pre"))
        self.assertFalse(self.called("erplora-prod-"))

    def test_settings_in_force_it_cannot_read_change_nothing(self):
        self.rollback(FAKE_APP_ENV_FAILURE="AccessDeniedException")
        self.assertNothingChanged()
        self.assertRegex(self.out, "::error::aws ssm get-parameter failed: .*AccessDeniedException.*; nothing was "
                                   "changed")

    def test_settings_that_cannot_be_written_fail_the_rollback_and_record_no_tag(self):
        self.assertEqual(1, self.rollback(FAKE_PUT_FAILURE="app_env"))
        self.assertTrue(self.called("update-service"))
        self.assertFalse(self.called("/erplora/prod/saas/image_tag"))
        self.assertIn("::error::the services run the previous revisions, but /erplora/prod/saas/app_env was not "
                      "written", self.out)


if __name__ == "__main__":
    unittest.main()
