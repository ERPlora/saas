"""Tests of ecs_rollback.py: the rollout of the services after services-stable.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it COMPLETED once the old
tasks have drained from the ALB, seconds to a minute later. The fakes are ecs_rollback_test.py's.
"""

from __future__ import annotations

import unittest

from ecs_rollback_test import TD, RollbackCase

SAAS = f"{TD}/erplora-prod-saas"
PUT_BACK = (f"::error::saas runs {SAAS}:12 (COMPLETED), not {SAAS}:10; rolled back by the circuit breaker? See the "
            "service events\n")


class RolloutTest(RollbackCase):
    def test_a_rollout_completed_on_the_second_read_succeeds_after_one_pause(self):
        self.assertEqual(0, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual((2, ["15"]), (self.reads_of("saas"), self.pauses()))
        self.assertTrue(self.called("^ssm put-parameter --name /erplora/prod/saas/image_tag --value tag-10 "))
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services"))

    def test_poll_seconds_sets_the_pause(self):
        self.assertEqual(0, self.rollback(POLL_SECONDS="5", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(["5"], self.pauses())

    def test_a_failed_rollout_fails_on_that_read(self):
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="FAILED"))
        self.assertEqual((1, []), (self.reads_of("saas"), self.pauses()))
        self.assertFalse(self.called("put-parameter"))
        self.assertIn(f"::error::saas runs {SAAS}:10 (FAILED), not {SAAS}:10;", self.out)
        self.setUp()
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED"))
        self.assertEqual((2, ["15"]), (self.reads_of("saas"), self.pauses()))
        self.assertFalse(self.called("put-parameter"))

    def test_a_service_the_circuit_breaker_put_back_fails_on_that_read(self):
        self.assertEqual(1, self.rollback(FAKE_CIRCUIT_BREAKER="saas"))
        self.assertEqual((1, []), (self.reads_of("saas"), self.pauses()))
        self.assertIn(PUT_BACK, self.out)
        self.assertFalse(self.called("put-parameter"))
        self.setUp()
        self.assertEqual(1, self.rollback(FAKE_PRIMARY_REVISIONS="10 12", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(2, self.reads_of("saas"))
        self.assertIn(PUT_BACK, self.out)
        self.assertFalse(self.called("put-parameter"))

    def test_a_rollout_that_outlasts_its_timeout_fails(self):
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS", ROLLOUT_TIMEOUT_SECONDS="30"))
        self.assertEqual((3, ["15", "15"]), (self.reads_of("saas"), self.pauses()))
        self.assertIn("::error::rollout of saas did not complete in 30 s; see the service events\n", self.out)
        self.assertFalse(self.called("put-parameter"))
        self.setUp()
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS", ROLLOUT_TIMEOUT_SECONDS="030"))
        self.assertIn("::error::rollout of saas did not complete in 030 s;", self.out)
        self.setUp()
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual((41, 40), (self.reads_of("saas"), len(self.pauses())))
        self.assertIn("::error::rollout of saas did not complete in 600 s", self.out)

    def test_the_primary_deployment_is_read_as_bash_read_it(self):
        self.primary("saas", f" \t{SAAS}:12 \t IN PROGRESS \t\nx y")
        self.assertEqual(0, self.rollback())
        self.setUp()
        self.assertEqual(1, self.rollback(FAKE_PRIMARY_ANSWER=f"{SAAS}:12 IN  PROGRESS "))
        self.assertIn(f"::error::saas runs {SAAS}:12 (IN  PROGRESS), not {SAAS}:10;", self.out)

    def test_a_setting_that_is_not_a_number_of_seconds_fails_before_any_call(self):
        for name in ("POLL_SECONDS", "ROLLOUT_TIMEOUT_SECONDS"):
            for value in ("soon", "1.5", "-1", " 1", "1\n", "١"):
                self.rollback(**{name: value})
                self.assertFailsBeforeAnyCall(f"::error::{name} must be a number of seconds, not '{value}'; nothing "
                                              "was changed\n")

    def test_the_environment_is_refused_before_the_seconds(self):
        self.rollback(ENVIRONMENT="staging", POLL_SECONDS="soon")
        self.assertFailsBeforeAnyCall("::error::ENVIRONMENT must be prod or pre, not 'staging'; nothing was changed\n")
        self.assertNotIn("POLL_SECONDS", self.out)
        self.rollback(POLL_SECONDS="soon", ROLLOUT_TIMEOUT_SECONDS="later")
        self.assertEqual("::error::POLL_SECONDS must be a number of seconds, not 'soon'; nothing was changed\n", self.out)

    def test_an_empty_one_takes_its_default(self):
        self.assertEqual(0, self.rollback(POLL_SECONDS="", ROLLOUT_TIMEOUT_SECONDS="",
                                          FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(["15"], self.pauses())


if __name__ == "__main__":
    unittest.main()
