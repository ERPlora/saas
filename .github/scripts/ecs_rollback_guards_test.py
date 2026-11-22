"""Tests of ecs_rollback.py: what a rollback refuses before it changes anything, and how it reads what aws answers.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The fakes are ecs_rollback_test.py's.
"""

from __future__ import annotations

import json
import unittest

from ecs_rollback_test import TD, RollbackCase

SAAS = f"{TD}/erplora-prod-saas"
# The saas container on its image and with its settings.
APP = object()


class ConfirmationTest(RollbackCase):
    def test_it_asks_for_exactly_rollback_before_any_call(self):
        for confirm in (None, "rollback", "ROLLBACK ", ""):
            self.rollback("CONFIRM") if confirm is None else self.rollback(CONFIRM=confirm)
            self.assertFailsBeforeAnyCall(f"::error::CONFIRM must be exactly ROLLBACK, not '{confirm or ''}'; "
                                          "nothing was changed\n")
        self.rollback(CONFIRM="no", AWS_REGION="")
        self.assertFailsBeforeAnyCall("::error::CONFIRM must be exactly ROLLBACK, not 'no'; nothing was changed\n")

    def test_the_region_and_the_environment_are_required(self):
        for unset in ((), ("AWS_REGION",)):
            self.rollback(*unset, **({} if unset else {"AWS_REGION": ""}))
            self.assertFailsBeforeAnyCall("::error::AWS_REGION is required\n")
        self.rollback("ENVIRONMENT")
        self.assertFailsBeforeAnyCall("::error::ENVIRONMENT must be prod or pre, not ''; nothing was changed\n")
        for environment in ("staging", "Prod", "prod ", " pre"):
            self.rollback(ENVIRONMENT=environment)
            self.assertFailsBeforeAnyCall(f"::error::ENVIRONMENT must be prod or pre, not '{environment}'; nothing "
                                          "was changed\n")

    def test_what_it_refuses_is_said_byte_for_byte_whatever_the_locale(self):
        self.rollback(apart=True, CONFIRM="\udcc3\udcb1\udcff", PYTHONIOENCODING="ascii")
        self.assertEqual(b"::error::CONFIRM must be exactly ROLLBACK, not '\xc3\xb1\xff'; nothing was changed\n",
                         self.stderr)
        self.assertEqual(b"", self.stdout)


