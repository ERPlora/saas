"""Reads of accounts: the hubs a user can enter, and the query the launcher (/launch) reads them with."""

import pytest
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import translation
from live.errors import Unauthorized

from accounts import queries
from accounts.models import HubMembership
from accounts.schemas import HubListIn

pytestmark = pytest.mark.django_db


def test_hub_slugs_of_lists_the_user_hubs_in_alphabetical_order(ana):
    HubMembership.objects.create(user=ana, hub_slug="b", role=HubMembership.Role.EMPLOYEE)
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.ADMIN)
    bo = get_user_model().objects.create_user(email="bo@example.com", password="x")
    HubMembership.objects.create(user=bo, hub_slug="c", role=HubMembership.Role.ADMIN)

    assert queries.hub_slugs_of(ana) == ["a", "b"]


def test_a_user_without_memberships_has_no_hubs(ana):
    assert queries.hub_slugs_of(ana) == []


def test_hubs_with_members_lists_every_hub_once_with_its_member_count(ana):
    """The «Hubs» page of the admin (ronda 13): one row per hub, whoever its members are."""
    bo = get_user_model().objects.create_user(email="bo@example.com", password="x")
    HubMembership.objects.create(user=ana, hub_slug="b", role=HubMembership.Role.OWNER)
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)
    HubMembership.objects.create(user=bo, hub_slug="a", role=HubMembership.Role.EMPLOYEE)

    assert queries.hubs_with_members() == [("a", 2), ("b", 1)]


def test_without_memberships_there_is_no_hub():
    assert queries.hubs_with_members() == []


@pytest.mark.parametrize(("slug", "link"), [("a", "/admin/hub/a/"), ("0day", "/admin/hub/0day/")])
def test_the_deep_link_of_a_hub_in_the_hub_admin(slug, link):
    """``hubs.erplora.com/admin/hub/<slug>/`` fixes that hub in the Hub admin's session (PLAN §18.1.5)."""
    assert queries.hub_admin_path(slug) == link


def test_active_user_reads_the_account_again(ana):
    get_user_model().objects.filter(pk=ana.pk).update(first_name="Anabel")

    assert queries.active_user(ana.pk).first_name == "Anabel"


def test_active_user_is_none_for_a_deactivated_or_deleted_account(ana):
    get_user_model().objects.filter(pk=ana.pk).update(is_active=False)
    assert queries.active_user(ana.pk) is None

    get_user_model().objects.filter(pk=ana.pk).delete()
    assert queries.active_user(ana.pk) is None


# accounts.hub.list: the launcher's hubs (the Vue page /launch), as the query operation of the SPA.


def _ctx(actor):
    from live.context import OperationContext, Scope

    return OperationContext(scope=Scope("user", str(actor.pk) if actor else "anonymous"), actor=actor)


class TestHubList:
    def test_is_a_query_open_to_any_signed_in_account(self):
        assert (queries.hub_list.name, queries.hub_list.kind, queries.hub_list.permission) == (
            "accounts.hub.list",
            "query",
            None,
        )

    def test_lists_the_hubs_of_the_account_with_their_host_and_the_jump_to_each(self, ana):
        HubMembership.objects.create(user=ana, hub_slug="b", role=HubMembership.Role.EMPLOYEE)
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)
        bo = get_user_model().objects.create_user(email="bo@example.com", password="x")
        HubMembership.objects.create(user=bo, hub_slug="c", role=HubMembership.Role.OWNER)

        result = queries.hub_list(_ctx(ana), HubListIn())

        assert result.model_dump() == {
            "hubs": [
                {"slug": "a", "host": "a.localhost:8000", "url": "http://a.localhost:8000/auth/login?next=/"},
                {"slug": "b", "host": "b.localhost:8000", "url": "http://b.localhost:8000/auth/login?next=/"},
            ]
        }

    def test_an_account_without_hubs_gets_an_empty_list(self, ana):
        assert queries.hub_list(_ctx(ana), HubListIn()).model_dump() == {"hubs": []}

    def test_the_host_comes_from_the_callback_setting(self, ana, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)

        [hub] = queries.hub_list(_ctx(ana), HubListIn()).hubs

        assert hub.host == "a.erplora.com"
        assert hub.url == "https://a.erplora.com/auth/login?next=/"

    def test_an_anonymous_caller_is_refused(self):
        with pytest.raises(Unauthorized):
            queries.hub_list(_ctx(None), HubListIn())

    def test_the_refusal_speaks_the_language_of_the_request(self):
        with translation.override("es"), pytest.raises(Unauthorized) as refused:
            queries.hub_list(_ctx(None), HubListIn())

        assert refused.value.message == "Inicia sesión para ver tus negocios."


def test_hub_origin_is_the_scheme_and_host_of_the_hub_callback(settings):
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

    assert queries.hub_origin("a") == "https://a.erplora.com"
    # The SPA fills the slug in itself (spa-config `hubOrigin`).
    assert queries.hub_origin("{slug}") == "https://{slug}.erplora.com"


# The jump to a hub starts at the hub (``/auth/login``): it sets the ``state`` cookie of that browser
# and only then sends it to the SaaS's ``/hub-login/`` (login CSRF). A link straight to ``/hub-login/``
# carries no ``state`` and the Hub refuses it.


@pytest.mark.parametrize(
    ("next_path", "url"),
    [
        ("/", "http://a.localhost:8000/auth/login?next=/"),
        ("/demo/items?x=1", "http://a.localhost:8000/auth/login?next=/demo/items%3Fx%3D1"),
    ],
)
def test_hub_start_url_is_the_hubs_own_login_keeping_next(next_path, url):
    assert queries.hub_start_url("a", next_path) == url


