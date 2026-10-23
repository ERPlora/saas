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


@pytest.mark.parametrize("query", ["lp@example", "Lucía", "Pérez"])
def test_the_staff_find_an_account_by_its_email_or_its_names(staff_client, query):
    """ACCOUNTS-F13: «El personal busca una cuenta por correo o nombre»; the names are not in the address."""
    client, _ = staff_client
    get_user_model().objects.create_user(email="lp@example.com", password="x", first_name="Lucía", last_name="Pérez")

    response = client.get("/admin/accounts/user/", {"q": query})

    assert [user.email for user in response.context["cl"].result_list] == ["lp@example.com"]


@pytest.mark.parametrize(
    ("filters", "found"),
    [
        ({"language__exact": "es"}, ["ana@example.com"]),
        ({"is_staff__exact": "1"}, ["root@example.com"]),
        ({"is_active__exact": "0"}, []),
    ],
)
def test_the_staff_filter_the_accounts_by_active_staff_and_language(staff_client, ana, filters, found):
    """ACCOUNTS-F13: «… o filtra por activa, personal e idioma»."""
    client, _ = staff_client

    response = client.get("/admin/accounts/user/", filters)

    assert sorted(user.email for user in response.context["cl"].result_list) == found
    # The admin answers any lookup on a field of its own: the filters must be offered on the page too.
    offered = {spec.field_path for spec in response.context["cl"].filter_specs}
    assert {"is_active", "is_staff", "language"} <= offered


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
        """The admin's login signs nobody in: it hands over to the SaaS's sign-in (``test_mfa``)."""
        response = client.post("/admin/login/", {"username": "owner@example.com", "password": "owner"})

        assert (response.status_code, response.url) == (302, "/launch?next=/admin/")
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
    """An account issues its keys in the Account page; the admin sees who has which key, its scopes and its last use, a
    superuser can cut one («revoke») and issue one for a team account (``TestTheSuperuserIssuesAKey``). Never the hash,
    never a delete: revoking is the audit trail (ported from ERPlora/saas ``apps/auth/apikeys/admin.py``)."""

    def test_the_list_and_the_key_load_without_its_hash(self, staff_client, ana):
        client, _ = staff_client
        key = _key(ana)

        listing = client.get("/admin/accounts/apikey/")
        page = client.get(f"/admin/accounts/apikey/{key.pk}/change/")

        assert listing.status_code == page.status_code == 200
        assert "ana@example.com" in listing.text and "erps_live_" in listing.text
        assert key.key_hash not in listing.text + page.text

    @pytest.mark.parametrize(
        ("language", "heading", "labels"),
        [
            ("en", "Permissions", "Businesses · read, Invoices · read"),
            ("es", "Permisos", "Negocios · lectura, Facturas · lectura"),
        ],
    )
    def test_the_permissions_are_named_as_the_panel_names_them(self, staff_client, ana, language, heading, labels):
        """ACCOUNTS-F33: the list and the key's page say what a key may open in words, never the raw scope list."""
        client, _ = staff_client
        key = _key(ana)
        key.scopes = ["hubs.read", "billing.read"]
        key.save(update_fields=["scopes"])

        listing = unescape(client.get("/admin/accounts/apikey/", headers={"Accept-Language": language}).text)
        page = unescape(
            client.get(f"/admin/accounts/apikey/{key.pk}/change/", headers={"Accept-Language": language}).text
        )

        for html in (listing, page):
            assert labels in html
            assert "hubs.read" not in html and "billing.read" not in html
        assert re.search(rf'class="column-permissions">\s*<div class="text"><span>{heading}</span>', listing)
        assert f"<label>{heading}:</label>" in page

    def test_keys_are_not_changed_nor_deleted_here(self, staff_client, ana):
        client, _ = staff_client
        key = _key(ana)

        assert client.post(f"/admin/accounts/apikey/{key.pk}/change/", {"name": "Other"}).status_code == 403
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