class GuardTest(RollbackCase):
    def assertRefused(self, revision: str, environment: str = "prod"):
        self.assertNothingChanged()
        self.assertIn(f"::error::{revision} is not a {environment} revision (it needs the tag Environment={environment} "
                      f"and the roles erplora-{environment}-*); nothing was changed\n", self.out)

    def test_a_revision_of_another_environment_is_refused(self):
        for table, value, environment in (("tags", "pre", "prod"), ("tags", "none", "prod"),
                                          ("roles", "erplora-pre-saas", "prod"), ("tags", "prod", "pre")):
            self.setUp()
            revision = f"{TD}/erplora-{environment}-saas:10"
            self.given(table, revision, value)
            self.rollback(ENVIRONMENT=environment)
            self.assertRefused(revision, environment)

    def described(self, containers=APP, tags=None) -> None:
        """saas:10 as aws describes it: prod's roles and tag, and <containers> and <tags> if given."""
        settings = [{"name": k, "value": v} for k, v in self.in_force("prod")["saas"].items()]
        containers = [{"name": "saas", "image": "reg.example/erplora/saas:t", "environment": settings}] \
            if containers is APP else containers
        role = "arn:aws:iam::123456789012:role/erplora-prod-saas"
        found = {"taskDefinition": {"taskRoleArn": f"{role}-task", "executionRoleArn": f"{role}-execution",
                                    "containerDefinitions": containers},
                 "tags": [{"key": "Environment", "value": "prod"}] if tags is None else tags}
        (self.fixtures / "describe-erplora-prod-saas:10").write_text(json.dumps(found))

    def test_its_tags_are_read_as_the_deploy_reads_them(self):
        # How jq reads the tags is ecs_common_test.py's; here, that the rollback goes through it.
        self.described(tags={"one": {"key": "Environment", "value": "prod"}})
        self.assertEqual(0, self.rollback())
        for answer in ("", "[]", "not json", "{}", '{"tags": ["x", {"key": "Environment", "value": "prod"}]}'):
            self.setUp()
            (self.fixtures / "describe-erplora-prod-saas:10").write_text(answer)
            self.rollback()
            self.assertRefused(f"{SAAS}:10")

    def test_a_previous_revision_must_run_the_image_of_its_environment(self):
        for image in ("other.example/thing:1", "reg.example/erplora/hub:tag-10"):
            self.setUp()
            self.given("images", f"{SAAS}:10", image)
            self.rollback()
            self.assertNothingChanged()
            self.assertIn(f"::error::{SAAS}:10 does not run an erplora/saas image ({image}); nothing was changed\n",
                          self.out)
        self.setUp()
        self.given("images", f"{TD}/erplora-pre-saas:10", "reg.example/erplora/saas:tag-10")
        self.rollback(ENVIRONMENT="pre")
        self.assertNothingChanged()
        self.assertIn("does not run an erplora/saas-pre image (reg.example/erplora/saas:tag-10);", self.out)

    def test_the_image_is_read_as_jq_reads_it(self):
        def saas(**image):
            return {"name": "saas", **image}

        for containers, image in (([], ""), ([saas(image=None)], ""), ([saas(image=False)], ""), ([saas()], ""),
                                  ([saas(image=5)], "5"), ([saas(image=0)], "0"), ([saas(image=[])], "[]"),
                                  ([saas(image=True)], "true"), ([saas(image=[1, "ñ"])], '[\n  1,\n  "ñ"\n]'),
                                  ([{"name": 1, "image": "r/erplora/saas:t"}], ""),
                                  ([{"name": "Saas", "image": "r/erplora/saas:t"}], ""),
                                  ([saas(image="erplora/saas:t")], "erplora/saas:t"),
                                  ([saas(image="r/erplora/saas-pre:t")], "r/erplora/saas-pre:t"),
                                  ([saas(image="r/erplora/x:\udcff")], "r/erplora/x:\ufffd")):
            self.setUp()
            self.described(containers)
            self.rollback()
            self.assertNothingChanged()
            # As bytes: what is no UTF-8 is written as U+FFFD, as jq wrote it, not as the byte it came as.
            self.assertIn(f"::error::{SAAS}:10 does not run an erplora/saas image ({image}); nothing was changed\n"
                          .encode(), self.stdout)

    def test_the_first_saas_container_gives_the_tag(self):
        # saas-worker goes back to tag-10: the warning that it stays says the tag saas goes back to.
        for containers, tag in (([None, {"name": "saas", "image": "r/erplora/saas:t1"}], "t1"),
                                ([{"name": "saas", "image": "r/erplora/saas:t1\n\n"}], "t1"),
                                ([{"name": "saas", "image": "r/erplora/saas:t1 \n"}], "t1 "),
                                ([{"name": "saas", "image": "r/erplora/saas:a:b"}, {"name": "saas", "image": "x"}],
                                 "b"),
                                ({"a": {"name": "saas", "image": "r/erplora/saas:t3"}}, "t3"),
                                ([{"name": "saas", "image": "r/erplora/saas:"}], "")):
            self.setUp()
            self.with_worker()
            self.described(containers)
            self.rollback()
            self.assertIn(f"::warning::saas-worker: its previous revision {TD}/erplora-prod-saas-worker:10 runs tag-10, "
                          f"not {tag} as saas's: it stays as it is\n", self.out)
        self.setUp()
        self.described()
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called("^ssm put-parameter --name /erplora/prod/saas/image_tag --value t "))

    def test_containers_that_cannot_be_read_through_end_the_rollback_as_jq_did(self):
        for containers in (None, "s", ["x", {"name": "saas", "image": "r/erplora/saas:t"}],
                           [{"name": "saas", "image": "r/erplora/saas:t"}, 5]):
            self.setUp()
            self.described(containers)
            self.assertEqual(5, self.rollback(), containers)
            self.assertFalse(self.called("update-service|put-parameter|get-parameter"))
            self.assertIn(f"ecs_rollback.py: {SAAS}:10 cannot be read: ", self.out)


