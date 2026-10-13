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


class TestSeedDemoOwner:
    def test_creates_a_customer_that_owns_each_hub_and_is_no_staff(self):
        user = services.seed_demo_owner("owner@example.com", "owner", ["a", "b"])

        assert user.check_password("owner")
        assert (user.is_staff, user.is_superuser) == (False, False)
        assert not user.groups.exists()
        assert sorted(user.hub_memberships.values_list("hub_slug", "role")) == [
            ("a", "hub_owner"),
            ("b", "hub_owner"),
        ]

    def test_the_hub_receives_the_owner_role_as_it_is(self):
        owner = services.seed_demo_owner("owner@example.com", "owner", ["a", "b"])

        assert (
            services.redeem_code(services.issue_code(owner, "a"), "a").role
            == "hub_owner"
        )

    def test_running_it_again_changes_nothing(self):
        first = services.seed_demo_owner("owner@example.com", "owner", ["a", "b"])
        again = services.seed_demo_owner("owner@example.com", "owner", ["a", "b"])

        assert again.pk == first.pk
        assert get_user_model().objects.count() == 1
        assert HubMembership.objects.count() == 2


class TestSeedDemoMember:
    """A customer of the demo hubs with any customer role (DEMO-F06 needs an employee)."""

    def test_creates_an_employee_of_each_hub_that_is_no_staff(self):
        user = services.seed_demo_member(
            "employee@example.com", "employee", ["a", "b"], HubMembership.Role.EMPLOYEE
        )

        assert user.check_password("employee")
        assert (user.is_staff, user.is_superuser) == (False, False)
        assert not user.groups.exists()
        assert sorted(user.hub_memberships.values_list("hub_slug", "role")) == [
            ("a", "hub_employee"),
            ("b", "hub_employee"),
        ]

    def test_the_hub_receives_the_employee_role_as_it_is(self):
        employee = services.seed_demo_member(
            "employee@example.com", "employee", ["a"], HubMembership.Role.EMPLOYEE
        )

        assert (
            services.redeem_code(services.issue_code(employee, "a"), "a").role
            == "hub_employee"
        )

    @pytest.mark.parametrize("role", ["platform_admin", "employee", ""])
    def test_refuses_a_role_that_is_not_a_customer_role(self, role):
        with pytest.raises(ValueError):
            services.seed_demo_member("employee@example.com", "employee", ["a"], role)

        assert not get_user_model().objects.exists()

    def test_running_it_again_changes_nothing(self):
        first = services.seed_demo_member(
            "employee@example.com", "employee", ["a", "b"], HubMembership.Role.EMPLOYEE
        )
        again = services.seed_demo_member(
            "employee@example.com", "employee", ["a", "b"], HubMembership.Role.EMPLOYEE
        )

        assert again.pk == first.pk
        assert get_user_model().objects.count() == 1
        assert HubMembership.objects.count() == 2


class TestSeedDemoPlatformAdmin:
    def test_creates_a_superuser_of_the_platform_with_no_hub(self):
        user = services.seed_demo_platform_admin("platform@example.com", "platform")

        assert user.check_password("platform")
        assert (user.is_staff, user.is_superuser) == (True, True)
        assert not user.hub_memberships.exists()

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
