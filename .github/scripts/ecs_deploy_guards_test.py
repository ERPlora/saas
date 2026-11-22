"""Tests of ecs_deploy.py: pre, and what a deploy refuses before it changes anything.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes and the checkout are ecs_deploy_test.py's.
"""

from __future__ import annotations

import json
import re
import unittest

from ecs_deploy_test import DeployCase, one


class PreTest(DeployCase):
    def test_pre_deploys_its_own_families_on_its_own_image_and_wakes_up(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        self.assertEqual(["erplora-pre-saas", "erplora-pre-saas-migrate"], sorted(self.registered()))
        self.assertEqual(["reg.example/erplora/saas-pre:abc123"], self.images("erplora-pre-saas", "saas"))
        self.assertEqual(["reg.example/erplora/saas-pre:abc123"], self.images("erplora-pre-saas-migrate"))
        self.assertEqual(["reg.example/erplora/saas:bootstrap"], self.images("erplora-pre-saas", "prod-image"))
        self.assertIn({"key": "Environment", "value": "pre"}, self.registered()["erplora-pre-saas"]["tags"])
        self.assertTrue(self.called(r"describe-services .*--services saas-pre .*--query services\[0\]\."
                                    r"networkConfiguration"))
        self.assertTrue(self.called('run-task .*--task-definition arn:td/erplora-pre-saas-migrate:2 .*"sg-saas-pre"'))
        self.assertTrue(self.called(r"describe-tasks .*containers\[\?name=='saas-migrate'\]\.exitCode"))
        self.assertEqual(self.lines("update-service"), self.lines(
            "update-service .*--service saas-pre --task-definition arn:td/erplora-pre-saas:2 --desired-count 1 "))
        self.assertTrue(self.called("wait services-stable .*--services saas-pre$"))
        self.assertGreater(self.last_line_of("describe-services .*--services saas-pre .*deployments"),
                           self.line_of("wait services-stable"))
        self.assertTrue(self.called(
            "^ssm put-parameter --name /erplora/pre/saas/image_tag --value abc123 --type String --overwrite"))
        registered = (self.work / "registered.log").read_text()
        self.assertFalse(re.search(r"erplora-prod-|/erplora/prod/|--services? saas( |$)|erplora/saas:abc123",
                                   "\n".join(self.calls()) + registered))
        self.assertTrue(all("--region eu-south-2" in call for call in self.calls()))
        self.assertTrue(self.cluster_is("erplora-pre"))

    def test_a_failed_migration_in_pre_names_pres_log_group(self):
        self.assertNotEqual(0, self.deploy(ENVIRONMENT="pre", FAKE_MIGRATE_EXIT="1"))
        self.assertFalse(self.called("update-service|put-parameter"))
        self.assertIn("::error::saas-migrate exited with code 1; logs in /ecs/erplora-pre-saas-migrate", self.out)

    def test_the_migration_is_started_by_the_first_twelve_characters_of_the_tag(self):
        self.git("tag", "-f", "0123456789abcdef")
        self.assertEqual(0, self.deploy(IMAGE_TAG="0123456789abcdef"))
        self.assertTrue(self.called(" --started-by deploy-0123456789ab --region "))


class EnvironmentGuardTest(DeployCase):
    """The pre deploy role can register a revision in any family (ecs:RegisterTaskDefinition takes no resource), so
    a base revision without the Environment tag of this run, or with another environment's roles, is refused before
    anything is registered."""

    def assertRefused(self, family: str, environment: str = "prod"):
        self.assertNothingRegistered()
        self.assertIn(f"::error::{family} is not a {environment} revision (it needs the tag Environment={environment} "
                      f"and the roles erplora-{environment}-*); nothing was registered\n", self.out)

    def test_a_revision_without_the_tag_or_the_roles_of_its_environment_is_refused(self):
        self.fixture("erplora-prod-saas-cron", one("saas-cron", "saas:bootstrap"), "")
        self.deploy()
        self.assertRefused("erplora-prod-saas-cron")
        self.fixture("erplora-pre-saas", one("saas", "saas-pre:bootstrap"), "prod")
        self.deploy(ENVIRONMENT="pre")
        self.assertRefused("erplora-pre-saas", "pre")
        self.fixture("erplora-prod-saas-migrate", one("saas-migrate", "saas:bootstrap"), "prod",
                     "erplora-pre-saas-migrate")
        self.deploy()
        self.assertRefused("erplora-prod-saas-migrate")

    def described(self, change) -> None:
        """The answer for erplora-prod-saas, changed in place by <change>."""
        path = self.fixtures / "erplora-prod-saas.json"
        found = json.loads(path.read_text())
        change(found)
        path.write_text(json.dumps(found))

    def test_the_roles_must_be_text_of_this_environment(self):
        role = "arn:aws:iam::123456789012:role/erplora-prod-x"
        for roles in ({"taskRoleArn": None}, {"taskRoleArn": 5}, {"taskRoleArn": f"x\n{role}"},
                      {"executionRoleArn": role.replace("123", "12")}, {"taskRoleArn": role.replace("1", "\u0661")}):
            self.setUp()
            self.described(lambda found, roles=roles: found["taskDefinition"].update(roles))
            self.deploy()
            self.assertRefused("erplora-prod-saas")
        self.setUp()
        self.described(lambda found: [found["taskDefinition"].pop(key) for key in ("taskRoleArn", "executionRoleArn")])
        self.deploy()
        self.assertRefused("erplora-prod-saas")
        self.setUp()
        self.described(lambda found: found["taskDefinition"].update(
            taskRoleArn="arn:aws-us-gov:iam::123456789012:role/erplora-prod-", executionRoleArn=f"{role}\n"))
        self.assertEqual(0, self.deploy())

    def test_the_tags_are_read_as_jq_reads_them(self):
        tag = {"key": "Environment", "value": "prod"}
        for tags, accepted in (([None, tag], True), ([tag, "x"], True), ({"one": tag}, True), (["x", tag], False),
                               ("prod", False), ([{"key": "Environment", "value": "pre"}], False),
                               ([{"key": "Stage", "value": "prod"}], False)):
            self.setUp()
            self.described(lambda found, tags=tags: found.update(tags=tags))
            self.assertEqual(0 if accepted else 1, self.deploy(), tags)
        for answer in ([], None, "", "[1]", {}, {"tags": [tag], "taskDefinition": "s"}):
            self.setUp()
            (self.fixtures / "erplora-prod-saas.json").write_text(answer if isinstance(answer, str) else
                                                                  json.dumps(answer))
            self.deploy()
            self.assertRefused("erplora-prod-saas")


class SaasImageTest(DeployCase):
    def test_a_family_without_a_container_of_the_saas_image_fails_before_the_migration(self):
        # saas-cron is the scheduled tasks' family: a revision left on the old image would keep it running.
        for family, image in (("saas-cron", "other.example/erplora/saas:bootstrap"),
                              ("saas-migrate", "reg.example/erplora/hub:bootstrap")):
            self.setUp()
            self.fixture(f"erplora-prod-{family}", [{"name": family, "image": image}])
            self.assertNotEqual(0, self.deploy())
            self.assertFalse(self.called("run-task|update-service|put-parameter"))
            self.assertIn(f"::error::erplora-prod-{family} ", self.out)

    def test_a_revision_without_the_cache_prefix_registers_nothing(self):
        # The four policies come from deploy/app-env.json; CACHE_KEY_PREFIX from ERPlora/aws: a revision Terraform has
        # not given it would register saas-cron's, the one the Scheduler runs, and only then fail at the migration.
        stripe = [{"name": "STRIPE_EXPECTED_MODE", "value": "live"}]
        self.fixture("erplora-prod-saas-cron", one("saas-cron", "saas:bootstrap", environment=stripe))
        self.deploy()
        self.assertNothingRegistered()
        self.assertIn("::error::erplora-prod-saas-cron has no CACHE_KEY_PREFIX in the environment or secrets of its "
                      "saas container (apply ERPlora/aws first); nothing was registered", self.out)
        self.fixture("erplora-pre-saas", one("saas", "saas-pre:bootstrap", environment=[]))
        self.deploy(ENVIRONMENT="pre")
        self.assertNothingRegistered()
        self.assertIn("::error::erplora-pre-saas has no CACHE_KEY_PREFIX ", self.out)

    def test_a_cache_prefix_given_as_a_secret_counts(self):
        secret = [{"name": "CACHE_KEY_PREFIX", "valueFrom": "arn:secret:x"}]
        self.fixture("erplora-prod-saas-cron", one("saas-cron", "saas:bootstrap", environment=[], secrets=secret))
        self.assertEqual(0, self.deploy())
        container = self.registered()["erplora-prod-saas-cron"]["containerDefinitions"][0]
        self.assertEqual(["AEAT_PRODUCTION_ENABLED", "PLATFORM_INVOICING_ENABLED", "PUBLIC_INDEXING_ENABLED",
                          "STRIPE_EXPECTED_MODE"], [setting["name"] for setting in container["environment"]])


class RunSettingsTest(DeployCase):
    def test_each_environment_deploys_to_its_own_cluster_unless_one_is_given(self):
        for environment in ("prod", "pre"):
            self.assertEqual(0, self.deploy(ENVIRONMENT=environment, CLUSTER="custom-cluster"))
            self.assertTrue(self.cluster_is("custom-cluster"))
            self.assertEqual(0, self.deploy(ENVIRONMENT=environment, CLUSTER=""))
            self.assertTrue(self.cluster_is(f"erplora-{environment}"))

    def test_an_unknown_environment_fails_before_any_call(self):
        for environment in ("staging", "Prod", "", "prod "):
            self.deploy(ENVIRONMENT=environment)
            self.assertFailsBeforeAnyCall(f"::error::ENVIRONMENT must be prod or pre, not '{environment}'\n")
        self.deploy(apart=True, ENVIRONMENT=b"pr\xffd")
        self.assertEqual(b"::error::ENVIRONMENT must be prod or pre, not 'pr\xffd'\n", self.stderr)

    def test_each_required_setting_is_named_when_missing_or_empty(self):
        for name in ("AWS_REGION", "REGISTRY", "IMAGE_TAG"):
            self.deploy(name)
            self.assertFailsBeforeAnyCall(f"::error::{name} is required\n")
            self.deploy(**{name: ""})
            self.assertFailsBeforeAnyCall(f"::error::{name} is required\n")
        self.deploy("ENVIRONMENT")
        self.assertFailsBeforeAnyCall("::error::ENVIRONMENT must be prod or pre, not ''\n")
        self.deploy("AWS_REGION", "IMAGE_TAG", ENVIRONMENT="x")
        self.assertEqual("::error::AWS_REGION is required\n", self.out)

    def test_an_aws_call_that_fails_ends_the_deploy_with_its_code(self):
        self.deploy(FAKE_DESCRIBE_DENIED="erplora-prod-saas")
        self.assertEqual(254, self.status)
        self.assertNothingRegistered()
        self.assertIn("An error occurred (AccessDeniedException) when calling the DescribeTaskDefinition", self.out)
        self.assertEqual(137, self.deploy(FAKE_KILLED_ON="ecs register-task-definition"))
        self.assertFalse(self.called("run-task"))

    def test_without_aws_it_cannot_look_for_the_worker(self):
        self.assertEqual(1, self.deploy(PATH=str(self.work / "fixtures")))
        self.assertIn("aws: command not found\n", self.out)
        self.assertTrue(self.out.endswith("::error::could not look for erplora-prod-saas-worker; nothing was "
                                          "registered\n"), self.out)


if __name__ == "__main__":
    unittest.main()
