"""Tests of ecs_deploy.py: saas-worker, the service that may not exist yet.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes and the checkout are ecs_deploy_test.py's.
"""

from __future__ import annotations

import unittest

from ecs_deploy_test import DeployCase, one


class SaasWorkerTest(DeployCase):
    """ERPlora/aws creates saas-worker once the image with run_worker is out: until its family exists the deploy goes
    on without it and says so; from then on it is deployed with the saas service."""

    def worker(self, environment: str = "prod") -> None:
        image = "saas:bootstrap" if environment == "prod" else "saas-pre:bootstrap"
        self.fixture(f"erplora-{environment}-saas-worker", one("saas-worker", image))

    def test_before_it_exists_it_is_only_looked_for(self):
        self.assertEqual(0, self.deploy())
        self.assertIn("::warning::erplora-prod-saas-worker does not exist yet: skipped", self.out)
        self.assertTrue(self.called("^ecs list-task-definitions --family-prefix erplora-prod-saas-worker --status "
                                    "ACTIVE --region eu-south-2 --query taskDefinitionArns --output text$"))
        self.assertFalse(self.called("--task-definition erplora-prod-saas-worker|--services? saas-worker"))

    def test_once_it_exists_it_moves_with_the_saas_service(self):
        self.worker()
        self.assertEqual(0, self.deploy())
        self.assertNotIn("::warning::", self.out)
        self.assertEqual(["reg.example/erplora/saas:abc123"], self.images("erplora-prod-saas-worker"))
        self.assertEqual(2, len(self.lines("update-service")))
        self.assertLess(self.last_line_of("describe-tasks"), self.line_of(
            "update-service .*--service saas-worker --task-definition arn:td/erplora-prod-saas-worker:2 "))
        self.assertTrue(self.called("wait services-stable .*--services saas saas-worker$"))
        self.assertLess(self.last_line_of("describe-services .*--services saas-worker .*deployments"),
                        self.line_of("ssm put-parameter"))
        self.assertFalse(self.called("--desired-count|--services? worker( |$)"))
        self.assertNotEqual(0, self.deploy(FAKE_PRIMARY_REVISIONS="1"))
        self.assertIn("::error::saas-worker runs arn:td/erplora-prod-saas-worker:1", self.out)

    def test_only_its_own_family_counts(self):
        (self.fixtures / "erplora-prod-saas-worker-longer.json").touch()
        self.assertEqual(0, self.deploy())
        self.assertIn("::warning::erplora-prod-saas-worker does not exist yet", self.out)
        self.worker()
        # Only the answer's first line is read, its ARNs apart by spaces and tabs, as bash's `read -ra` read them.
        for listed, found in (("arn:td/erplora-prod-saas-worker:7", True), ("arn:td/erplora-prod-saas-worker:1\tarn:x", True),
                              (" \tarn:other\t arn/erplora-prod-saas-worker \t", True), ("/erplora-prod-saas-worker", True),
                              ("None\narn:td/erplora-prod-saas-worker:7", False), ("", False),
                              ("arn:td/erplora-prod-saas-worker:1\x0barn:x", False),
                              ("arn:td/other-erplora-prod-saas-worker:1", False)):
            self.assertEqual(0, self.deploy(FAKE_LIST_ANSWER=listed))
            self.assertEqual(not found, "::warning::erplora-prod-saas-worker does not exist yet" in self.out, listed)

    def test_a_failure_looking_for_it_or_reading_it_fails_the_deploy(self):
        self.deploy(FAKE_LIST_FAILURE="AccessDeniedException")
        self.assertNothingRegistered()
        self.assertNotIn("::warning::", self.out)
        self.assertIn("::error::could not look for erplora-prod-saas-worker; nothing was registered", self.out)
        self.worker()
        self.deploy(FAKE_DESCRIBE_DENIED="erplora-prod-saas-worker")
        self.assertNothingRegistered()

    def test_pre_wakes_it_with_saas_pre(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        self.assertIn("::warning::erplora-pre-saas-worker does not exist yet: skipped", self.out)
        self.worker("pre")
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        self.assertEqual(["reg.example/erplora/saas-pre:abc123"], self.images("erplora-pre-saas-worker"))
        self.assertTrue(self.called("update-service .*--service saas-worker-pre --task-definition "
                                    "arn:td/erplora-pre-saas-worker:2 --desired-count 1 "))


if __name__ == "__main__":
    unittest.main()
