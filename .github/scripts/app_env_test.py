"""Tests of app_env.py: the checks of deploy/app-env.json and how a deploy applies it to a task definition.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

Only the standard library: the deploy runs app_env.py with the runner's python3. How ecs_deploy.py calls it, with a
fake aws CLI, is tested by ecs_deploy_test.py and its siblings.
"""

import copy
import json
import unittest
from pathlib import Path

import app_env

REPO = Path(__file__).resolve().parents[2]

POLICIES_PROD = {
    "AEAT_PRODUCTION_ENABLED": "true",
    "PLATFORM_INVOICING_ENABLED": "true",
    "PUBLIC_INDEXING_ENABLED": "true",
    "STRIPE_EXPECTED_MODE": "live",
}
POLICIES_PRE = {
    "AEAT_PRODUCTION_ENABLED": "false",
    "PLATFORM_INVOICING_ENABLED": "false",
    "PUBLIC_INDEXING_ENABLED": "false",
    "STRIPE_EXPECTED_MODE": "test",
}
SETTINGS = {
    "prod": {
        "saas": {**POLICIES_PROD, "GA_MEASUREMENT_ID": "G-CHB9NM1C74", "MICROSOFT_STORE_APP_ID": "9P5C0XP1GS69"},
        "saas-cron": dict(POLICIES_PROD),
        "saas-migrate": dict(POLICIES_PROD),
        "saas-worker": dict(POLICIES_PROD),
    },
    "pre": {
        "saas": {**POLICIES_PRE, "MICROSOFT_STORE_APP_ID": "9P5C0XP1GS69"},
        "saas-migrate": dict(POLICIES_PRE),
        "saas-worker": dict(POLICIES_PRE),
    },
}
SECRET_VALUE = "never-print-this-value-0451"


def settings() -> dict:
    return copy.deepcopy(SETTINGS)


def container(name: str, image: str, environment: dict, secrets: tuple = ()) -> dict:
    return {
        "name": name,
        "image": image,
        "environment": [{"name": key, "value": value} for key, value in environment.items()],
        "secrets": [{"name": key, "valueFrom": f"arn:secret:{key}"} for key in secrets],
    }


def described(family: str, containers: list) -> dict:
    """A task definition as `aws ecs describe-task-definition --include TAGS` returns it."""
    return {
        "taskDefinition": {
            "family": family,
            "taskDefinitionArn": f"arn:td/{family}:7",
            "revision": 7,
            "status": "ACTIVE",
            "requiresAttributes": [],
            "compatibilities": ["FARGATE"],
            "registeredAt": "t",
            "registeredBy": "u",
            "taskRoleArn": "arn:aws:iam::123456789012:role/x-task",
            "containerDefinitions": containers,
        },
        "tags": [{"key": "Environment", "value": "prod"}],
    }


def environment_of(definition: dict, name: str) -> dict:
    [found] = [c for c in definition["containerDefinitions"] if c["name"] == name]
    return {variable["name"]: variable["value"] for variable in found.get("environment", [])}


class FileTestCase(unittest.TestCase):
    def assertRefused(self, value, *fragments) -> list:
        problems = app_env.file_errors(value)
        self.assertTrue(problems, "the file was accepted")
        for fragment in fragments:
            self.assertTrue(any(fragment in problem for problem in problems), f"no problem says {fragment!r}: {problems}")
        return problems


class TheFileOfTheRepository(unittest.TestCase):
    def test_deploy_app_env_json_passes_every_check(self):
        text = (REPO / "deploy" / "app-env.json").read_text()
        self.assertEqual(app_env.file_errors(json.loads(text)), [])

    def test_the_settings_of_these_tests_pass_every_check(self):
        self.assertEqual(app_env.file_errors(settings()), [])


class TheShapeOfTheFile(FileTestCase):
    def test_it_is_an_object(self):
        self.assertRefused([], "an object")

    def test_an_unknown_environment(self):
        value = settings()
        value["staging"] = value["pre"]
        self.assertRefused(value, "staging")

    def test_a_missing_environment(self):
        value = settings()
        del value["pre"]
        self.assertRefused(value, "pre")

    def test_a_family_the_environment_does_not_deploy(self):
        value = settings()
        value["pre"]["saas-cron"] = dict(POLICIES_PRE)
        self.assertRefused(value, "pre.saas-cron")

    def test_a_family_of_the_hub(self):
        value = settings()
        value["prod"]["hub"] = dict(POLICIES_PROD)
        self.assertRefused(value, "prod.hub")

    def test_a_missing_family(self):
        value = settings()
        del value["prod"]["saas-worker"]
        self.assertRefused(value, "prod", "saas-worker")

    def test_a_family_that_is_no_object(self):
        value = settings()
        value["prod"]["saas-cron"] = [["STRIPE_EXPECTED_MODE", "live"]]
        self.assertRefused(value, "prod.saas-cron")

    def test_an_environment_that_is_no_object(self):
        value = settings()
        value["pre"] = "saas"
        self.assertRefused(value, "pre")

    def test_a_secrets_section(self):
        value = settings()
        value["prod"]["saas"]["secrets"] = {"STRIPE_SECRET_KEY": "erplora/prod/saas:STRIPE_SECRET_KEY"}
        self.assertRefused(value, "prod.saas.secrets")