def test_hub_start_url_lands_on_the_hub_home_by_default():
    assert queries.hub_start_url("a") == "http://a.localhost:8000/auth/login?next=/"


def test_in_production_the_hub_start_url_is_on_erplora_com(settings):
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

    assert queries.hub_start_url("a", "/demo/items") == "https://a.erplora.com/auth/login?next=/demo/items"


@pytest.mark.parametrize("next_path", ["", "//evil.example/x", "https://evil.example/x", "javascript:alert(1)", "/\\evil"])
def test_a_next_that_is_not_a_local_path_becomes_the_hub_home(next_path):
    assert queries.hub_start_url("a", next_path) == "http://a.localhost:8000/auth/login?next=/"


# The second factor (accounts/mfa.py): whether an account has an authenticator app, and whether
# an authenticator named by the session's records is the account's own.


def test_has_totp_with_an_authenticator_app(ana):
    TOTP.activate(ana, generate_totp_secret())

    assert queries.has_totp(ana) is True


def test_recovery_codes_alone_are_no_authenticator_app(ana):
    RecoveryCodes.activate(ana)

    assert queries.has_totp(ana) is False


def test_an_anonymous_visitor_has_no_authenticator_app():
    assert queries.has_totp(AnonymousUser()) is False


def test_owns_authenticator_with_one_of_its_own(ana):
    totp = TOTP.activate(ana, generate_totp_secret()).instance
    codes = RecoveryCodes.activate(ana).instance

    assert queries.owns_authenticator(ana, {totp.pk}) is True
    assert queries.owns_authenticator(ana, {codes.pk, 0}) is True


def test_owns_authenticator_not_with_another_accounts(ana):
    bo = get_user_model().objects.create_user(email="bo@example.com", password="x")
    theirs = TOTP.activate(bo, generate_totp_secret()).instance

    assert queries.owns_authenticator(ana, {theirs.pk}) is False


def test_owns_authenticator_not_without_ids(ana):
    TOTP.activate(ana, generate_totp_secret())

    assert queries.owns_authenticator(ana, set()) is False
    assert queries.owns_authenticator(ana, {None}) is False


# --- Who proved their email, and who has a way in (saas#2541; L1-A2) ----------------------------


class TestEmailIsProven:
    """``email_is_proven``: an account holds an address by proof, not by having typed it first (saas#2541).

    Proven = a **verified** ``EmailAddress`` for that address. Nothing to prove (so proven): staff, and
    an account with **no** address on record (made by an invitation, by the console or by staff, never
    signed up by itself).
    """

    def _address(self, user, email, verified, primary=True):
        from allauth.account.models import EmailAddress

        return EmailAddress.objects.create(user=user, email=email, verified=verified, primary=primary)

    def test_an_account_with_no_address_on_record_has_nothing_to_prove(self, ana):
        assert queries.email_is_proven(ana, "ana@example.com") is True

    def test_a_verified_address_is_proof(self, ana):
        self._address(ana, "ana@example.com", verified=True)

        assert queries.email_is_proven(ana, "ANA@example.com") is True

    def test_an_address_never_verified_is_no_proof(self, ana):
        self._address(ana, "ana@example.com", verified=False)

        assert queries.email_is_proven(ana, "ana@example.com") is False

    def test_a_verified_address_that_is_another_one_proves_nothing(self, ana):
        self._address(ana, "squatter@example.com", verified=True)
        self._address(ana, "ana@example.com", verified=False, primary=False)

        assert queries.email_is_proven(ana, "ana@example.com") is False

    def test_staff_have_nothing_to_prove(self, ana):
        ana.is_staff = True
        ana.save(update_fields=["is_staff"])
        self._address(ana, "ana@example.com", verified=False)

        assert queries.email_is_proven(ana, "ana@example.com") is True


class TestEmailHasAccount:
    """``email_has_account``: whether the unified login signs in (an account holds the address) or signs up
    (``accounts.unified_login``). The account's own email and any address on record count, whatever the case."""

    def test_the_accounts_email_has_an_account(self, ana):
        assert queries.email_has_account("ana@example.com") is True

    def test_whatever_its_case(self, ana):
        assert queries.email_has_account("Ana@Example.COM") is True

    def test_an_address_on_record_has_an_account(self, ana):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email="ana.old@example.com", verified=False, primary=False)

        assert queries.email_has_account("ANA.OLD@example.com") is True

    def test_an_invited_account_without_a_password_has_an_account(self):
        get_user_model().objects.create_user(email="invited@example.com", password=None)

        assert queries.email_has_account("invited@example.com") is True

    def test_an_unknown_email_has_none(self, ana):
        assert queries.email_has_account("new@example.com") is False


class TestHasNoWayIn:
    """``has_no_way_in``: no usable password and no linked Google: the person must claim the account first
    (the invitation's mail then says how)."""

    def test_an_account_with_a_password_has_a_way_in(self, ana):
        assert queries.has_no_way_in(ana) is False

    def test_an_account_without_a_password_nor_google_has_none(self, ana):
        ana.set_unusable_password()
        ana.save(update_fields=["password"])

        assert queries.has_no_way_in(ana) is True

    def test_a_linked_google_is_a_way_in(self, ana):
        from allauth.socialaccount.models import SocialAccount

        ana.set_unusable_password()
        ana.save(update_fields=["password"])
        SocialAccount.objects.create(user=ana, provider="google", uid="ana-google")

        assert queries.has_no_way_in(ana) is False
