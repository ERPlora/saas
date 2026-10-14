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

from accounts.models import (
    API_KEY_PREFIX,
    API_KEY_SCOPES,
    ApiKey,
    AuthExchangeCode,
    HubMembership,
    ProfilePhoto,
    UnknownScope,
    UserPreferences,
    validate_scopes,
)

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


class TestUserPreferences:
    """Account → Preferences (plan 2026-10-13 §3): the theme mode and the mails; the language is the
    account's own column (``User.language``), which the mails and the jump to a hub already read."""

    def test_defaults_follow_the_system_and_ask_before_marketing(self, ana):
        preferences = UserPreferences.objects.create(user=ana)

        assert (preferences.theme_mode, preferences.hub_alerts, preferences.marketing_emails) == (
            "system",
            True,
            False,
        )
        assert preferences.pk.version == 7

    def test_the_modes_are_the_shells(self):
        """The vocabulary of ``ThemeMode`` in packages/ui (shell/theme.ts): no mapping on the way."""
        assert [value for value, _ in UserPreferences.ThemeMode.choices] == ["system", "light", "dark"]

    def test_one_row_per_account(self, ana):
        UserPreferences.objects.create(user=ana)

        with pytest.raises(IntegrityError):
            UserPreferences.objects.create(user=ana)

    def test_they_go_with_the_account(self, ana):
        UserPreferences.objects.create(user=ana)

        ana.delete()

        assert not UserPreferences.objects.exists()


class TestApiKey:
    """An account's API key (ported from ERPlora/saas ``apps/auth/apikeys/models.py``): ``erps_live_`` and
    48 base62 characters, shown once and kept as its SHA-256 (plan 2026-10-13 §7 point 12: ``erps_live``
    tells the account's keys apart from a hub's ``erpk_live``)."""

    def test_a_new_secret_carries_the_prefix_and_only_its_hash_is_kept(self):
        secret, prefix, key_hash = ApiKey.new_secret()

        assert API_KEY_PREFIX == "erps_live_"
        assert secret.startswith(API_KEY_PREFIX)
        body = secret.removeprefix(API_KEY_PREFIX)
        assert len(body) == 48
        assert set(body) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
        assert prefix == body[:8]
        assert key_hash == hashlib.sha256(secret.encode()).hexdigest()

    def test_two_secrets_are_never_the_same(self):
        assert ApiKey.new_secret()[0] != ApiKey.new_secret()[0]

    def test_a_well_formed_secret_parses_to_its_body(self):
        secret, prefix, _ = ApiKey.new_secret()

        assert ApiKey.parse(secret) == secret.removeprefix(API_KEY_PREFIX)
        assert ApiKey.parse(f"  {secret} ") == secret.removeprefix(API_KEY_PREFIX)

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "erps_live_",
            "erpk_live_" + "a" * 48,  # a hub's key (hub-next), not the account's
            "erps_pre_" + "a" * 48,
            "erps_live_" + "a" * 47,
            "erps_live_" + "a" * 49,
            "erps_live_" + "a" * 47 + "-",
            "Bearer erps_live_" + "a" * 48,
        ],
    )
    def test_anything_else_is_refused_before_any_query(self, raw):
        assert ApiKey.parse(raw) is None

    def test_a_key_has_a_uuid7_id_and_belongs_to_its_account(self, ana):
        _, prefix, key_hash = ApiKey.new_secret()
        key = ApiKey.objects.create(user=ana, name="Zapier", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"])

        assert key.pk.version == 7
        assert list(ana.api_keys.all()) == [key]
        assert str(key) == f"Zapier (erps_live_{prefix}…)"

    def test_usable_until_revoked_or_expired(self, ana):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        _, prefix, key_hash = ApiKey.new_secret()
        key = ApiKey(user=ana, name="k", prefix=prefix, key_hash=key_hash)

        assert key.is_usable(now)
        key.expires_at = now + timedelta(days=1)
        assert key.is_usable(now)
        key.expires_at = now
        assert not key.is_usable(now)
        key.expires_at = None
        key.revoked_at = now
        assert not key.is_usable(now)

    def test_the_hash_is_unique(self, ana):
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=ana, name="a", prefix=prefix, key_hash=key_hash)

        with pytest.raises(IntegrityError):
            ApiKey.objects.create(user=ana, name="b", prefix=prefix, key_hash=key_hash)

    def test_keys_go_with_the_account(self, ana):
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=ana, name="a", prefix=prefix, key_hash=key_hash)

        ana.delete()

        assert not ApiKey.objects.exists()


class TestApiKeyScopes:
    """A scope is ``<app>.read`` (its queries) or ``<app>.write`` (its commands): the hub's app × {read,
    write}, here for the account's apps (plan 2026-10-13, L3-A)."""

    def test_the_registry_names_what_a_key_may_open(self):
        assert list(API_KEY_SCOPES) == ["hubs.read", "hubs.write", "billing.read"]

    def test_every_scope_says_what_it_opens_in_english_and_spanish(self):
        assert [str(label) for label in API_KEY_SCOPES.values()] == [
            "Businesses · read",
            "Businesses · write",
            "Invoices · read",
        ]
        with translation.override("es"):
            assert [str(label) for label in API_KEY_SCOPES.values()] == [
                "Negocios · lectura",
                "Negocios · escritura",
                "Facturas · lectura",
            ]

    def test_scopes_are_checked_and_deduplicated_in_order(self):
        assert validate_scopes(["billing.read", "hubs.read", "billing.read"]) == ["billing.read", "hubs.read"]

    def test_a_typo_is_refused_naming_it(self):
        with pytest.raises(UnknownScope, match="hubs.reed"):
            validate_scopes(["hubs.read", "hubs.reed"])


class TestProfilePhoto:
    def test_one_photo_per_account_that_goes_with_it(self, ana):
        photo = ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"png")

        assert photo.pk.version == 7
        assert ana.photo == photo
        with pytest.raises(IntegrityError):
            ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"png")

    def test_it_is_a_data_url(self, ana):
        photo = ProfilePhoto(user=ana, content_type="image/png", data=b"\x89PNG")

        assert photo.data_url() == "data:image/png;base64,iVBORw=="


class TestEmailChangeRequest:
    def test_one_waiting_change_per_account_that_goes_with_it(self, ana):
        from accounts.models import EmailChangeRequest

        change = EmailChangeRequest.objects.create(user=ana, session_key="s" * 32, email="a@new.example", code_hash="h")

        assert change.pk.version == 7
        assert change.attempts == 0
        with pytest.raises(IntegrityError):
            EmailChangeRequest.objects.create(user=ana, session_key="t" * 32, email="b@new.example", code_hash="h")
