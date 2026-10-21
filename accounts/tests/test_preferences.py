"""Account → Preferences: ``accounts.preferences.get`` and ``accounts.preferences.update`` (plan 2026-10-13,
L3-A).

Ported from ERPlora/saas ``apps/dashboard/settings/tests``: ``test_api`` (17) and ``test_views`` (33, the
form → the API) for what survives the single panel (the theme mode, the language and the «Business notices»
switch; ACCOUNTS-F22, F23). Dropped, with their reason: the palette (``test_theme_palette``, 18 → only the mode: the SaaS
paints one palette), currency, menu order and developer mode (gone with the panel of round 17); the cached
language (``test_language_cache``, 5: there is no cache, the language is a column of the account row the
session already loads); «unset until chosen» (``test_language_unset_until_chosen``, 9: ``User.language``
always holds one, because the mails and the jump to a hub need one; how the panel applies it is the shell's,
see accounts/README.md); the password change (allauth.headless ``account/password/change``, rate-limited by
allauth itself).
"""

import pytest
from django.utils import translation
from live.live_registry import live_registry

from accounts import events, queries, services
from accounts.models import UserPreferences
from accounts.schemas import PreferencesGetIn, PreferencesUpdateIn
from accounts.tests.conftest import api_get, api_post, ctx_for

pytestmark = pytest.mark.django_db

PREFERENCES = "/api/accounts/preferences"


class TestReading:
    def test_an_account_that_never_chose_gets_the_defaults_and_its_language(self, ana):
        result = queries.preferences_get(ctx_for(ana), PreferencesGetIn())

        assert result.model_dump() == {
            "theme_mode": "system",
            "language": "es",
            "hub_alerts": True,
        }

    def test_reading_writes_nothing(self, ana):
        """A query runs READ ONLY: the row is born with the first change, not by opening the page."""
        queries.preferences_get(ctx_for(ana), PreferencesGetIn())

        assert not UserPreferences.objects.exists()

    def test_what_was_chosen_is_read_back(self, ana):
        UserPreferences.objects.create(user=ana, theme_mode="dark", hub_alerts=False)

        result = queries.preferences_get(ctx_for(ana), PreferencesGetIn())

        assert (result.theme_mode, result.hub_alerts) == ("dark", False)

    def test_an_anonymous_visitor_is_refused(self, db):
        """Without an account there is no role ``account`` and so no ``accounts.view`` (``base.operations``)."""
        from live.errors import PermissionDenied

        with pytest.raises(PermissionDenied):
            queries.preferences_get(ctx_for(None), PreferencesGetIn())


class TestUpdating:
    def test_the_first_change_creates_the_row(self, ana):
        result = services.preferences_update(ctx_for(ana), PreferencesUpdateIn(theme_mode="dark"))

        assert result.theme_mode == "dark"
        assert UserPreferences.objects.get(user=ana).theme_mode == "dark"

    def test_only_what_is_sent_changes(self, ana):
        UserPreferences.objects.create(user=ana, theme_mode="light", hub_alerts=True)

        result = services.preferences_update(ctx_for(ana), PreferencesUpdateIn(hub_alerts=False))

        assert result.model_dump() == {
            "theme_mode": "light",
            "language": "es",
            "hub_alerts": False,
        }

    def test_the_language_is_the_accounts_own(self, ana):
        """``User.language``: the one the mails, the hubs' invitations and the jump to a hub read."""
        services.preferences_update(ctx_for(ana), PreferencesUpdateIn(language="en"))

        ana.refresh_from_db()
        assert ana.language == "en"
        assert not UserPreferences.objects.exists()

    def test_a_change_re_runs_the_live_preferences(self, ana):
        assert "accounts.preferences.get" in live_registry.affected([events.PREFERENCES_UPDATED])

    def test_a_change_is_recorded_as_an_event(self, ana):
        from live.models import OutboxEvent

        services.preferences_update(ctx_for(ana), PreferencesUpdateIn(hub_alerts=False))

        assert list(OutboxEvent.objects.values_list("name", "scope_key")) == [
            (events.PREFERENCES_UPDATED, str(ana.pk))
        ]


class TestOverHttp:
    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_get(client, PREFERENCES).status_code == 401
        assert api_post(client, PREFERENCES, {"theme_mode": "dark"}).status_code == 401

    def test_get_and_update(self, client, ana):
        client.force_login(ana)

        assert api_get(client, PREFERENCES).json()["theme_mode"] == "system"
        response = api_post(client, PREFERENCES, {"theme_mode": "dark", "hub_alerts": False})

        assert response.status_code == 200
        assert response.json() == {
            "theme_mode": "dark",
            "language": "es",
            "hub_alerts": False,
        }

    @pytest.mark.parametrize(
        "body, field",
        [
            ({"theme_mode": "auto"}, "theme_mode"),
            ({"language": "fr"}, "language"),
            ({"hub_alerts": "maybe"}, "hub_alerts"),
            ({"currency": "EUR"}, "currency"),
            # No mail of «ERPlora news» exists: no switch for it (ACCOUNTS-F23).
            ({"marketing_emails": True}, "marketing_emails"),
        ],
    )
    def test_an_unknown_value_is_a_422_on_its_field_and_changes_nothing(self, client, ana, body, field):
        client.force_login(ana)

        response = api_post(client, PREFERENCES, body)

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert not UserPreferences.objects.exists()
        ana.refresh_from_db()
        assert ana.language == "es"

    def test_the_422_speaks_spanish(self, client, ana):
        client.force_login(ana)

        response = client.post(
            PREFERENCES,
            {"theme_mode": "auto"},
            content_type="application/json",
            HTTP_HOST="localhost:8001",
            HTTP_ACCEPT_LANGUAGE="es",
        )

        assert response.json()["error"]["fields"]["theme_mode"] == "Selecciona una opción válida."
        translation.deactivate()
