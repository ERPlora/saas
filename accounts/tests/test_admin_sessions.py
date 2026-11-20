"""The Django admin of the sessions: allauth's page, searched by email and named in the staff's language, and a
superuser closing an account's sessions or the picked ones."""

import re
from html import unescape
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.services import active_sessions, platform_staff

pytestmark = pytest.mark.django_db


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


def _signed_in_browser(email: str, password: str):
    from django.test import Client

    from accounts.tests.conftest import sign_in

    return sign_in(Client(), email, password)


class TestTheSessionsSpeakTheStaffsLanguage:
    """«User sessions» in the staff's language. allauth.usersessions gives its model and its columns
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
    """For an incident, a superuser ends every session of an account (here and in its businesses) and the trust of its
    browsers, or only the sessions they pick. Through the operation, so the owner's live list of sessions refreshes.
    Support only looks."""

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_its_actions_are_named_as_briefly_as_djangos_own(self, language):
        """The «Action» select is as wide as its longest option: a label longer than Django's own «Delete selected
        users» pushed the changelist past the screen at 834 px."""
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

        supporter, _ = platform_staff.create_platform_user("support@example.com", platform_staff.PLATFORM_SUPPORT, "x")
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
            active_sessions.session_close_any(system_context(Scope("user", "someone-else")), SessionCloseAnyIn(user_id=ana.pk))

    def test_an_account_that_is_gone_is_not_found(self):
        from uuid import uuid7

        from live.context import Scope, system_context
        from live.errors import NotFound

        from accounts.schemas import SessionCloseAnyIn

        gone = uuid7()
        with pytest.raises(NotFound):
            active_sessions.session_close_any(system_context(Scope("user", str(gone))), SessionCloseAnyIn(user_id=gone))

    def test_no_role_may_close_any_accounts_sessions(self):
        from live.meta import all_live_app_configs, permissions_for_role

        from base.operations import ACCOUNT_ROLE

        assert active_sessions.CLOSE_ANY_SESSIONS not in permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)