class TestTheSuperuserIssuesAKey:
    """ACCOUNTS-G101 (ACCOUNTS-F31; PLAN-SAAS §1.1, ronda 2026-10-15b: «Admin de ApiKey … SE PORTA «Emitir» para el
    superusuario (la clave se enseña una vez)»): a superuser issues a key for a TEAM account (the old SaaS's
    ``user_not_staff``: a customer's key is only the customer's), and the key is shown on the answer once, never kept
    in clear, in the session or in a message. The owner is told by mail and its live list refreshes."""

    ADD = "/admin/accounts/apikey/add/"

    @pytest.fixture
    def teammate(self, password):
        user, _ = services.create_platform_user("qa@erplora.com", services.PLATFORM_SUPPORT, password)
        return user

    def _issue(self, client, user, **fields):
        return client.post(
            self.ADD, {"user": str(user.pk), "name": "QA monitor", "scopes": ["hubs.read"], "expires_in_days": "30", **fields}
        )

    def test_the_service_refuses_a_customer_whatever_the_form_offers(self, staff_client, ana):
        """The form offers team accounts only; the service holds the line on its own (the old ``user_not_staff``)."""
        from live.errors import NotFound

        _, root = staff_client
        with pytest.raises(NotFound):
            services.issue_api_key(ana, name="Monitor", scopes=["hubs.read"], expires_in_days=30, by=root)
        assert not ana.api_keys.exists()

    @pytest.mark.parametrize(
        ("language", "labels"),
        [("en", ["User:", "Name:", "Permissions:", "Expires:"]), ("es", ["Usuario:", "Nombre:", "Permisos:", "Caduca:"])],
    )
    def test_the_form_names_each_field_alike(self, staff_client, language, labels):
        """Django capitalises the labels it takes from the model («User:», «Name:»), not the form's own: «permissions:»
        and «expires:» stood out in lower case."""
        client, _ = staff_client

        page = client.get(self.ADD, HTTP_ACCEPT_LANGUAGE=language).text

        assert [unescape(label).strip() for label in re.findall(r"<(?:label|legend)[^>]*>([^<]+:)</(?:label|legend)>", page)][:4] == labels

    def test_the_form_offers_only_team_accounts(self, staff_client, teammate, ana):
        client, _ = staff_client

        page = client.get(self.ADD)

        assert page.status_code == 200
        assert "qa@erplora.com" in page.text and "ana@example.com" not in page.text

    def test_the_key_is_shown_once_and_only_its_hash_is_kept(self, staff_client, teammate):
        from accounts.models import ApiKey

        client, _ = staff_client

        response = self._issue(client, teammate)

        assert response.status_code == 200
        secret = re.search(r'data-api-key-secret="(erps_live_[A-Za-z0-9]{48})"', response.text).group(1)
        key = ApiKey.objects.get()
        assert (key.user, key.name, key.scopes, key.key_hash) == (teammate, "QA monitor", ["hubs.read"], ApiKey.hash_key(secret))
        assert key.expires_at is not None
        assert secret not in str(dict(client.session))
        assert secret not in client.get(f"/admin/accounts/apikey/{key.pk}/change/").text
        assert secret not in client.get("/admin/accounts/apikey/").text

    def test_the_owner_is_told_by_mail_and_its_live_list_refreshes(
        self, staff_client, teammate, mailoutbox, django_capture_on_commit_callbacks
    ):
        from live.models import OutboxEvent

        from accounts import events

        client, _ = staff_client

        with django_capture_on_commit_callbacks(execute=True):
            self._issue(client, teammate)

        assert [message.to for message in mailoutbox] == [["qa@erplora.com"]]
        assert list(OutboxEvent.objects.values_list("name", "scope_key")) == [(events.APIKEY_CREATED, str(teammate.pk))]

    def test_a_customer_account_gets_no_key_from_here(self, staff_client, ana):
        from accounts.models import ApiKey

        client, _ = staff_client

        response = self._issue(client, ana)

        assert response.status_code == 200
        assert "errorlist" in response.text
        assert not ApiKey.objects.exists()

    def test_without_a_permission_or_a_name_nothing_is_issued(self, staff_client, teammate):
        from accounts.models import ApiKey

        client, _ = staff_client

        assert "errorlist" in self._issue(client, teammate, scopes=[]).text
        assert "errorlist" in self._issue(client, teammate, name="  ").text
        assert not ApiKey.objects.exists()

    def test_the_page_of_the_key_speaks_spanish(self, staff_client, teammate):
        client, _ = staff_client

        response = client.post(
            self.ADD,
            {"user": str(teammate.pk), "name": "QA", "scopes": ["hubs.read"], "expires_in_days": ""},
            headers={"Accept-Language": "es"},
        )

        html = unescape(response.content.decode())
        assert "La clave «QA» de qa@erplora.com está lista. Cópiala ahora: no se volverá a mostrar." in html
        assert "Volver a las claves de API" in html
        assert response.headers["Cache-Control"].startswith("max-age=0")
        assert "no-store" in response.headers["Cache-Control"]

    def test_support_cannot_issue(self, client, teammate):
        supporter, _ = services.create_platform_user("support@example.com", services.PLATFORM_SUPPORT, "x")
        client.force_login(supporter)

        assert client.get(self.ADD).status_code == 403
        assert self._issue(client, teammate).status_code == 403


