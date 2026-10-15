"""Issuing and redeeming the one-time code of the jump to a hub (PLAN-SAAS §3.1 steps 5-6)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts import services
from accounts.models import AuthExchangeCode, HubMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(ana):
    HubMembership.objects.create(
        user=ana, hub_slug="a", role=HubMembership.Role.MANAGER
    )
    return ana


def _later(monkeypatch, seconds):
    """Move ``timezone.now`` as the services see it ``seconds`` into the future."""
    moment = timezone.now() + timedelta(seconds=seconds)
    monkeypatch.setattr(services.timezone, "now", lambda: moment)


class TestIssueCode:
    def test_a_member_gets_a_random_urlsafe_code(self, member):
        code = services.issue_code(member, "a")
        other = services.issue_code(member, "a")

        assert len(code) >= 43
        assert code != other
        assert set(code) <= set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )

    def test_only_the_sha256_of_the_code_is_stored(self, member):
        code = services.issue_code(member, "a")

        row = AuthExchangeCode.objects.get()
        assert row.code_hash == AuthExchangeCode.hash_code(code)
        assert not AuthExchangeCode.objects.filter(code_hash=code).exists()

    def test_the_code_is_bound_to_the_user_the_hub_and_the_hub_session(self, member):
        services.issue_code(member, "a")

        row = AuthExchangeCode.objects.get()
        assert (row.user, row.hub_slug, row.audience, row.used_at) == (
            member,
            "a",
            "hub-session",
            None,
        )

    def test_the_code_expires_60_seconds_after_it_is_issued(self, member):
        services.issue_code(member, "a")

        row = AuthExchangeCode.objects.get()
        assert row.expires_at - row.created_at == timedelta(seconds=60)
        assert abs(row.created_at - timezone.now()) < timedelta(seconds=5)

    def test_someone_who_is_no_member_of_the_hub_gets_no_code(self, member):
        with pytest.raises(services.HubAccessDenied):
            services.issue_code(member, "b")

        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("slug", ["www", "hub", "admin", "ab", "A", "-a", "a.b"])
    def test_a_reserved_or_invalid_slug_gets_no_code_even_with_a_membership_row(
        self, member, slug
    ):
        # A row saved without validation (``objects.create`` skips validators) opens nothing.
        HubMembership.objects.create(
            user=member, hub_slug=slug, role=HubMembership.Role.OWNER
        )

        with pytest.raises(services.HubAccessDenied):
            services.issue_code(member, slug)

        assert not AuthExchangeCode.objects.exists()


class TestRedeemCode:
    def test_returns_who_signs_in_and_their_role_in_the_hub(self, member):
        code = services.issue_code(member, "a")

        identity = services.redeem_code(code, "a")

        assert identity == services.HubIdentity(
            user_id=str(member.pk),
            email="ana@example.com",
            name="Ana García",
            locale="es",
            role="hub_manager",
        )

    def test_marks_the_code_used(self, member):
        services.redeem_code(services.issue_code(member, "a"), "a")

        assert AuthExchangeCode.objects.get().used_at is not None

    def test_a_code_works_only_once(self, member):
        code = services.issue_code(member, "a")
        services.redeem_code(code, "a")

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

    def test_a_code_for_another_hub_is_refused_and_stays_usable_by_its_hub(
        self, member
    ):
        code = services.issue_code(member, "a")

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "b")

        assert services.redeem_code(code, "a").email == "ana@example.com"

    def test_an_expired_code_is_refused(self, member, monkeypatch):
        code = services.issue_code(member, "a")
        _later(monkeypatch, 61)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

    @pytest.mark.parametrize("code", ["", "not-a-code-we-issued"])
    def test_an_unknown_code_is_refused(self, member, code):
        services.issue_code(member, "a")

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

    def test_a_deactivated_account_cannot_redeem(self, member):
        code = services.issue_code(member, "a")
        get_user_model().objects.filter(pk=member.pk).update(is_active=False)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

    def test_a_membership_removed_after_issuing_cannot_redeem(self, member):
        code = services.issue_code(member, "a")
        HubMembership.objects.filter(user=member).delete()

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

    def test_the_role_is_the_one_at_redemption(self, member):
        code = services.issue_code(member, "a")
        HubMembership.objects.filter(user=member).update(role=HubMembership.Role.ADMIN)

        assert services.redeem_code(code, "a").role == "hub_admin"

    def test_one_account_carries_a_different_role_to_each_hub(self, member):
        HubMembership.objects.filter(user=member, hub_slug="a").update(
            role=HubMembership.Role.OWNER
        )
        HubMembership.objects.create(
            user=member, hub_slug="b", role=HubMembership.Role.EMPLOYEE
        )
        code_a = services.issue_code(member, "a")
        code_b = services.issue_code(member, "b")

        assert services.redeem_code(code_b, "b").role == "hub_employee"
        assert services.redeem_code(code_a, "a").role == "hub_owner"

    @pytest.mark.parametrize("slug", ["admin", "www", "ab", "A"])
    def test_a_reserved_or_invalid_hub_is_refused_without_spending_the_code(
        self, member, slug
    ):
        # Rows saved without validation, as if they predated the shared rule.
        HubMembership.objects.create(
            user=member, hub_slug=slug, role=HubMembership.Role.OWNER
        )
        now = timezone.now()
        AuthExchangeCode.objects.create(
            code_hash=AuthExchangeCode.hash_code("a-code"),
            user=member,
            hub_slug=slug,
            created_at=now,
            expires_at=now + timedelta(seconds=60),
        )

        with pytest.raises(services.InvalidCode):
            services.redeem_code("a-code", slug)

        assert AuthExchangeCode.objects.get().used_at is None

    @pytest.mark.parametrize("slug", [None, 42])
    def test_a_hub_that_is_no_string_is_refused(self, member, slug):
        with pytest.raises(services.InvalidCode):
            services.redeem_code(services.issue_code(member, "a"), slug)

    def test_without_a_full_name_the_name_is_the_email(self, member):
        get_user_model().objects.filter(pk=member.pk).update(
            first_name="", last_name=""
        )

        assert (
            services.redeem_code(services.issue_code(member, "a"), "a").name
            == "ana@example.com"
        )


class TestSeedDemoCustomer:
    """A customer account of ``demo_seed``: its businesses and roles are ``hubs.services.seed_demo_business``'s
    (the mirror the jump reads has one writer, ``hubs.services.sync_access``; L1-A2)."""

    def test_creates_a_customer_that_is_no_staff_and_belongs_to_no_hub_yet(self):
        user = services.seed_demo_customer("owner@example.com", "owner")

        assert user.check_password("owner")
        assert (user.is_staff, user.is_superuser) == (False, False)
        assert not user.groups.exists()
        assert not HubMembership.objects.exists()

    def test_running_it_again_changes_nothing(self):
        first = services.seed_demo_customer("owner@example.com", "owner")
        again = services.seed_demo_customer("owner@example.com", "owner")

        assert again.pk == first.pk
        assert get_user_model().objects.count() == 1

    def test_its_address_is_proven_so_it_signs_in_without_a_code(self):
        """Every account proves its address before its first session; the local ones come proven."""
        from allauth.account.models import EmailAddress

        user = services.seed_demo_customer("owner@example.com", "owner")

        assert list(EmailAddress.objects.filter(user=user).values_list("email", "verified", "primary")) == [
            ("owner@example.com", True, True)
        ]

    def test_an_existing_customer_without_a_proven_address_gets_it_proven(self):
        """A local database seeded before the code existed keeps working: running it again proves it."""
        from allauth.account.models import EmailAddress

        existing = get_user_model().objects.create_user(email="owner@example.com", password="owner")
        EmailAddress.objects.create(user=existing, email="owner@example.com", verified=False, primary=True)

        services.seed_demo_customer("owner@example.com", "owner")

        assert list(EmailAddress.objects.filter(user=existing).values_list("verified", "primary")) == [(True, True)]

    def test_the_old_seeds_that_wrote_the_mirror_are_gone(self):
        assert not hasattr(services, "seed_demo_owner")
        assert not hasattr(services, "seed_demo_member")


class TestSeedDemoPlatformAdmin:
    def test_creates_a_superuser_of_the_platform_with_no_hub(self):
        user = services.seed_demo_platform_admin("platform@example.com", "platform")

        assert user.check_password("platform")
        assert (user.is_staff, user.is_superuser) == (True, True)
        assert not user.hub_memberships.exists()

    def test_its_address_is_proven_so_it_signs_in_without_a_code(self):
        from allauth.account.models import EmailAddress

        user = services.seed_demo_platform_admin("platform@example.com", "platform")

        assert list(EmailAddress.objects.filter(user=user).values_list("email", "verified", "primary")) == [
            ("platform@example.com", True, True)
        ]

    def test_a_platform_role_never_travels_to_a_hub(self):
        user = services.seed_demo_platform_admin("platform@example.com", "platform")

        with pytest.raises(services.HubAccessDenied):
            services.issue_code(user, "a")

    def test_running_it_again_changes_nothing(self):
        first = services.seed_demo_platform_admin("platform@example.com", "platform")
        again = services.seed_demo_platform_admin("platform@example.com", "platform")

        assert again.pk == first.pk
        assert get_user_model().objects.count() == 1


class TestHubAdminCode:
    """Audience ``hub-admin`` (ronda 13, PLAN §18): the platform's staff jump to the Hub's Django admin
    at ``hubs.erplora.com/admin/hub/<slug>/``. Staff need no membership; customers never get one."""

    # The wire value the Hub sends back in ``/internal/auth/redeem``.
    HUB_ADMIN = "hub-admin"

    @pytest.fixture
    def platform_admin(self, password):
        user, _ = services.create_platform_user("boss@erplora.com", "admin", password)
        return user

    @pytest.fixture
    def platform_support(self, password):
        user, _ = services.create_platform_user("help@erplora.com", "support", password)
        return user

    def test_the_audience_is_a_constant_of_the_code(self):
        assert AuthExchangeCode.HUB_ADMIN_AUDIENCE == "hub-admin"

    def test_a_platform_admin_mints_a_code_for_any_hub_without_being_a_member(self, platform_admin):
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)

        row = AuthExchangeCode.objects.get()
        assert row.code_hash == AuthExchangeCode.hash_code(code)
        assert (row.user, row.hub_slug, row.audience, row.used_at) == (platform_admin, "a", "hub-admin", None)
        assert row.expires_at - row.created_at == timedelta(seconds=60)

    def test_support_mints_one_too(self, platform_support):
        services.issue_code(platform_support, "a", audience=self.HUB_ADMIN)

        assert AuthExchangeCode.objects.get().audience == "hub-admin"

    @pytest.mark.parametrize("role", HubMembership.Role.values)
    def test_a_customer_gets_no_hub_admin_code_not_even_for_their_own_hub(self, ana, role):
        HubMembership.objects.create(user=ana, hub_slug="a", role=role)

        with pytest.raises(services.HubAccessDenied):
            services.issue_code(ana, "a", audience=self.HUB_ADMIN)

        assert not AuthExchangeCode.objects.exists()

    def test_an_inactive_staff_account_gets_no_code(self, platform_admin):
        platform_admin.is_active = False

        with pytest.raises(services.HubAccessDenied):
            services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)

        assert not AuthExchangeCode.objects.exists()

    def test_staff_without_a_platform_role_gets_no_code(self, ana):
        """Only the platform's roles (superuser or ``support``) reach the Hub admin."""
        ana.is_staff = True
        ana.save()

        with pytest.raises(services.HubAccessDenied):
            services.issue_code(ana, "a", audience=self.HUB_ADMIN)

        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("slug", ["hubs", "hub", "www", "admin", "support", "ab", "A", "-a", "a.b", ""])
    def test_the_platform_host_and_reserved_or_invalid_slugs_are_no_target(self, platform_admin, slug):
        with pytest.raises(services.HubAccessDenied):
            services.issue_code(platform_admin, slug, audience=self.HUB_ADMIN)

        assert not AuthExchangeCode.objects.exists()

    def test_an_unknown_audience_is_a_programming_error(self, platform_admin):
        with pytest.raises(ValueError, match="audience"):
            services.issue_code(platform_admin, "a", audience="hub-everything")

        assert not AuthExchangeCode.objects.exists()

    def test_redeeming_returns_the_platform_admin_role(self, platform_admin):
        platform_admin.first_name, platform_admin.last_name = "Bo", "Ss"
        platform_admin.save()
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)

        identity = services.redeem_code(code, "a", audience=self.HUB_ADMIN)

        assert identity == services.HubIdentity(
            user_id=str(platform_admin.pk),
            email="boss@erplora.com",
            name="Bo Ss",
            locale="en",
            role="platform_admin",
        )
        assert AuthExchangeCode.objects.get().used_at is not None

    def test_redeeming_returns_the_platform_support_role(self, platform_support):
        code = services.issue_code(platform_support, "a", audience=self.HUB_ADMIN)

        assert services.redeem_code(code, "a", audience=self.HUB_ADMIN).role == "platform_support"

    def test_a_hub_admin_code_works_only_once(self, platform_admin):
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)
        services.redeem_code(code, "a", audience=self.HUB_ADMIN)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a", audience=self.HUB_ADMIN)

    def test_a_hub_admin_code_opens_no_hub_session_and_stays_usable(self, platform_admin):
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a")

        assert AuthExchangeCode.objects.get().used_at is None
        assert services.redeem_code(code, "a", audience=self.HUB_ADMIN).role == "platform_admin"

    def test_a_hub_session_code_opens_no_hub_admin(self, member):
        code = services.issue_code(member, "a")

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a", audience=self.HUB_ADMIN)

        assert AuthExchangeCode.objects.get().used_at is None

    def test_a_hub_admin_code_for_another_hub_is_refused(self, platform_admin):
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "b", audience=self.HUB_ADMIN)

    @pytest.mark.parametrize(
        "demote",
        [
            {"is_active": False},
            {"is_staff": False},
            {"is_superuser": False},
        ],
    )
    def test_an_account_that_lost_the_platform_role_after_issuing_cannot_redeem(self, platform_admin, demote):
        code = services.issue_code(platform_admin, "a", audience=self.HUB_ADMIN)
        get_user_model().objects.filter(pk=platform_admin.pk).update(**demote)

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a", audience=self.HUB_ADMIN)

    def test_support_removed_from_its_group_after_issuing_cannot_redeem(self, platform_support):
        code = services.issue_code(platform_support, "a", audience=self.HUB_ADMIN)
        platform_support.groups.clear()

        with pytest.raises(services.InvalidCode):
            services.redeem_code(code, "a", audience=self.HUB_ADMIN)

    @pytest.mark.parametrize("slug", ["hubs", "hub"])
    def test_a_code_bound_to_the_platform_host_is_refused_without_spending_it(self, platform_admin, slug):
        # A row saved without validation, as if it predated ronda 13.
        now = timezone.now()
        AuthExchangeCode.objects.create(
            code_hash=AuthExchangeCode.hash_code("a-code"),
            user=platform_admin,
            audience=self.HUB_ADMIN,
            hub_slug=slug,
            created_at=now,
            expires_at=now + timedelta(seconds=60),
        )

        with pytest.raises(services.InvalidCode):
            services.redeem_code("a-code", slug, audience=self.HUB_ADMIN)

        assert AuthExchangeCode.objects.get().used_at is None


