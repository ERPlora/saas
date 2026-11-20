"""«Open in the Hub admin»: the jump from the Django admin to the hub's page in the Hub admin, and why it failed."""

import re
from html import escape, unescape
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from accounts.admin.hub_admin_jump import open_hub_admin_url
from accounts.models import AuthExchangeCode
from accounts.services import platform_staff
from accounts.tests.conftest import enter

pytestmark = pytest.mark.django_db


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)"', html)
    assert match, f"no hidden input {name!r} in the page"
    return unescape(match.group(1))


class TestOpenInTheHubAdmin:
    """«Open in the Hub admin»: from ``erplora.com/admin`` the staff jump to
    ``hubs.erplora.com/admin/hub/<slug>/``. The jump STARTS at the Hub (``/auth/login``), which binds it
    to the browser with its ``state`` cookie and sends it to ``/hub-login/?audience=hub-admin`` (tested
    in ``test_handoff.py``). The staff never type ``hubs.erplora.com``."""

    JUMP = "http://hubs.localhost:8000/auth/login?hub={slug}&next=/admin/hub/{slug}/"
    #: The jump the SaaS admin answered itself before the Hub asked for ``state``.
    OLD_JUMP = "/admin/accounts/hubmembership/open-hub-admin/{slug}/"
    HUBS = "/admin/accounts/hubs/"

    def _href(self, slug: str) -> str:
        return f'href="{escape(self.JUMP.format(slug=slug))}"'

    @pytest.fixture
    def users(self):
        # demo_seed runs only with DEBUG on (local development); pytest-django turns it off.
        with override_settings(DEBUG=True):
            call_command("demo_seed", stdout=StringIO())
        return get_user_model().objects

    @pytest.fixture
    def platform(self, client, users):
        user = users.get(email="platform@example.com")
        client.force_login(user)
        return user

    @pytest.fixture
    def support(self, client, password):
        user, _ = platform_staff.create_platform_user("help@erplora.com", "support", password)
        client.force_login(user)
        return user

    def test_the_button_starts_the_jump_at_the_hub_admin_login_with_the_deep_link(self):
        assert open_hub_admin_url("a") == "http://hubs.localhost:8000/auth/login?hub=a&next=/admin/hub/a/"

    def test_in_production_it_starts_at_hubs_erplora_com(self, settings):
        settings.HUB_ADMIN_ORIGIN = "https://hubs.erplora.com"

        assert open_hub_admin_url("a") == "https://hubs.erplora.com/auth/login?hub=a&next=/admin/hub/a/"

    @pytest.mark.parametrize("slug", ["hubs", "hub", "www", "admin", "A", "ab", "evil.example/x", ""])
    def test_no_button_for_the_platform_host_nor_a_reserved_or_invalid_slug(self, slug):
        assert open_hub_admin_url(slug) is None

    def test_the_old_address_mints_no_code(self, client, platform):
        # A code posted without the Hub's ``state`` is always refused by the Hub: never minted.
        client.get(self.OLD_JUMP.format(slug="a"))

        assert not AuthExchangeCode.objects.exists()

    def test_each_membership_row_has_the_button(self, client, platform):
        response = client.get("/admin/hubs/hubmember/")

        html = response.content.decode()
        assert response.status_code == 200
        assert self._href("a") in html
        assert self._href("b") in html
        assert "Open in the Hub admin" in html
        assert f'href="{self.HUBS}"' in html

    def test_the_hubs_page_lists_each_hub_once_with_its_button(self, client, platform, ana):
        enter(ana, "a", "hub_employee")

        response = client.get(self.HUBS)

        html = response.content.decode()
        assert response.status_code == 200
        assert html.count(self._href("a")) == 1
        assert html.count(self._href("b")) == 1
        # ``demo_seed`` gives each hub two members (owner and employee); ``ana`` is a third in ``a``.
        assert re.search(r"<td>a</td>\s*<td>3</td>", html)
        assert re.search(r"<td>b</td>\s*<td>2</td>", html)
        assert "No hub has members yet." not in html

    @pytest.mark.parametrize("slug", ["hubs", "www", "evil.example/x", ""])
    def test_a_row_saved_with_no_valid_hub_slug_shows_no_button_and_breaks_no_page(self, client, platform, slug):
        # ``objects.create`` skips the validators, as rows that predate the shared rule.
        owner = get_user_model().objects.get(email="owner@example.com")
        enter(owner, slug, "hub_owner")

        # One button per valid membership (``demo_seed``: owner and employee of ``a`` and ``b``), and
        # one per hub on the Hubs page; none for the bad row.
        for page, buttons in (("/admin/hubs/hubmember/", 4), (self.HUBS, 2)):
            response = client.get(page)
            html = response.content.decode()
            assert response.status_code == 200
            assert html.count('href="http://hubs.localhost:8000/auth/login?') == buttons

    def test_the_hubs_page_says_when_there_is_no_hub(self, client, password):
        user, _ = platform_staff.create_platform_user("boss@erplora.com", "admin", password)
        client.force_login(user)

        response = client.get(self.HUBS)

        assert response.status_code == 200
        assert "No hub has members yet." in response.content.decode()

    def test_support_sees_the_hubs_page(self, client, support):
        assert client.get(self.HUBS).status_code == 200

    def test_a_customer_is_sent_from_the_hubs_page_to_the_admin_login(self, client, users):
        client.force_login(users.get(email="owner@example.com"))

        response = client.get(self.HUBS)

        assert response.status_code == 302
        assert response.url.startswith("/admin/login/")

    def test_staff_who_may_not_view_memberships_do_not_see_the_hubs(self, client, ana):
        ana.is_staff = True
        ana.save()
        client.force_login(ana)

        assert client.get(self.HUBS).status_code == 403

    def test_the_button_is_translated_to_spanish(self, client, platform):
        response = client.get(self.HUBS, headers={"Accept-Language": "es"})

        assert "Abrir en el admin del Hub" in response.content.decode()

    # A failed jump comes back from the Hub as ``/admin/accounts/hubs/?error=<code>``:
    # the codes of the Hub's ``base/auth.py`` and ``auth_views.py``, and those the SaaS's
    # ``/internal/auth/redeem`` answers with a 400, which the Hub forwards as they are.
    @pytest.mark.parametrize(
        ("code", "text"),
        [
            ("invalid_code", "The access to the Hub admin expired or was already used. Open it again from this page."),
            (
                "invalid_request",
                "The Hub sent ERPlora a request it could not read. Try again; if it keeps happening, "
                "tell the development team.",
            ),
            (
                "hub_unauthorized",
                "ERPlora rejected the Hub's signed request (wrong internal key or clock out of sync). "
                "Tell the development team.",
            ),
            ("saas_unavailable", "The Hub could not reach ERPlora to check the access. Try again in a moment."),
            (
                "unknown_role",
                "The Hub does not accept your account's role. Only ERPlora's administrators and support "
                "can open the Hub admin.",
            ),
            ("not_platform_staff", "Your account is not part of ERPlora's staff, so it cannot open the Hub admin."),
            (
                "user_inactive",
                "Your account is deactivated in the Hub admin. Ask an ERPlora administrator to reactivate it.",
            ),
        ],
    )
    def test_the_hubs_page_says_why_the_jump_failed(self, client, platform, code, text):
        response = client.get(self.HUBS, {"error": code})

        html = unescape(response.content.decode())
        assert response.status_code == 200
        assert '<ul class="messagelist">' in html
        assert f'<li class="error">{text}</li>' in html

    def test_an_unknown_error_gets_a_generic_message_and_is_never_echoed(self, client, platform):
        response = client.get(self.HUBS, {"error": "zz_forged<b>bold</b>"})

        html = response.content.decode()
        assert response.status_code == 200
        assert '<li class="error">The Hub admin could not be opened. Try again from this page.</li>' in html
        assert "zz_forged" not in html
        assert "<b>bold</b>" not in html

    def test_an_empty_error_still_says_the_jump_failed(self, client, platform):
        html = client.get(self.HUBS, {"error": ""}).content.decode()

        assert '<li class="error">The Hub admin could not be opened. Try again from this page.</li>' in html

    def test_without_an_error_the_hubs_page_shows_no_message(self, client, platform):
        html = client.get(self.HUBS).content.decode()

        assert "messagelist" not in html

    def test_the_failed_jump_is_said_in_spanish(self, client, platform):
        response = client.get(self.HUBS, {"error": "invalid_code"}, headers={"Accept-Language": "es"})

        html = unescape(response.content.decode())
        assert (
            '<li class="error">El acceso al admin del Hub ha caducado o ya se usó. '
            "Vuelve a abrirlo desde esta página.</li>"
        ) in html

    def test_the_generic_failure_is_said_in_spanish(self, client, platform):
        response = client.get(self.HUBS, {"error": "whatever"}, headers={"Accept-Language": "es"})

        html = unescape(response.content.decode())
        assert '<li class="error">No se pudo abrir el admin del Hub. Vuelve a intentarlo desde esta página.</li>' in html
