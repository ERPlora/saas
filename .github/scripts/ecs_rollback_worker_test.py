"""Tests of ecs_rollback.py: saas-worker, the service that may not exist yet and never blocks the rollback of saas.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

ERPlora/aws creates it: until its family exists the rollback goes on without it and says so; from then on it goes back
with saas, to a revision of the same tag. The fakes are ecs_rollback_test.py's.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import ecs_rollback
from ecs_common import Stop
from ecs_rollback_test import TD, RollbackCase

WORKER = f"{TD}/erplora-prod-saas-worker"


class SaasWorkerTest(RollbackCase):
    def test_before_it_exists_the_rollback_goes_on_without_it(self):
        self.assertEqual(0, self.rollback())
        self.assertIn("::warning::erplora-prod-saas-worker does not exist yet: skipped\n", self.out)
        self.assertFalse(self.called("--services? saas-worker"))

    def test_once_it_exists_it_goes_back_with_saas(self):
        self.with_worker()
        self.assertEqual(0, self.rollback())
        self.assertNotIn("::warning::erplora-prod-saas-worker", self.out)
        self.assertTrue(self.called(f"update-service .*--service saas-worker --task-definition {WORKER}:10 "))
        self.assertTrue(self.called(f"update-service .*--service saas --task-definition {TD}/erplora-prod-saas:10 "))
        self.assertTrue(self.called("wait services-stable .*--services saas saas-worker$"))
        self.assertGreaterEqual(self.reads_of("saas-worker"), 1)
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services .*saas-worker "))
        self.assertIn("::warning::rolling back saas saas-worker (prod) to their previous revisions;", self.out)
        self.assertIn(f"rolling back saas-worker to {WORKER}:10\n", self.out)

    def test_only_its_own_family_counts(self):
        for listed, exists in ((f"{WORKER}-x:12\t{WORKER}:12", True), (f"{WORKER}-x:12", False),
                               (f"None\n{WORKER}:12", False), ("", False)):
            self.setUp()
            self.with_worker()
            (self.fixtures / "list-erplora-prod-saas-worker").write_text(listed)
            self.assertEqual(0, self.rollback(), listed)
            self.assertEqual(not exists, "::warning::erplora-prod-saas-worker does not exist yet" in self.out, listed)

    def test_a_previous_revision_of_another_tag_stays_as_it_is(self):
        self.with_worker()
        self.given("images", f"{WORKER}:10", "reg.example/erplora/saas:tag-other")
        self.assertEqual(0, self.rollback())
        self.assertIn(f"::warning::saas-worker: its previous revision {WORKER}:10 runs tag-other, not tag-10 as "
                      "saas's: it stays as it is\n", self.out)
        self.assertTrue(self.called(f"update-service .*--service saas --task-definition {TD}/erplora-prod-saas:10 "))
        self.assertFalse(self.called("update-service .*--service saas-worker"))
        self.assertTrue(self.called("wait services-stable .*--services saas$"))
        self.assertTrue(self.called("^ssm put-parameter .*--value tag-10 "))
        self.assertFalse(self.called(f"describe-task-definition --task-definition {WORKER}:10 --output json"))

    def test_without_an_earlier_revision_it_stays_as_it_is(self):
        # The first rollback after the deploy that brought the worker: Terraform's revision is its only one.
        self.with_worker()
        (self.fixtures / "list-erplora-prod-saas-worker").write_text(f"{WORKER}:12\t")
        self.assertEqual(0, self.rollback(apart=True))
        self.assertIn(f"::warning::saas-worker runs {WORKER}:12 and erplora-prod-saas-worker has no earlier ACTIVE "
                      "revision: it stays as it is\n".encode(), self.stdout)
        self.assertEqual(b"", self.stderr)
        self.assertTrue(self.called(f"update-service .*--service saas --task-definition {TD}/erplora-prod-saas:10 "))
        self.assertFalse(self.called("update-service .*--service saas-worker"))

    def test_a_revision_of_another_environment_or_image_still_changes_nothing(self):
        self.with_worker()
        self.given("tags", f"{WORKER}:10", "pre")
        self.rollback()
        self.assertNothingChanged()
        self.assertIn(f"::error::{WORKER}:10 is not a prod revision (it needs the tag Environment=prod and the roles "
                      "erplora-prod-*); nothing was changed\n", self.out)
        self.setUp()
        self.with_worker()
        self.given("images", f"{WORKER}:10", "reg.example/erplora/hub:tag-10")
        self.rollback()
        self.assertNothingChanged()
        self.assertIn(f"::error::{WORKER}:10 does not run an erplora/saas image (reg.example/erplora/hub:tag-10); "
                      "nothing was changed\n", self.out)

    def test_a_failure_looking_for_it_is_not_taken_for_a_missing_family(self):
        self.rollback(FAKE_LIST_FAILURE="AccessDeniedException")
        self.assertNothingChanged()
        self.assertNotIn("::warning::erplora-prod-saas-worker", self.out)
        self.assertEqual("An error occurred (AccessDeniedException) when calling the ListTaskDefinitions operation\n"
                         "::error::could not look for erplora-prod-saas-worker; nothing was changed\n", self.out)

    def test_without_aws_it_cannot_look_for_it(self):
        self.rollback(PATH="/nowhere")
        self.assertEqual(1, self.status)
        self.assertEqual("ecs_rollback.py: aws: command not found\n"
                         "::error::could not look for erplora-prod-saas-worker; nothing was changed\n", self.out)

    def test_pre_takes_saas_worker_pre_back_with_saas_pre(self):
        self.with_worker("pre", "-pre")
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertTrue(self.called(f"update-service .*--service saas-worker-pre --task-definition "
                                    f"{TD}/erplora-pre-saas-worker:10 "))
        self.assertTrue(self.called("wait services-stable .*--services saas-pre saas-worker-pre$"))

    def test_both_are_watched_on_one_clock(self):
        self.with_worker()
        self.assertEqual(0, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual((2, 2, ["15"]), (self.reads_of("saas"), self.reads_of("saas-worker"), self.pauses()))
        self.setUp()
        self.with_worker()
        self.assertEqual(1, self.rollback(FAKE_CIRCUIT_BREAKER="saas-worker"))
        self.assertIn(f"::error::saas-worker runs {WORKER}:12 (COMPLETED), not {WORKER}:10; rolled back by the "
                      "circuit breaker? See the service events\n", self.out)


class TagRuleTest(unittest.TestCase):
    """saas comes first and is never skipped; only an optional family stays when its tag is not saas's. With saas-worker
    as the only optional family, the refusal can only be reached by calling the rule itself."""

    def rule(self, optional: list[str]) -> tuple[object, str, str]:
        rollback = ecs_rollback.Rollback(region="r", environment="prod", cluster="c", seconds={}, optional=optional)
        moving = [ecs_rollback.Previous("saas", "saas", "arn:1", "t1"), ecs_rollback.Previous("other", "other", "arn:2",
                                                                                              "t2"),
                  ecs_rollback.Previous("third", "third", "arn:3", "t1")]
        said, warned = io.StringIO(), io.StringIO()
        with redirect_stderr(said), redirect_stdout(warned):
            try:
                kept = ecs_rollback.kept(rollback, moving)
            except Stop as stop:
                kept = stop.code
        return kept, warned.getvalue(), said.getvalue()

    def test_an_optional_family_of_another_tag_stays(self):
        self.assertEqual(({"saas": "arn:1", "third": "arn:3"}, "::warning::other: its previous revision arn:2 runs t2, "
                          "not t1 as saas's: it stays as it is\n", ""), self.rule(["other"]))

    def test_another_family_of_another_tag_changes_nothing(self):
        self.assertEqual((1, "", "::error::the previous revisions run different tags (t1 t2 t1); nothing was changed\n"),
                         self.rule([]))


if __name__ == "__main__":
    unittest.main()