class TheVariables(FileTestCase):
    def test_only_text_values(self):
        for value in (True, 1, None, {"value": "true"}, ["true"]):
            with self.subTest(value=value):
                file = settings()
                file["prod"]["saas-cron"]["PUBLIC_INDEXING_ENABLED"] = value
                self.assertRefused(file, "prod.saas-cron.PUBLIC_INDEXING_ENABLED", "text")

    def test_an_unknown_variable(self):
        value = settings()
        value["prod"]["saas"]["DEBUG"] = "True"
        self.assertRefused(value, "prod.saas.DEBUG")

    def test_a_variable_terraform_owns_is_unknown_too(self):
        value = settings()
        value["prod"]["saas"]["CACHE_KEY_PREFIX"] = "saas"
        self.assertRefused(value, "prod.saas.CACHE_KEY_PREFIX")

    def test_a_name_that_looks_like_a_secret(self):
        for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "EMAIL_HOST_PASSWORD", "GITHUB_TOKEN",
                     "FISCAL_CERTIFICATE_KEY", "PRIVATE_PEM", "AWS_CREDENTIALS"):
            with self.subTest(name=name):
                value = settings()
                value["prod"]["saas"][name] = SECRET_VALUE
                problems = self.assertRefused(value, f"prod.saas.{name}", "secret")
                self.assertFalse(any(SECRET_VALUE in problem for problem in problems))

    def test_a_name_that_is_no_environment_variable(self):
        value = settings()
        value["prod"]["saas"]["stripe-mode"] = "live"
        self.assertRefused(value, "stripe-mode")

    def test_no_problem_repeats_a_value(self):
        for variable in ("GA_MEASUREMENT_ID", "MICROSOFT_STORE_APP_ID", "STRIPE_EXPECTED_MODE", "PUBLIC_INDEXING_ENABLED"):
            with self.subTest(variable=variable):
                value = settings()
                value["prod"]["saas"][variable] = SECRET_VALUE
                problems = self.assertRefused(value, f"prod.saas.{variable}")
                self.assertFalse(any(SECRET_VALUE in problem for problem in problems))

    def test_the_booleans_are_true_or_false(self):
        for variable in ("AEAT_PRODUCTION_ENABLED", "PLATFORM_INVOICING_ENABLED", "PUBLIC_INDEXING_ENABLED"):
            for wrong in ("True", "1", "yes", ""):
                with self.subTest(variable=variable, wrong=wrong):
                    value = settings()
                    for family in value["prod"].values():
                        family[variable] = wrong
                    self.assertRefused(value, f"prod.saas.{variable}")

    def test_the_stripe_mode_is_live_or_test(self):
        value = settings()
        for family in value["prod"].values():
            family["STRIPE_EXPECTED_MODE"] = "sandbox"
        self.assertRefused(value, "prod.saas.STRIPE_EXPECTED_MODE")

    def test_a_measurement_id_of_google_analytics(self):
        value = settings()
        value["prod"]["saas"]["GA_MEASUREMENT_ID"] = "UA-1234-1"
        self.assertRefused(value, "prod.saas.GA_MEASUREMENT_ID")

    def test_a_product_id_of_the_microsoft_store(self):
        value = settings()
        value["prod"]["saas"]["MICROSOFT_STORE_APP_ID"] = "https://apps.microsoft.com/detail/9P5C0XP1GS69"
        self.assertRefused(value, "prod.saas.MICROSOFT_STORE_APP_ID")

    def test_the_web_settings_are_optional(self):
        value = settings()
        del value["prod"]["saas"]["GA_MEASUREMENT_ID"]
        del value["prod"]["saas"]["MICROSOFT_STORE_APP_ID"]
        del value["pre"]["saas"]["MICROSOFT_STORE_APP_ID"]
        self.assertEqual(app_env.file_errors(value), [])


