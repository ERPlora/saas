"""Models of accounts: the user, the membership of a user in a hub and the one-time code."""

import hashlib
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import IntegrityError
from django.utils import translation
from live.slugs import hub_slug_validator

from accounts.models import AuthExchangeCode, HubMembership

pytestmark = pytest.mark.django_db


class TestUser:
    def test_signs_in_with_the_email_and_has_a_uuid7_primary_key(self):
        user = get_user_model().objects.create_user(
            email="ana@EXAMPLE.com", password="s3cret-pass"
        )

        assert get_user_model().USERNAME_FIELD == "email"
        assert user.email == "ana@example.com"
        assert isinstance(user.pk, uuid.UUID)
        assert user.pk.version == 7
        assert user.check_password("s3cret-pass")
        assert user.is_active and not user.is_staff

    def test_speaks_english_unless_told_otherwise(self):
        user = get_user_model().objects.create_user(
            email="ana@example.com", password="x"
        )

        assert user.language == "en"

    def test_full_name_joins_first_and_last_name(self):
        user = get_user_model()(
            email="ana@example.com", first_name="Ana", last_name="García"
        )

        assert user.get_full_name() == "Ana García"
        assert get_user_model()(email="bo@example.com").get_full_name() == ""

    def test_an_email_is_required(self):
        with pytest.raises(ValueError):
            get_user_model().objects.create_user(email="", password="x")

    def test_a_superuser_is_staff(self):
        admin = get_user_model().objects.create_superuser(
            email="root@example.com", password="x"
        )

        assert admin.is_staff and admin.is_superuser


class TestHubMembership:
    def test_customer_roles_are_owner_admin_manager_and_employee_with_the_hub_prefix(
        self,
    ):
        # The prefix keeps a customer's role on a hub apart from the platform's (superuser, support).
        assert HubMembership.Role.values == [
            "hub_owner",
            "hub_admin",
            "hub_manager",
            "hub_employee",
        ]

    def test_role_labels_drop_the_prefix_and_are_translated(self):
        assert [str(label) for label in HubMembership.Role.labels] == [
            "Owner",
            "Admin",
            "Manager",
            "Employee",
        ]
        with translation.override("es"):
            assert [str(label) for label in HubMembership.Role.labels] == [
                "Propietario",
                "Administrador",
                "Gestor",
                "Empleado",
            ]

    def test_str_shows_the_label_of_the_role_not_its_stored_value(self, ana):
        membership = HubMembership(
            user=ana, hub_slug="a", role=HubMembership.Role.OWNER
        )

        assert str(membership) == "ana@example.com @ a (Owner)"

    @pytest.mark.parametrize(
        "role", ["owner", "admin", "manager", "employee", "superuser", "support"]
    )
    def test_a_role_without_the_hub_prefix_is_not_a_customer_role(self, ana, role):
        with pytest.raises(ValidationError):
            HubMembership(user=ana, hub_slug="a", role=role).full_clean()

    def test_is_unique_per_user_and_hub(self, ana):
        HubMembership.objects.create(
            user=ana, hub_slug="a", role=HubMembership.Role.ADMIN
        )

        with pytest.raises(IntegrityError):
            HubMembership.objects.create(
                user=ana, hub_slug="a", role=HubMembership.Role.EMPLOYEE
            )

    # The shared rule of live.slugs (one DNS label, never a reserved name; Ioan, 2026-10-13). The
    # tests run with the development minimum (1): the demo hubs are `a` and `b`.

    @pytest.mark.parametrize("slug", ["a", "b", "pelu-centro", "0day", "123", "a" * 63])
    def test_a_hub_slug_is_one_dns_label(self, ana, slug):
        HubMembership(
            user=ana, hub_slug=slug, role=HubMembership.Role.ADMIN
        ).full_clean()

    @pytest.mark.parametrize(
        "slug",
        [
            "",
            "A",
            "1a",
            "ab",
            "-a",
            "abc-",
            "a_b",
            "a.b",
            "a" * 64,
            "xn--bcher-kva",
            "www",
            "hub",
            "admin",
        ],
    )
    def test_anything_else_is_not_a_hub_slug(self, ana, slug):
        with pytest.raises(ValidationError):
            HubMembership(
                user=ana, hub_slug=slug, role=HubMembership.Role.ADMIN
            ).full_clean()

    def test_a_reserved_name_says_so(self, ana):
        with pytest.raises(ValidationError) as caught:
            HubMembership(
                user=ana, hub_slug="www", role=HubMembership.Role.ADMIN
            ).full_clean()

        assert caught.value.error_dict["hub_slug"][0].code == "reserved"

    def test_production_wants_at_least_three_characters(self, ana, settings):
        settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}

        with pytest.raises(ValidationError) as caught:
            HubMembership(
                user=ana, hub_slug="a", role=HubMembership.Role.ADMIN
            ).full_clean()

        assert caught.value.error_dict["hub_slug"][0].code == "too_short"


class TestAuthExchangeCode:
    def test_the_code_is_stored_as_its_sha256(self):
        assert AuthExchangeCode.hash_code("abc") == hashlib.sha256(b"abc").hexdigest()

    def test_the_only_audience_is_the_hub_session(self):
        assert AuthExchangeCode.HUB_SESSION_AUDIENCE == "hub-session"


@pytest.mark.parametrize("model", [HubMembership, AuthExchangeCode])
def test_every_hub_slug_uses_the_shared_validator(model):
    # Besides the MaxLengthValidator every CharField adds by itself.
    validators = model._meta.get_field("hub_slug").validators
    assert [v for v in validators if not isinstance(v, MaxLengthValidator)] == [hub_slug_validator]
