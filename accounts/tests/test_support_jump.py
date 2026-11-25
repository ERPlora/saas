"""ERPlora's support entering a business that lets it in.

erplora.com gives a person of the platform's staff (a superuser or the ``support`` group) a ``hub-session`` code with
the role ``hub_support`` for a business they are no member of, and the admin's «Enter as support» starts that jump at
the business. The business decides: with its support access off, the Hub refuses the code with a page of its own.
"""

import json
import logging
import re
import secrets
import time
from html import escape, unescape

import pytest

from accounts.admin import hub_admin_jump
from accounts.models import AuthExchangeCode
from accounts.services import hub_jump, platform_staff
from accounts.signing import sign
from accounts.tests.conftest import enter

pytestmark = pytest.mark.django_db

HUB_SUPPORT = "hub_support"
STATE = secrets.token_urlsafe(32)
SECRET = "test-internal-secret"
HUBS_PAGE = "/admin/accounts/hubs/"


@pytest.fixture
def support(password):
    user, _ = platform_staff.create_platform_user("help@erplora.com", "support", password)
    user.first_name, user.last_name = "Sam", "Port"
    user.save()
    return user


@pytest.fixture
def platform_admin(password):
    user, _ = platform_staff.create_platform_user("boss@erplora.com", "admin", password)
    return user


@pytest.fixture
def staff_without_a_platform_role(ana):
    ana.is_staff = True
    ana.save()
    return ana


@pytest.fixture
def inactive_support(support):
    support.is_active = False
    support.save()
    return support


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)"', html)
    assert match, f"no hidden input {name!r} in the page"
    return unescape(match.group(1))


class TestTheCodeOfSupport:
    def test_support_gets_a_hub_session_code_for_a_business_it_is_no_member_of(self, support):
        code = hub_jump.issue_code(support, "a")

        row = AuthExchangeCode.objects.get()
        assert row.code_hash == AuthExchangeCode.hash_code(code)
        assert (row.user, row.hub_slug, row.audience, row.used_at) == (support, "a", "hub-session", None)

    def test_redeeming_it_says_who_of_support_comes_in_with_the_role_hub_support(self, support):
        code = hub_jump.issue_code(support, "a")

        assert hub_jump.redeem_code(code, "a") == hub_jump.HubIdentity(
            user_id=str(support.pk),
            email="help@erplora.com",
            name="Sam Port",
            locale=support.language,
            role=HUB_SUPPORT,
        )

    def test_a_platform_admin_comes_in_as_support_too(self, platform_admin):
        code = hub_jump.issue_code(platform_admin, "a")

        assert hub_jump.redeem_code(code, "a").role == HUB_SUPPORT

    def test_a_member_of_the_business_comes_in_with_their_own_role(self, platform_admin):
        enter(platform_admin, "a", "hub_manager")
        code = hub_jump.issue_code(platform_admin, "a")

        assert hub_jump.redeem_code(code, "a").role == "hub_manager"

    @pytest.mark.parametrize("who", ["ana", "staff_without_a_platform_role", "inactive_support"])
    def test_nobody_else_gets_a_code_for_a_business_they_are_no_member_of(self, request, who):
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(request.getfixturevalue(who), "a")

        assert not AuthExchangeCode.objects.exists()

    @pytest.mark.parametrize("slug", ["hubs", "www", "A", ""])
    def test_the_platform_host_and_reserved_or_invalid_slugs_are_no_business(self, support, slug):
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(support, slug)

    def test_the_hub_admin_code_of_support_never_carries_hub_support(self, support):
        code = hub_jump.issue_code(support, "a", audience="hub-admin")

        assert hub_jump.redeem_code(code, "a", audience="hub-admin").role == "platform_support"

    @pytest.mark.parametrize("demote", ["groups", "is_active"])
    def test_support_that_lost_its_role_before_redeeming_enters_nothing(self, support, demote):
        code = hub_jump.issue_code(support, "a")
        if demote == "groups":
            support.groups.clear()
        else:
            support.is_active = False
            support.save()

        with pytest.raises(hub_jump.InvalidCode):
            hub_jump.redeem_code(code, "a")

    def test_each_code_of_support_leaves_a_log_line_with_the_account_and_the_business(self, support, caplog):
        with caplog.at_level(logging.INFO, logger="accounts.services.hub_jump"):
            hub_jump.issue_code(support, "a")

        assert f"hub_login.hub_support user={support.pk} hub=a" in caplog.messages

    def test_a_member_leaves_no_such_line(self, platform_admin, caplog):
        enter(platform_admin, "a", "hub_manager")

        with caplog.at_level(logging.INFO, logger="accounts.services.hub_jump"):
            hub_jump.issue_code(platform_admin, "a")

        assert not [line for line in caplog.messages if line.startswith("hub_login.hub_support")]


