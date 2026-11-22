"""Tests of ecs_deploy.py: the two waits of a deploy, the migration and the rollout of the services.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes and the checkout are ecs_deploy_test.py's.
"""

from __future__ import annotations

import unittest

from ecs_deploy_test import DeployCase


class MigrationTest(DeployCase):
    def test_a_slow_migration_is_polled_until_it_is_stopped(self):
        self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="PROVISIONING PENDING RUNNING STOPPED"))
        self.assertEqual(4, len(self.lines("describe-tasks .*lastStatus")))
        self.assertEqual(["15", "15", "15"], self.pauses())

    def test_poll_seconds_sets_the_pause(self):
        self.assertEqual(0, self.deploy(POLL_SECONDS="5", FAKE_TASK_STATUSES="RUNNING STOPPED"))
        self.assertEqual(["5"], self.pauses())

    def test_a_migration_that_outlasts_its_timeout_is_left_running_and_changes_nothing(self):
        self.assertNotEqual(0, self.deploy(MIGRATE_TIMEOUT_SECONDS="0"))
        self.assertFalse(self.called("update-service|put-parameter|stop-task"))
        self.assertIn("::error::saas-migrate is still RUNNING after 0s; it was left running "
                      "(arn:task/erplora-prod/migrate1) and no service changed; logs in /ecs/erplora-prod-saas-migrate",
                      self.out)
        self.assertNotEqual(0, self.deploy(MIGRATE_TIMEOUT_SECONDS="30", FAKE_TASK_STATUSES="RUNNING"))
        self.assertEqual(3, len(self.lines("describe-tasks .*lastStatus")))
        self.assertFalse(self.called("update-service"))
        self.assertIn("still RUNNING after 30s", self.out)

    def test_a_timeout_is_said_as_it_was_given(self):
        self.assertNotEqual(0, self.deploy(MIGRATE_TIMEOUT_SECONDS="030", FAKE_TASK_STATUSES="RUNNING"))
        self.assertIn("still RUNNING after 030s", self.out)
        self.assertEqual(3, len(self.lines("describe-tasks .*lastStatus")))

    def test_a_failed_migration_changes_no_service(self):
        self.assertNotEqual(0, self.deploy(FAKE_MIGRATE_EXIT="1"))
        self.assertFalse(self.called("update-service|put-parameter"))
        self.assertIn("::error::saas-migrate exited with code 1; logs in /ecs/erplora-prod-saas-migrate", self.out)
        self.assertNotEqual(0, self.deploy(FAKE_MIGRATE_EXIT="00"))
        self.assertIn("::error::saas-migrate exited with code 00;", self.out)

    def test_a_migration_that_never_ran_shows_why(self):
        reason = "CannotPullContainerError: pull image manifest has been retried 1 time(s)"
        self.assertNotEqual(0, self.deploy(FAKE_MIGRATE_EXIT="None", FAKE_STOPPED_REASON=reason))
        self.assertFalse(self.called("update-service"))
        self.assertIn(f"::error::saas-migrate stopped without running: {reason}\n", self.out)

    def test_what_aws_answers_is_said_byte_for_byte_whatever_the_locale(self):
        self.deploy(apart=True, PYTHONIOENCODING="ascii", FAKE_MIGRATE_EXIT="None",
                    FAKE_STOPPED_REASON=b"\xc3\xb1 \xff exited")
        self.assertEqual(b"::error::saas-migrate stopped without running: \xc3\xb1 \xff exited\n", self.stderr)

    def test_a_migration_task_that_cannot_start_shows_the_failures(self):
        self.assertNotEqual(0, self.deploy(FAKE_RUN_TASK_FAILURE="RESOURCE:ENI"))
        self.assertFalse(self.called("describe-tasks|update-service|put-parameter"))
        self.assertIn('::error::saas-migrate did not start: [{"arn":"arn:capacity","reason":"RESOURCE:ENI"}]\n',
                      self.out)

    def test_run_tasks_answer_is_read_as_jq_reads_it(self):
        for answer, said in (('{"tasks": [{"taskArn": 5}]}', "running saas-migrate: 5\n"),
                             ('{"tasks": [{"taskArn": "arn:t\\n\\n"}]}', "running saas-migrate: arn:t\n"),
                             ('{"tasks": [{"taskArn": {"a": [1]}}]}', 'running saas-migrate: {\n  "a": [\n    1\n'
                                                                      '  ]\n}\n')):
            self.assertEqual(0, self.deploy(FAKE_RUN_TASK_ANSWER=answer), answer)
            self.assertIn(said, self.out)
        for answer, said in (("null", "did not start: null\n"), ("", "did not start: \n"),
                             ('{"tasks": [], "failures": []}', "did not start: []\n"),
                             ('{"tasks": [{"taskArn": false}]}', "did not start: null\n"),
                             ('{"tasks": [{}], "failures": [{"reason": "ñ"}]}', 'did not start: [{"reason":"ñ"}]\n')):
            self.assertEqual(1, self.deploy(FAKE_RUN_TASK_ANSWER=answer), answer)
            self.assertIn(f"::error::saas-migrate {said}", self.out)
        for answer in ("not json", "[]", '{"tasks": {}}', '{"tasks": "s"}', '{"tasks": ["s"]}'):
            self.assertEqual(5, self.deploy(FAKE_RUN_TASK_ANSWER=answer), answer)
            self.assertFalse(self.called("describe-tasks"))