def test_the_platform_host_is_no_customer_hub_either(member):
    """``hubs`` is the Hub admin's host (ronda 13): a membership row naming it opens nothing."""
    HubMembership.objects.create(user=member, hub_slug="hubs", role=HubMembership.Role.OWNER)

    with pytest.raises(services.HubAccessDenied):
        services.issue_code(member, "hubs")

    assert not AuthExchangeCode.objects.exists()


class TestReleaseUnprovenAccount:
    """``release_unproven_account`` (saas#2541): every credential of an account whose holder never proved its
    email goes, so only whoever opens that mailbox gets in («Forgot your password?», or Google, which
    proves the address). The account, its addresses and what hangs from it stay."""

    @pytest.fixture
    def squatter(self, ana):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email=ana.email, primary=True, verified=False)
        return ana

    def test_the_password_goes(self, squatter, password):
        services.release_unproven_account(squatter, reason="invited_while_unverified")

        squatter.refresh_from_db()
        assert not squatter.check_password(password)
        assert not squatter.has_usable_password()

    def test_the_browser_session_ends_with_the_password(self, client, squatter):
        client.force_login(squatter)
        assert client.get("/api/me").json()["user"] is not None

        services.release_unproven_account(squatter, reason="invited_while_unverified")

        assert client.get("/api/me").json()["user"] is None

    def test_the_second_factor_and_a_linked_google_go(self, squatter):
        from allauth.mfa.models import Authenticator
        from allauth.socialaccount.models import SocialAccount

        Authenticator.objects.create(user=squatter, type=Authenticator.Type.TOTP, data={"secret": "x"})
        SocialAccount.objects.create(user=squatter, provider="google", uid="squatter-google-uid")

        services.release_unproven_account(squatter, reason="invited_while_unverified")

        assert not Authenticator.objects.filter(user=squatter).exists()
        assert not SocialAccount.objects.filter(user=squatter).exists()

    def test_the_account_and_its_address_stay(self, squatter):
        from allauth.account.models import EmailAddress

        services.release_unproven_account(squatter, reason="invited_while_unverified")

        assert get_user_model().objects.filter(pk=squatter.pk, is_active=True).exists()
        assert EmailAddress.objects.filter(user=squatter, email=squatter.email, verified=False).exists()


