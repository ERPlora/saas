"""The Django admin of the API keys: who has which key, a superuser revokes it or issues one for a team account."""

import re
from html import unescape

import pytest

from accounts.services import api_keys, platform_staff

pytestmark = pytest.mark.django_db


def _key(user, **fields):
    from accounts.models import ApiKey

    _, prefix, key_hash = ApiKey.new_secret()
    return ApiKey.objects.create(user=user, name="Zapier", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"], **fields)


class TestApiKeys:
    """An account issues its keys in the Account page; the admin sees who has which key, its scopes and its last use, a
    superuser can cut one («revoke») and issue one for a team account (``TestTheSuperuserIssuesAKey``). Never the hash,
    never a delete: revoking is the audit trail."""

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
        """The list and the key's page say what a key may open in words, never the raw scope list."""
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

        supporter, _ = platform_staff.create_platform_user("support@example.com", platform_staff.PLATFORM_SUPPORT, "x")
        client.force_login(supporter)
        key = _key(ana)

        assert client.get("/admin/accounts/apikey/").status_code == 200
        client.post("/admin/accounts/apikey/", {"action": "revoke", "_selected_action": [str(key.pk)]})
        assert ApiKey.objects.get(pk=key.pk).revoked_at is None


class TestTheSuperuserIssuesAKey:
    """A superuser issues a key for a TEAM account (a customer's key is only the customer's), and the key is shown
    on the answer once, never kept
    in clear, in the session or in a message. The owner is told by mail and its live list refreshes."""

    ADD = "/admin/accounts/apikey/add/"

    @pytest.fixture
    def teammate(self, password):
        user, _ = platform_staff.create_platform_user("qa@erplora.com", platform_staff.PLATFORM_SUPPORT, password)
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
            api_keys.issue_api_key(ana, name="Monitor", scopes=["hubs.read"], expires_in_days=30, by=root)
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
        supporter, _ = platform_staff.create_platform_user("support@example.com", platform_staff.PLATFORM_SUPPORT, "x")
        client.force_login(supporter)

        assert client.get(self.ADD).status_code == 403
        assert self._issue(client, teammate).status_code == 403