class RolloutTest(DeployCase):
    """services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it COMPLETED once the
    old tasks have drained from the ALB. The migration needs no pause here, so every pause is the rollout's."""

    def rollout(self, **env) -> int:
        return self.deploy(FAKE_TASK_STATUSES="STOPPED", **env)

    def reads(self) -> int:
        return len(self.lines("describe-services .*--services saas .*deployments"))

    def assertRolledBack(self):
        self.assertIn("::error::saas runs arn:td/erplora-prod-saas:1 (COMPLETED), not arn:td/erplora-prod-saas:2; "
                      "rolled back by the circuit breaker? See the service events\n", self.out)
        self.assertFalse(self.called("put-parameter"))

    def test_a_rollout_completed_on_the_second_read_succeeds(self):
        self.assertEqual(0, self.rollout(FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual((2, ["15"]), (self.reads(), self.pauses()))
        self.assertGreater(self.line_of("^ssm put-parameter --name /erplora/prod/saas/image_tag --value abc123 "),
                           self.last_line_of("describe-services .*deployments"))

    def test_a_failed_rollout_fails_on_that_read(self):
        self.assertNotEqual(0, self.rollout(FAKE_ROLLOUT_STATES="FAILED"))
        self.assertEqual((1, []), (self.reads(), self.pauses()))
        self.assertFalse(self.called("put-parameter"))
        self.assertIn("::error::saas runs arn:td/erplora-prod-saas:2 (FAILED), not arn:td/erplora-prod-saas:2", self.out)
        self.assertNotEqual(0, self.rollout(FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED"))
        self.assertEqual((2, ["15"]), (self.reads(), self.pauses()))

    def test_a_service_the_circuit_breaker_rolled_back_fails_on_that_read(self):
        self.assertNotEqual(0, self.rollout(FAKE_PRIMARY_REVISIONS="1"))
        self.assertEqual((1, []), (self.reads(), self.pauses()))
        self.assertRolledBack()
        self.assertNotEqual(0, self.rollout(FAKE_PRIMARY_REVISIONS="2 1", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(2, self.reads())
        self.assertRolledBack()

    def test_every_service_that_failed_is_said(self):
        self.fixture("erplora-prod-saas-worker", [{"name": "saas-worker", "image": "reg.example/erplora/saas:x"}])
        self.assertEqual(1, self.rollout(FAKE_ROLLOUT_STATES="FAILED"))
        self.assertIn("::error::saas runs arn:td/erplora-prod-saas:2 (FAILED)", self.out)
        self.assertIn("::error::saas-worker runs arn:td/erplora-prod-saas-worker:2 (FAILED)", self.out)

    def test_the_primary_deployment_is_read_as_bash_read_it(self):
        self.assertEqual(0, self.rollout(FAKE_PRIMARY_ANSWER=" \tarn:td/erplora-prod-saas:2 \t COMPLETED \t\nx y"))
        self.assertEqual(1, self.rollout(FAKE_PRIMARY_ANSWER="None"))
        self.assertIn("::error::saas runs None (), not arn:td/erplora-prod-saas:2;", self.out)
        self.assertEqual(1, self.rollout(FAKE_PRIMARY_ANSWER="arn:td/erplora-prod-saas:2  IN  PROGRESS ",
                                         ROLLOUT_TIMEOUT_SECONDS="0"))
        self.assertIn("::error::rollout of saas did not complete in 0 s", self.out)

    def test_a_rollout_that_outlasts_its_timeout_fails(self):
        self.assertNotEqual(0, self.rollout(FAKE_ROLLOUT_STATES="IN_PROGRESS", ROLLOUT_TIMEOUT_SECONDS="30"))
        self.assertEqual((3, ["15", "15"]), (self.reads(), self.pauses()))
        self.assertIn("::error::rollout of saas did not complete in 30 s; see the service events\n", self.out)
        self.assertFalse(self.called("put-parameter"))
        self.assertNotEqual(0, self.rollout(FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual((41, 40), (self.reads(), len(self.pauses())))
        self.assertIn("::error::rollout of saas did not complete in 600 s", self.out)

    def test_only_the_services_still_in_progress_are_read_again_on_one_clock(self):
        self.fixture("erplora-prod-saas-worker", [{"name": "saas-worker", "image": "reg.example/erplora/saas:x"}])
        self.assertEqual(1, self.rollout(FAKE_ROLLOUT_STATES="IN_PROGRESS", ROLLOUT_TIMEOUT_SECONDS="15"))
        self.assertEqual(["15"], self.pauses())
        self.assertIn("::error::rollout of saas did not complete in 15 s; see the service events\n"
                      "::error::rollout of saas-worker did not complete in 15 s;", self.out)
        self.assertEqual(0, self.rollout(FAKE_ROLLOUT_STATES_OF='{"saas-worker": "IN_PROGRESS COMPLETED"}'))
        self.assertEqual((1, 2, ["15"]), (self.reads(), len(self.lines("--services saas-worker .*deployments")),
                                          self.pauses()))


class TimingSettingsTest(DeployCase):
    def test_a_setting_that_is_not_a_number_of_seconds_fails_before_any_call(self):
        for name in ("POLL_SECONDS", "MIGRATE_TIMEOUT_SECONDS", "ROLLOUT_TIMEOUT_SECONDS"):
            for value in ("soon", "1.5", "-1", " 1", "1\n", "\u0661"):
                self.deploy(**{name: value})
                self.assertFailsBeforeAnyCall(f"::error::{name} must be a number of seconds, not '{value}'\n")

    def test_an_empty_one_takes_its_default(self):
        self.assertEqual(0, self.deploy(POLL_SECONDS="", MIGRATE_TIMEOUT_SECONDS="", ROLLOUT_TIMEOUT_SECONDS="",
                                        FAKE_TASK_STATUSES="RUNNING STOPPED"))
        self.assertEqual(["15"], self.pauses())


if __name__ == "__main__":
    unittest.main()
