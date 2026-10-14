"""The Django admin shows every model of accounts (PLAN-SAAS §6: «el Django admin, lo más completo posible»)."""

import re
from html import escape, unescape
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings

from accounts import services
from accounts.admin import open_hub_admin_url
from accounts.models import AuthExchangeCode, HubMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    admin = get_user_model().objects.create_superuser(email="root@example.com", password="x")
    HubMembership.objects.create(user=admin, hub_slug="a", role=HubMembership.Role.ADMIN)
    services.issue_code(admin, "a")
    client.force_login(admin)
    return client, admin


@pytest.mark.parametrize("model", ["user", "hubmembership", "authexchangecode"])
def test_changelist_and_change_page_load(staff_client, model):
    client, _ = staff_client

    response = client.get(f"/admin/accounts/{model}/")

    assert response.status_code == 200


def test_the_user_change_page_loads(staff_client):
    client, admin = staff_client

    assert client.get(f"/admin/accounts/user/{admin.pk}/change/").status_code == 200


def test_a_user_can_be_added_with_email_and_password(staff_client):
    client, _ = staff_client

    response = client.post(
        "/admin/accounts/user/add/",
        {"email": "bo@example.com", "password1": "a-long-pass-phrase", "password2": "a-long-pass-phrase", "usable_password": "true"},
    )

    assert response.status_code == 302
    assert get_user_model().objects.get(email="bo@example.com").check_password("a-long-pass-phrase")


def test_exchange_codes_are_read_only(staff_client):
    client, _ = staff_client

    assert client.get("/admin/accounts/authexchangecode/add/").status_code == 403


class TestWhoEntersTheAdmin:
    """Only the platform enters the admin: a superuser, or ``support`` (view only); never a customer."""

    @pytest.fixture
    def users(self):
        # demo_seed runs only with DEBUG on (local development); pytest-django turns it off.
        with override_settings(DEBUG=True):
            call_command("demo_seed", stdout=StringIO())
        return get_user_model().objects

    def test_the_owner_of_a_hub_is_sent_to_the_admin_login(self, client, users):
        client.force_login(users.get(email="owner@example.com"))

        response = client.get("/admin/")

        assert response.status_code == 302
        assert response.url == "/admin/login/?next=/admin/"

    def test_the_owner_of_a_hub_cannot_sign_in_to_the_admin(self, client, users):
        response = client.post("/admin/login/", {"username": "owner@example.com", "password": "owner"})

        assert response.status_code == 200
        assert response.context["form"].errors
        assert client.get("/admin/").status_code == 302

    @pytest.mark.parametrize("role", HubMembership.Role.values)
    def test_no_customer_role_enters_the_admin(self, client, ana, role):
        HubMembership.objects.create(user=ana, hub_slug="a", role=role)
        client.force_login(ana)

        assert client.get("/admin/").status_code == 302
        assert client.get("/admin/accounts/user/").status_code == 302

    def test_the_platform_administrator_enters(self, client, users):
        client.force_login(users.get(email="platform@example.com"))

        assert client.get("/admin/").status_code == 200

    def test_support_sees_accounts_but_cannot_add_change_or_delete(self, client, ana):
        helper = get_user_model().objects.create_user(email="help@erplora.com", password="x", is_staff=True)
        helper.groups.add(Group.objects.get(name="support"))
        client.force_login(helper)

        for model in ("user", "hubmembership", "authexchangecode"):
            assert client.get(f"/admin/accounts/{model}/").status_code == 200
        assert client.get(f"/admin/accounts/user/{ana.pk}/change/").status_code == 200
        assert client.get("/admin/accounts/user/add/").status_code == 403
        assert client.post(f"/admin/accounts/user/{ana.pk}/change/", {"email": "x@example.com"}).status_code == 403
        assert client.get(f"/admin/accounts/user/{ana.pk}/delete/").status_code == 403
        assert get_user_model().objects.get(pk=ana.pk).email == "ana@example.com"


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)"', html)
    assert match, f"no hidden input {name!r} in the page"
    return unescape(match.group(1))