def test_the_user_page_shows_the_preferences_and_the_photo(staff_client, ana):
    from accounts.models import ProfilePhoto, UserPreferences

    client, _ = staff_client
    UserPreferences.objects.create(user=ana, theme_mode="dark")
    ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert "Dark" in page.text
    assert "data:image/png;base64,iVBORw==" in page.text


def test_the_user_page_hides_the_preferences_and_the_photo_it_never_saved(staff_client, ana):
    """ACCOUNTS-G35/G36: an account on the defaults has no row there; an empty read-only box says nothing."""
    from accounts.models import HubMembership, ProfilePhoto, UserPreferences

    client, _ = staff_client

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert [inline.opts.model for inline in page.context["inline_admin_formsets"]] == [HubMembership]

    UserPreferences.objects.create(user=ana, theme_mode="dark")
    ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")
    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert [inline.opts.model for inline in page.context["inline_admin_formsets"]] == [
        UserPreferences,
        ProfilePhoto,
        HubMembership,
    ]


def test_the_user_page_shows_the_terms_it_accepted_read_only(staff_client, ana):
    """ACCOUNTS-G119: what the account accepted and when, as evidence; nobody edits it."""
    from datetime import UTC, date, datetime

    client, _ = staff_client
    get_user_model().objects.filter(pk=ana.pk).update(
        terms_accepted_at=datetime(2026, 10, 14, 9, 30, tzinfo=UTC), terms_version=date(2026, 10, 13), privacy_version=date(2026, 10, 13)
    )

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert "Terms accepted at" in page.text
    assert "Oct. 14, 2026" in page.text
    for field in ("terms_accepted_at", "terms_version", "privacy_version"):
        assert f'name="{field}"' not in page.text


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


def _signed_in_browser(email: str, password: str):
    from django.test import Client

    from accounts.tests.conftest import sign_in

    return sign_in(Client(), email, password)


class TestTheSessionsSpeakTheStaffsLanguage:
    """ACCOUNTS-F19: «Sesiones de usuario» in the staff's language. allauth.usersessions gives its model and its columns
    no names of their own (Django's «user session», «created at», «user agent»…, English in every language), so the
    admin names them; only the live names: allauth's migrations stay as they are."""

    @pytest.fixture
    def spanish_staff(self, client):
        """The admin speaks the browser's language (``Accept-Language``), not the account's: that is the panel's."""
        staff = get_user_model().objects.create_superuser(email="raiz@example.com", password="x", language="es")
        client.force_login(staff)
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        return client

    def test_the_list_is_named_and_headed_in_spanish(self, spanish_staff, ana, password):
        _signed_in_browser(ana.email, password)

        page = spanish_staff.get("/admin/usersessions/usersession/").text
        headers = re.findall(r'<th scope="col"[^>]*>.*?<div class="text">(?:<(?:a|span)[^>]*>)?([^<]+)<', page, re.S)

        assert "Seleccione sesión de usuario para ver" in page
        assert "1 sesión de usuario" in " ".join(page.split())
        assert [unescape(header).strip() for header in headers] == [
            "Cuenta",
            "Inicio de sesión",
            "Último uso",
            "Dirección IP",
            "Navegador",
        ]
        assert ana.email in page

    def test_the_page_of_a_session_is_labelled_in_spanish(self, spanish_staff, ana, password):
        from allauth.usersessions.models import UserSession

        _signed_in_browser(ana.email, password)
        session = UserSession.objects.get(user=ana)

        page = spanish_staff.get(f"/admin/usersessions/usersession/{session.pk}/change/").text
        labels = [unescape(label).strip() for label in re.findall(r"<label>([^<]+):</label>", page)]

        assert labels == [
            "Cuenta",
            "Inicio de sesión",
            "Último uso",
            "Dirección IP",
            "Navegador",
            "Clave de sesión",
            "Datos de la sesión",
        ]
        assert ana.email in page

    def test_the_names_are_not_a_change_of_allauths_models(self):
        """Only the live names change (``_meta``): ``makemigrations`` sees nothing to write in allauth's package."""
        call_command("makemigrations", "usersessions", "--check", "--dry-run", stdout=StringIO())


