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
                {"slug": "a", "host": "a.localhost:8000", "url": "/hub-login/?hub=a&next=/"},
                {"slug": "b", "host": "b.localhost:8000", "url": "/hub-login/?hub=b&next=/"},
            ]
        }

    def test_an_account_without_hubs_gets_an_empty_list(self, ana):
        assert queries.hub_list(_ctx(ana), HubListIn()).model_dump() == {"hubs": []}

    def test_the_host_comes_from_the_callback_setting(self, ana, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)

        [hub] = queries.hub_list(_ctx(ana), HubListIn()).hubs

        assert hub.host == "a.erplora.com"

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


@pytest.mark.parametrize(
    ("next_path", "url"),
    [("/", "/hub-login/?hub=a&next=/"), ("/demo/items?x=1", "/hub-login/?hub=a&next=/demo/items%3Fx%3D1")],
)
def test_hub_login_url_is_the_jump_to_a_hub(next_path, url):
    assert queries.hub_login_url("a", next_path) == url


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