class TheSafetyRules(FileTestCase):
    def test_every_family_carries_the_four_policies(self):
        for policy in POLICIES_PROD:
            for environment in ("prod", "pre"):
                with self.subTest(policy=policy, environment=environment):
                    value = settings()
                    del value[environment]["saas-migrate"][policy]
                    self.assertRefused(value, f"{environment}.saas-migrate", policy)

    def test_every_family_of_an_environment_takes_the_same_policies(self):
        value = settings()
        value["prod"]["saas-worker"]["PLATFORM_INVOICING_ENABLED"] = "false"
        self.assertRefused(value, "prod", "PLATFORM_INVOICING_ENABLED", "saas-worker")

    def test_pre_never_charges_files_in_production_nor_is_indexed(self):
        for policy, wrong in (("STRIPE_EXPECTED_MODE", "live"), ("PLATFORM_INVOICING_ENABLED", "true"),
                              ("PUBLIC_INDEXING_ENABLED", "true"), ("AEAT_PRODUCTION_ENABLED", "true")):
            with self.subTest(policy=policy):
                value = settings()
                for family in value["pre"].values():
                    family[policy] = wrong
                self.assertRefused(value, f"pre.saas.{policy}", "pre")

    def test_prod_may_turn_its_policies_off(self):
        value = settings()
        for family in value["prod"].values():
            family.update(POLICIES_PRE)
        self.assertEqual(app_env.file_errors(value), [])

    def test_google_analytics_only_in_the_web_of_prod(self):
        for environment, family in (("pre", "saas"), ("prod", "saas-cron"), ("prod", "saas-worker")):
            with self.subTest(environment=environment, family=family):
                value = settings()
                value[environment][family]["GA_MEASUREMENT_ID"] = "G-CHB9NM1C74"
                self.assertRefused(value, f"{environment}.{family}.GA_MEASUREMENT_ID")

    def test_the_microsoft_store_only_in_the_web(self):
        value = settings()
        value["prod"]["saas-migrate"]["MICROSOFT_STORE_APP_ID"] = "9P5C0XP1GS69"
        self.assertRefused(value, "prod.saas-migrate.MICROSOFT_STORE_APP_ID")


class TheConfirmation(unittest.TestCase):
    """In prod, changing a protected setting against the app_env in force needs CONFIRM_PROTECTED."""

    def turned_off(self) -> dict:
        wanted = settings()["prod"]
        for family in wanted.values():
            family["PLATFORM_INVOICING_ENABLED"] = "false"
        return wanted

    def test_no_change_needs_no_confirmation(self):
        self.assertEqual(app_env.confirmation_errors("prod", settings()["prod"], settings()["prod"], ""), [])

    def test_each_protected_change_needs_its_own(self):
        for variable, new in (("PLATFORM_INVOICING_ENABLED", "false"), ("AEAT_PRODUCTION_ENABLED", "false"),
                              ("STRIPE_EXPECTED_MODE", "test")):
            with self.subTest(variable=variable):
                wanted = settings()["prod"]
                for family in wanted.values():
                    family[variable] = new
                problems = app_env.confirmation_errors("prod", wanted, settings()["prod"], "")
                self.assertEqual(len(problems), 1)
                self.assertIn(f"{variable}={new}", problems[0])
                self.assertEqual(app_env.confirmation_errors("prod", wanted, settings()["prod"], f"{variable}={new}"), [])

    def test_the_confirmation_names_the_value_the_file_sets(self):
        problems = app_env.confirmation_errors("prod", self.turned_off(), settings()["prod"],
                                               "PLATFORM_INVOICING_ENABLED=true")
        self.assertTrue(problems)
        self.assertTrue(any("PLATFORM_INVOICING_ENABLED=false" in problem for problem in problems))

    def test_several_confirmations_by_commas_or_spaces(self):
        wanted = self.turned_off()
        for family in wanted.values():
            family["STRIPE_EXPECTED_MODE"] = "test"
        for confirm in ("PLATFORM_INVOICING_ENABLED=false,STRIPE_EXPECTED_MODE=test",
                        " STRIPE_EXPECTED_MODE=test  PLATFORM_INVOICING_ENABLED=false ",
                        "PLATFORM_INVOICING_ENABLED=false, STRIPE_EXPECTED_MODE=test"):
            with self.subTest(confirm=confirm):
                self.assertEqual(app_env.confirmation_errors("prod", wanted, settings()["prod"], confirm), [])
        problems = app_env.confirmation_errors("prod", wanted, settings()["prod"], "PLATFORM_INVOICING_ENABLED=false")
        self.assertEqual(len(problems), 1)
        self.assertIn("STRIPE_EXPECTED_MODE=test", problems[0])

    def test_a_confirmation_of_a_setting_that_is_not_protected(self):
        problems = app_env.confirmation_errors("prod", settings()["prod"], settings()["prod"],
                                               "PUBLIC_INDEXING_ENABLED=true")
        self.assertEqual(len(problems), 1)
        self.assertIn("PUBLIC_INDEXING_ENABLED, which is no protected setting", problems[0])

    def test_a_confirmation_that_is_no_pair(self):
        for confirm in ("yes", "PLATFORM_INVOICING_ENABLED", "=false"):
            with self.subTest(confirm=confirm):
                self.assertTrue(app_env.confirmation_errors("prod", self.turned_off(), settings()["prod"], confirm))

    def test_a_setting_that_is_not_protected_changes_freely(self):
        wanted = settings()["prod"]
        for family in wanted.values():
            family["PUBLIC_INDEXING_ENABLED"] = "false"
        del wanted["saas"]["GA_MEASUREMENT_ID"]
        self.assertEqual(app_env.confirmation_errors("prod", wanted, settings()["prod"], ""), [])

    def test_a_family_the_app_env_lacks_is_a_change(self):
        current = settings()["prod"]
        del current["saas-worker"]
        problems = app_env.confirmation_errors("prod", settings()["prod"], current, "")
        self.assertEqual(len(problems), 3)

    def test_pre_needs_none(self):
        current = settings()["pre"]
        for family in current.values():
            family["STRIPE_EXPECTED_MODE"] = "live"
        self.assertEqual(app_env.confirmation_errors("pre", settings()["pre"], current, ""), [])