class TestTheResetLinkProvesTheMailbox:
    """A password set from the key mailed by «Forgot your password?» (allauth's ``password_reset`` signal)
    proves the mailbox it went to: the account's address becomes verified and primary (L1-A2). Only when
    that address is the only one on record, since the key may have gone to any address of the account."""

    def _reset(self, client, email, password):
        """What /password/reset and the mailed /password/reset/key/<key> post (allauth.headless)."""
        from django.core import mail

        mail.outbox.clear()
        client.post("/_allauth/browser/v1/auth/password/request", {"email": email}, content_type="application/json")
        link = next(word for word in mail.outbox[0].body.split() if "/password/reset/key/" in word)
        key = link.rpartition("/password/reset/key/")[2]
        response = client.post(
            "/_allauth/browser/v1/auth/password/reset", {"key": key, "password": password}, content_type="application/json"
        )
        assert response.status_code in (200, 401), response.content

    def test_an_account_with_no_address_on_record_gets_it_verified(self, client, ana):
        from allauth.account.models import EmailAddress

        self._reset(client, ana.email, "N3w-pass-phrase-ok")

        (address,) = EmailAddress.objects.filter(user=ana)
        assert (address.email, address.verified, address.primary) == (ana.email, True, True)

    def test_its_unverified_address_becomes_verified(self, client, ana):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email=ana.email, primary=True, verified=False)

        self._reset(client, ana.email, "N3w-pass-phrase-ok")

        assert EmailAddress.objects.get(user=ana).verified

    def test_with_another_address_on_record_it_proves_nothing(self, client, ana):
        """The squatter's own verified address could have received the key: the login address stays unproven."""
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email="squatter@example.com", primary=True, verified=True)
        EmailAddress.objects.create(user=ana, email=ana.email, primary=False, verified=False)

        self._reset(client, "squatter@example.com", "N3w-pass-phrase-ok")

        assert not EmailAddress.objects.get(user=ana, email=ana.email).verified

    def test_changing_the_password_while_signed_in_proves_nothing(self, ana):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email=ana.email, primary=True, verified=False)
        ana.set_password("N3w-pass-phrase-ok")
        ana.save()

        assert not EmailAddress.objects.get(user=ana).verified