class TestOpenInTheHubAdmin:
    """«Open in the Hub admin» (ronda 13, PLAN §18.1.6): from ``erplora.com/admin`` the staff jump to
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
        user, _ = services.create_platform_user("help@erplora.com", "support", password)
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
        response = client.get("/admin/accounts/hubmembership/")

        html = response.content.decode()
        assert response.status_code == 200
        assert self._href("a") in html
        assert self._href("b") in html
        assert "Open in the Hub admin" in html
        assert f'href="{self.HUBS}"' in html

    def test_the_hubs_page_lists_each_hub_once_with_its_button(self, client, platform, ana):
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.EMPLOYEE)

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
        HubMembership.objects.create(user=owner, hub_slug=slug, role=HubMembership.Role.OWNER)

        # One button per valid membership (``demo_seed``: owner and employee of ``a`` and ``b``), and
        # one per hub on the Hubs page; none for the bad row.
        for page, buttons in (("/admin/accounts/hubmembership/", 4), (self.HUBS, 2)):
            response = client.get(page)
            html = response.content.decode()
            assert response.status_code == 200
            assert html.count('href="http://hubs.localhost:8000/auth/login?') == buttons

    def test_the_hubs_page_says_when_there_is_no_hub(self, client, password):
        user, _ = services.create_platform_user("boss@erplora.com", "admin", password)
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

    # A failed jump comes back from the Hub as ``/admin/accounts/hubs/?error=<code>`` (ERPlora/saas#1):
    # the codes of ``hub-next/base/auth.py`` and ``auth_views.py``, and those the SaaS's
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


# --- The Account page (plan 2026-10-13, L3-A) ---------------------------------------------------------------


def _key(user, **fields):
    from accounts.models import ApiKey

    _, prefix, key_hash = ApiKey.new_secret()
    return ApiKey.objects.create(user=user, name="Zapier", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"], **fields)


class TestApiKeys:
    """Read only: an account issues its keys in the Account page, the only place its secret is shown; the admin sees who has
    which key, its scopes and its last use, and a superuser can cut one («revoke»). Never the hash, never a delete:
    revoking is the audit trail (ported from ERPlora/saas ``apps/auth/apikeys/admin.py``)."""

    def test_the_list_and_the_key_load_without_its_hash(self, staff_client, ana):
        client, _ = staff_client
        key = _key(ana)

        listing = client.get("/admin/accounts/apikey/")
        page = client.get(f"/admin/accounts/apikey/{key.pk}/change/")

        assert listing.status_code == page.status_code == 200
        assert "ana@example.com" in listing.text and "erps_live_" in listing.text
        assert key.key_hash not in listing.text + page.text

    def test_keys_are_not_added_nor_deleted_here(self, staff_client, ana):
        client, _ = staff_client
        key = _key(ana)

        assert client.get("/admin/accounts/apikey/add/").status_code == 403
        assert client.get(f"/admin/accounts/apikey/{key.pk}/delete/").status_code == 403

    def test_a_superuser_revokes_on_the_spot(self, staff_client, ana):
        from accounts.models import ApiKey

        client, _ = staff_client
        key = _key(ana)

        response = client.post(
            "/admin/accounts/apikey/", {"action": "revoke", "_selected_action": [str(key.pk)]}, follow=True
        )

        assert response.status_code == 200
        assert ApiKey.objects.get(pk=key.pk).revoked_at is not None

    def test_revoking_here_refreshes_the_owners_live_list(self, staff_client, ana):
        """Through the operation path: the event goes to the owner's channel, as when the owner revokes it."""
        from live.models import OutboxEvent

        from accounts import events

        client, _ = staff_client
        key = _key(ana)

        client.post("/admin/accounts/apikey/", {"action": "revoke", "_selected_action": [str(key.pk)]})

        assert list(OutboxEvent.objects.values_list("name", "scope_key")) == [(events.APIKEY_REVOKED, str(ana.pk))]

    def test_support_sees_the_keys_and_cannot_revoke(self, client, ana):
        from accounts.models import ApiKey

        supporter, _ = services.create_platform_user("support@example.com", services.PLATFORM_SUPPORT, "x")
        client.force_login(supporter)
        key = _key(ana)

        assert client.get("/admin/accounts/apikey/").status_code == 200
        client.post("/admin/accounts/apikey/", {"action": "revoke", "_selected_action": [str(key.pk)]})
        assert ApiKey.objects.get(pk=key.pk).revoked_at is None


def test_the_user_page_shows_the_preferences_and_the_photo(staff_client, ana):
    from accounts.models import ProfilePhoto, UserPreferences

    client, _ = staff_client
    UserPreferences.objects.create(user=ana, theme_mode="dark")
    ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert "Dark" in page.text
    assert "data:image/png;base64,iVBORw==" in page.text


def test_the_sessions_of_allauth_have_their_page(staff_client):
    client, _ = staff_client

    assert client.get("/admin/usersessions/usersession/").status_code == 200


def test_the_sessions_are_searched_by_email(staff_client, ana, password):
    """allauth's own page searched ``user__username``, which this account model has not (a 500)."""
    from django.test import Client

    from accounts.tests.conftest import sign_in

    client, _ = staff_client
    sign_in(Client(), ana.email, password)

    response = client.get("/admin/usersessions/usersession/", {"q": "ana@exa"})

    assert response.status_code == 200
    assert "ana@example.com" in response.text


def test_a_change_of_email_waiting_is_seen_without_its_code_nor_its_session(staff_client, ana):
    from accounts.models import EmailChangeRequest

    client, _ = staff_client
    change = EmailChangeRequest.objects.create(
        user=ana, session_key="secret-session-key-0123456789", email="ana@new.example", code_hash="c0de" * 16
    )

    listing = client.get("/admin/accounts/emailchangerequest/")
    page = client.get(f"/admin/accounts/emailchangerequest/{change.pk}/change/")

    assert listing.status_code == page.status_code == 200
    assert "ana@new.example" in listing.text
    assert "c0de" not in listing.text + page.text and "secret-session-key" not in listing.text + page.text
    assert client.get("/admin/accounts/emailchangerequest/add/").status_code == 403