class TheRevision(unittest.TestCase):
    """What a deploy registers: the revision in force, with the new image and the file's settings."""

    IMAGE = "reg.example/erplora/saas:abc123"
    PROJECT_IMAGE = "reg.example/erplora/saas:"

    def base(self, saas_environment=None, secrets=()) -> dict:
        if saas_environment is None:
            saas_environment = {"CACHE_KEY_PREFIX": "saas", "DB_NAME": "saas", **POLICIES_PROD, "OLD_SETTING": "x"}
        return described("erplora-prod-saas", [
            container("saas", "reg.example/erplora/saas:old", saas_environment, secrets),
            container("log-router", "public.ecr.aws/fluent-bit:stable", {"STRIPE_EXPECTED_MODE": "kept"}),
        ])

    def current(self) -> dict:
        return {**POLICIES_PROD, "OLD_SETTING": "x"}

    def revision(self, base, wanted=None, current=None) -> dict:
        wanted = settings()["prod"]["saas"] if wanted is None else wanted
        current = self.current() if current is None else current
        return app_env.revision(base, wanted, current, self.IMAGE, self.PROJECT_IMAGE)

    def test_the_saas_container_gets_the_image_and_the_settings(self):
        new = self.revision(self.base())
        saas = next(c for c in new["containerDefinitions"] if c["name"] == "saas")
        self.assertEqual(saas["image"], self.IMAGE)
        self.assertEqual(environment_of(new, "saas"),
                         {"CACHE_KEY_PREFIX": "saas", "DB_NAME": "saas", **settings()["prod"]["saas"]})

    def test_a_setting_the_app_env_had_and_the_file_drops_is_removed(self):
        self.assertNotIn("OLD_SETTING", environment_of(self.revision(self.base()), "saas"))

    def test_the_settings_follow_the_file(self):
        wanted = {**settings()["prod"]["saas"], "PUBLIC_INDEXING_ENABLED": "false"}
        self.assertEqual(environment_of(self.revision(self.base(), wanted), "saas")["PUBLIC_INDEXING_ENABLED"], "false")

    def test_other_containers_keep_their_image_and_environment(self):
        new = self.revision(self.base())
        router = next(c for c in new["containerDefinitions"] if c["name"] == "log-router")
        self.assertEqual(router["image"], "public.ecr.aws/fluent-bit:stable")
        self.assertEqual(environment_of(new, "log-router"), {"STRIPE_EXPECTED_MODE": "kept"})

    def test_the_read_only_fields_go_and_the_tags_stay(self):
        new = self.revision(self.base())
        for field in ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
                      "registeredAt", "registeredBy"):
            self.assertNotIn(field, new)
        self.assertEqual(new["tags"], [{"key": "Environment", "value": "prod"}])
        self.assertEqual(new["taskRoleArn"], "arn:aws:iam::123456789012:role/x-task")

    def test_a_setting_the_latest_revision_has_and_the_app_env_lacks_follows_the_file(self):
        base = self.base({"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD, "GA_MEASUREMENT_ID": "G-0LD0000001"})
        self.assertEqual(environment_of(self.revision(base, current=dict(POLICIES_PROD)), "saas")["GA_MEASUREMENT_ID"],
                         "G-CHB9NM1C74")

    def test_a_setting_neither_the_file_nor_the_app_env_names_leaves_the_revision(self):
        base = self.base({"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD, "GA_MEASUREMENT_ID": "G-CHB9NM1C74"})
        new = self.revision(base, wanted=dict(POLICIES_PROD), current=dict(POLICIES_PROD))
        self.assertEqual(environment_of(new, "saas"), {"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD})

    def test_a_setting_that_is_a_secret_of_terraform_is_refused(self):
        environment = {"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD}
        del environment["STRIPE_EXPECTED_MODE"]
        current = self.current()
        del current["STRIPE_EXPECTED_MODE"]
        with self.assertRaises(app_env.Refused) as refused:
            self.revision(self.base(environment, secrets=("STRIPE_EXPECTED_MODE",)), current=current)
        self.assertIn("STRIPE_EXPECTED_MODE", str(refused.exception))

    def test_a_secret_of_terraform_is_refused_even_if_the_app_env_names_it(self):
        environment = {"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD}
        del environment["STRIPE_EXPECTED_MODE"]
        with self.assertRaises(app_env.Refused) as refused:
            self.revision(self.base(environment, secrets=("STRIPE_EXPECTED_MODE",)))
        self.assertIn("ERPlora/aws sets STRIPE_EXPECTED_MODE", str(refused.exception))

    def test_a_new_setting_neither_has_is_added(self):
        base = self.base({"CACHE_KEY_PREFIX": "saas", **POLICIES_PROD})
        self.assertEqual(environment_of(self.revision(base), "saas")["GA_MEASUREMENT_ID"], "G-CHB9NM1C74")

    def test_without_a_cache_prefix_it_is_refused(self):
        with self.assertRaises(app_env.Refused) as refused:
            self.revision(self.base({**POLICIES_PROD}))
        self.assertIn("erplora-prod-saas has no CACHE_KEY_PREFIX", str(refused.exception))

    def test_a_cache_prefix_given_as_a_secret_counts(self):
        new = self.revision(self.base({**POLICIES_PROD}, secrets=("CACHE_KEY_PREFIX",)))
        self.assertEqual(environment_of(new, "saas")["STRIPE_EXPECTED_MODE"], "live")

    def test_a_family_without_the_saas_image_is_refused(self):
        base = described("erplora-prod-saas-cron", [container("saas-cron", "other.example/erplora/saas:old", {})])
        with self.assertRaises(app_env.Refused) as refused:
            self.revision(base)
        self.assertIn("erplora-prod-saas-cron has no container of the image", str(refused.exception))

    def test_the_input_is_not_changed(self):
        base = self.base()
        before = copy.deepcopy(base)
        self.revision(base)
        self.assertEqual(base, before)


class TheHubFilesInProduction(unittest.TestCase):
    def hub(self, environment: dict, secrets=(), name="hub") -> dict:
        return described("erplora-prod-hub", [container(name, "reg.example/erplora/hub:abc", environment, secrets)])

    def test_with_verifactu_in_production(self):
        self.assertTrue(app_env.files_in_production(self.hub({"VERIFACTU_PRODUCTION_ENABLED": "true"}), "hub"))

    def test_without_it(self):
        for environment in ({}, {"VERIFACTU_PRODUCTION_ENABLED": "false"}, {"VERIFACTU_PRODUCTION_ENABLED": "True"}):
            with self.subTest(environment=environment):
                self.assertFalse(app_env.files_in_production(self.hub(environment), "hub"))

    def test_only_the_container_named_after_the_family_counts(self):
        hub = self.hub({"VERIFACTU_PRODUCTION_ENABLED": "true"}, name="sidecar")
        self.assertFalse(app_env.files_in_production(hub, "hub"))

    def test_a_secret_does_not_count(self):
        self.assertFalse(app_env.files_in_production(self.hub({}, secrets=("VERIFACTU_PRODUCTION_ENABLED",)), "hub"))


class TheCurrentAppEnv(unittest.TestCase):
    def test_an_object_of_families_of_text(self):
        self.assertEqual(app_env.parse_current('{"saas": {"A": "b"}}', "/p"), {"saas": {"A": "b"}})

    def test_anything_else_is_refused(self):
        for text in ("", "[]", '{"saas": ["A"]}', '{"saas": {"A": 1}}', "not json"):
            with self.subTest(text=text), self.assertRaises(app_env.Refused) as refused:
                app_env.parse_current(text, "/erplora/prod/saas/app_env")
            self.assertIn("/erplora/prod/saas/app_env", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