class NothingToGoBackToTest(RollbackCase):
    def test_without_a_previous_active_revision_nothing_changes(self):
        self.listed("erplora-prod-saas", "saas-migrate:11", "saas-cron:11", "saas:13", "saas:12")
        self.rollback()
        self.assertNothingChanged()
        self.assertIn(f"::error::saas runs {SAAS}:12 and erplora-prod-saas has no earlier ACTIVE revision; nothing was "
                      "changed\n", self.out)

    def test_a_service_without_a_primary_deployment_of_its_family_changes_nothing(self):
        for answer, current in (("None", "None"), ("", "COMPLETED"), (f"{SAAS}:12x", f"{SAAS}:12x"),
                                (f"{SAAS}-migrate:12", f"{SAAS}-migrate:12"), (f"{SAAS}:", f"{SAAS}:"),
                                ("task-definition/erplora-prod-saas:12", "task-definition/erplora-prod-saas:12"),
                                (f"{SAAS}:\u0661", f"{SAAS}:\u0661"), (f" \t{SAAS}:12x COMPLETED", f"{SAAS}:12x")):
            self.setUp()
            self.primary("saas", answer)
            self.rollback()
            self.assertNothingChanged()
            self.assertIn(f"::error::saas has no PRIMARY deployment of erplora-prod-saas (got '{current}'); nothing was "
                          "changed\n", self.out)

    def test_the_lists_are_read_as_bash_read_them(self):
        listings = {f"{SAAS}:11\n{SAAS}:10": "11", f"{SAAS}:010\t{SAAS}:9": "010", f"  {SAAS}:10  ": "10",
                    f"{SAAS}:9 {SAAS}:10 {SAAS}:11": "11", f"{SAAS}:11 {SAAS}:11": "11", f"{SAAS}:13 {SAAS}:1": "1",
                    "": None, "None": None, "\t \t": None, f"{SAAS}:12": None, f"{SAAS}:0": None,
                    f"{TD}/erplora-prod-saas-cron:11": None, f"{SAAS}:11\x0b{SAAS}:10": None,
                    "arn:aws:ecs:eu-west-1:123456789012:task-definition/erplora-prod-saas:11": None,
                    # aws lists revisions as plain numbers; anything else is no candidate.
                    f"{SAAS}:x {SAAS}:10": "10", f"{SAAS}:\u0661": None, f"{SAAS}:+11": None}
        for listed, revision in listings.items():
            self.setUp()
            (self.fixtures / "list-erplora-prod-saas").write_text(listed)
            self.assertEqual(0 if revision else 1, self.rollback(), listed)
            if revision:
                self.assertTrue(self.called(f"update-service .*--task-definition {SAAS}:{revision} "), listed)
        self.setUp()
        self.primary("saas", "x:task-definition/erplora-prod-saas:12")
        self.rollback()
        self.assertIn("::error::saas runs x:task-definition/erplora-prod-saas:12 and erplora-prod-saas has no earlier",
                      self.out)


class AwsFailureTest(RollbackCase):
    def test_an_aws_call_that_fails_ends_the_rollback_with_its_code(self):
        for command in ("ecs describe-services", "ecs describe-task-definition", "ecs update-service", "ecs wait"):
            self.setUp()
            self.assertEqual(254, self.rollback(FAKE_FAILURE_ON=command), command)
            self.assertFalse(self.called("put-parameter"))
            self.assertNotIn("::error::", self.out)
        self.setUp()
        self.assertEqual(137, self.rollback(FAKE_KILLED_ON="ecs update-service"))
        self.assertEqual(1, len(self.lines("update-service")))
        self.setUp()
        self.with_worker()
        self.assertEqual(254, self.rollback(FAKE_PUT_FAILURE="image_tag"))
        self.assertTrue(self.called("update-service .*saas-worker"))
        self.assertTrue(self.out.endswith("recorded the settings of the revisions it went back to in "
                                          "/erplora/prod/saas/app_env\nAn error occurred (AccessDeniedException) when "
                                          "calling the PutParameter operation\n"), self.out)


if __name__ == "__main__":
    unittest.main()