@pytest.fixture
def ended():
    """The accounts whose businesses were asked to end their sessions (``signals.sessions_ended``)."""
    from accounts import signals

    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(user_id)

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-admin-close-sessions")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-admin-close-sessions")


class TestCloseSessions:
    """ACCOUNTS-F19 (old ``revoke_user_sessions`` and the «revoke» of the sessions' admin, ERPlora/saas
    ``test_revoke_user_sessions.py``; PLAN-SAAS: «SE PORTA como acción del admin, «Cerrar sesiones»»): for an incident,
    a superuser ends every session of an account (here and in its businesses) and the trust of its browsers, or only
    the sessions they pick. Through the operation, so the owner's live list of sessions refreshes. Support only looks."""

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_its_actions_are_named_as_briefly_as_djangos_own(self, language):
        """The «Action» select is as wide as its longest option: a label longer than Django's own «Delete selected
        users» pushed the changelist past the screen at 834 px (seen in the e2e of ACCOUNTS-G09)."""
        from django.contrib import admin
        from django.contrib.admin.actions import delete_selected
        from django.contrib.auth import get_user_model
        from django.utils import translation
        from allauth.usersessions.models import UserSession

        with translation.override(language):
            for model in (get_user_model(), UserSession):
                model_admin = admin.site._registry[model]
                djangos = str(delete_selected.short_description) % {
                    "verbose_name_plural": model._meta.verbose_name_plural
                }
                label = str(model_admin.close_sessions.short_description)
                assert len(label) <= len(djangos) + 4, (model.__name__, label, djangos)

    def test_closing_an_accounts_sessions_ends_them_all_here_and_in_its_businesses(
        self, staff_client, ana, password, ended
    ):
        from allauth.usersessions.models import UserSession

        client, _ = staff_client
        laptop = _signed_in_browser(ana.email, password)
        phone = _signed_in_browser(ana.email, password)

        response = client.post(
            "/admin/accounts/user/", {"action": "close_sessions", "_selected_action": [str(ana.pk)]}, follow=True
        )

        assert response.status_code == 200
        assert "Sessions closed: 2." in response.text
        assert not UserSession.objects.filter(user=ana).exists()
        assert laptop.get("/api/me").json()["user"] is None
        assert phone.get("/api/me").json()["user"] is None
        assert ended == [ana.pk]

    def test_it_ends_the_trust_of_its_browsers_and_keeps_its_app(self, staff_client, ana):
        from allauth.mfa.models import Authenticator
        from allauth.mfa.totp.internal import auth as totp_auth

        totp_auth.TOTP.activate(ana, totp_auth.generate_totp_secret())
        before = set(Authenticator.objects.filter(user=ana).values_list("pk", flat=True))
        client, _ = staff_client

        client.post("/admin/accounts/user/", {"action": "close_sessions", "_selected_action": [str(ana.pk)]})

        after = Authenticator.objects.filter(user=ana)
        assert [row.type for row in after] == ["totp"]
        assert before.isdisjoint(row.pk for row in after)

    def test_the_other_accounts_keep_theirs(self, staff_client, ana, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _signed_in_browser(ana.email, password)
        theirs = _signed_in_browser(bo.email, password)
        client, _ = staff_client

        client.post("/admin/accounts/user/", {"action": "close_sessions", "_selected_action": [str(ana.pk)]})

        assert theirs.get("/api/me").json()["user"] is not None

    def test_closing_refreshes_the_owners_live_list_of_sessions(self, staff_client, ana, password):
        from live.models import OutboxEvent

        from accounts import events

        client, _ = staff_client
        _signed_in_browser(ana.email, password)

        client.post("/admin/accounts/user/", {"action": "close_sessions", "_selected_action": [str(ana.pk)]})

        assert list(OutboxEvent.objects.values_list("name", "scope_key")) == [(events.SESSION_CLOSED, str(ana.pk))]

    def test_on_the_sessions_page_only_the_picked_ones_end(self, staff_client, ana, password, ended):
        from allauth.usersessions.models import UserSession

        client, _ = staff_client
        laptop = _signed_in_browser(ana.email, password)
        phone = _signed_in_browser(ana.email, password)
        picked = UserSession.objects.get(session_key=phone.session.session_key)

        response = client.post(
            "/admin/usersessions/usersession/",
            {"action": "close_sessions", "_selected_action": [str(picked.pk)]},
            follow=True,
        )

        assert "Sessions closed: 1." in response.text
        assert phone.get("/api/me").json()["user"] is None
        assert laptop.get("/api/me").json()["user"] is not None
        assert ended == [ana.pk]

    def test_the_sessions_page_only_shows_them(self, staff_client, ana, password):
        from allauth.usersessions.models import UserSession

        client, _ = staff_client
        _signed_in_browser(ana.email, password)
        session = UserSession.objects.get(user=ana)

        assert client.get("/admin/usersessions/usersession/add/").status_code == 403
        assert client.get(f"/admin/usersessions/usersession/{session.pk}/delete/").status_code == 403
        page = client.get(f"/admin/usersessions/usersession/{session.pk}/change/")
        assert page.status_code == 200
        assert 'name="ip"' not in page.text

    def test_support_sees_the_sessions_and_cannot_close_them(self, client, ana, password):
        from allauth.usersessions.models import UserSession

        supporter, _ = services.create_platform_user("support@example.com", services.PLATFORM_SUPPORT, "x")
        client.force_login(supporter)
        _signed_in_browser(ana.email, password)

        client.post("/admin/accounts/user/", {"action": "close_sessions", "_selected_action": [str(ana.pk)]})

        assert UserSession.objects.filter(user=ana).exists()
        assert "close_sessions" not in client.get("/admin/accounts/user/").text

    def test_the_action_is_said_in_spanish(self, staff_client, ana, password):
        client, _ = staff_client
        _signed_in_browser(ana.email, password)

        listing = client.get("/admin/accounts/user/", headers={"Accept-Language": "es"})
        response = client.post(
            "/admin/accounts/user/",
            {"action": "close_sessions", "_selected_action": [str(ana.pk)]},
            headers={"Accept-Language": "es"},
            follow=True,
        )

        assert '<option value="close_sessions">Cerrar todas sus sesiones</option>' in listing.text
        assert "Sesiones cerradas: 1." in response.text

    def test_the_operation_runs_only_on_the_accounts_own_channel(self, ana):
        from live.context import Scope, system_context
        from live.errors import LiveMisuse

        from accounts.schemas import SessionCloseAnyIn

        with pytest.raises(LiveMisuse):
            services.session_close_any(system_context(Scope("user", "someone-else")), SessionCloseAnyIn(user_id=ana.pk))

    def test_an_account_that_is_gone_is_not_found(self):
        from uuid import uuid7

        from live.context import Scope, system_context
        from live.errors import NotFound

        from accounts.schemas import SessionCloseAnyIn

        gone = uuid7()
        with pytest.raises(NotFound):
            services.session_close_any(system_context(Scope("user", str(gone))), SessionCloseAnyIn(user_id=gone))

    def test_no_role_may_close_any_accounts_sessions(self):
        from live.meta import all_live_app_configs, permissions_for_role

        from base.operations import ACCOUNT_ROLE

        assert services.CLOSE_ANY_SESSIONS not in permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)