class TestTheSecondFactorOfSupport:
    def test_with_the_flag_on_support_needs_it_even_without_an_authenticator_app(self, support, mfa_on):
        with pytest.raises(hub_jump.SecondFactorRequired):
            hub_jump.issue_code(support, "a")

        assert not AuthExchangeCode.objects.exists()

    def test_with_the_second_factor_passed_support_gets_its_code(self, support, mfa_on):
        hub_jump.issue_code(support, "a", second_factor=True)

        assert AuthExchangeCode.objects.count() == 1

    def test_a_member_without_an_app_still_needs_none(self, platform_admin, mfa_on):
        enter(platform_admin, "a", "hub_manager")

        hub_jump.issue_code(platform_admin, "a")

        assert AuthExchangeCode.objects.count() == 1


class TestTheJumpOfSupport:
    def test_signed_in_support_gets_the_form_that_posts_its_code_to_the_business(self, client, support):
        client.force_login(support)

        response = client.get("/hub-login/", {"hub": "a", "next": "/", "state": STATE})

        html = response.content.decode()
        assert response.status_code == 200
        assert 'action="http://a.localhost:8000/auth/callback"' in html
        assert _hidden(html, "state") == STATE
        assert hub_jump.redeem_code(_hidden(html, "code"), "a").role == HUB_SUPPORT

    def test_staff_without_a_platform_role_get_the_error_page_and_no_code(self, client, staff_without_a_platform_role):
        client.force_login(staff_without_a_platform_role)

        response = client.get("/hub-login/", {"hub": "a", "next": "/", "state": STATE})

        assert response.status_code == 302
        assert response.url == "/login/error?code=not_a_member&hub=a"
        assert not AuthExchangeCode.objects.exists()

    def test_the_hub_receives_hub_support_when_it_redeems_the_code(self, client, support, settings):
        settings.INTERNAL_SHARED_SECRET = SECRET
        body = json.dumps({"code": hub_jump.issue_code(support, "a"), "hub": "a"}).encode()
        timestamp = int(time.time())
        headers = {"X-Erplora-Timestamp": str(timestamp), "X-Erplora-Signature": sign(body, timestamp, SECRET)}

        response = client.post("/internal/auth/redeem", body, content_type="application/json", headers=headers)

        assert response.status_code == 200
        assert response.json() == {
            "user_id": str(support.pk),
            "email": "help@erplora.com",
            "name": "Sam Port",
            "locale": support.language,
            "role": HUB_SUPPORT,
        }


class TestEnterAsSupport:
    """«Enter as support» of the SaaS admin: it starts the jump at the business (``/auth/login``), which binds it to the
    browser with its ``state`` and sends it to ``/hub-login/``, as every jump into a business."""

    ENTRY = "http://a.localhost:8000/auth/login?next=/"

    @pytest.fixture
    def signed_in_support(self, client, support, ana):
        enter(ana, "a", "hub_employee")
        client.force_login(support)
        return client

    def test_the_button_starts_the_jump_at_the_business(self):
        assert hub_admin_jump.enter_as_support_url("a") == self.ENTRY

    def test_in_production_it_starts_at_the_address_of_the_business(self, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

        assert hub_admin_jump.enter_as_support_url("a") == "https://a.erplora.com/auth/login?next=/"

    @pytest.mark.parametrize("slug", ["hubs", "hub", "www", "A", "evil.example/x", ""])
    def test_no_button_for_the_platform_host_nor_a_reserved_or_invalid_slug(self, slug):
        assert hub_admin_jump.enter_as_support_url(slug) is None

    def test_each_business_of_the_hubs_page_has_it_once(self, signed_in_support):
        response = signed_in_support.get(HUBS_PAGE)

        html = response.content.decode()
        assert response.status_code == 200
        assert html.count(f'href="{escape(self.ENTRY)}"') == 1
        assert "Enter as support" in html

    def test_the_record_of_the_business_has_it(self, signed_in_support):
        from hubs.models import Hub

        response = signed_in_support.get(f"/admin/hubs/hub/{Hub.objects.get(slug='a').pk}/change/")

        html = response.content.decode()
        assert response.status_code == 200
        assert f'href="{escape(self.ENTRY)}"' in html
        assert "Enter as support" in html

    def test_it_is_said_in_spanish(self, signed_in_support):
        response = signed_in_support.get(HUBS_PAGE, headers={"Accept-Language": "es"})

        assert "Entrar como soporte" in response.content.decode()
