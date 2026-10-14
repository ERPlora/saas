"""Account → Profile: ``accounts.profile.get`` and ``accounts.profile.update`` (plan 2026-10-13, L3-A).

Ported from ERPlora/saas ``apps/dashboard/profile/tests``: ``test_api`` (16) and ``test_views`` (27, the
form → the API) for the names and the read of the profile. Dropped, with their reason: the billing address
(``BillingAddress``: the payer's data is ``hubs.BillingProfile``, Billing), ``show_developer_menu``
(the developer part left the panel, PLAN-SAAS §3.6 point 2), the htmx navigation and the template pages
(the panel is the SPA). The photo, the email, the deletion and the password have their own files
(``test_photo``, ``test_email_change``, ``test_delete_account``; the password is allauth.headless's).
"""

import pytest
from allauth.account.models import EmailAddress
from live.errors import PermissionDenied
from live.live_registry import live_registry

from accounts import events, queries, services
from accounts.schemas import ProfileGetIn, ProfileUpdateIn
from accounts.tests.conftest import api_get, api_post, ctx_for

pytestmark = pytest.mark.django_db

PROFILE = "/api/accounts/profile"


class TestReading:
    def test_the_account_as_cuenta_shows_it(self, ana):
        result = queries.profile_get(ctx_for(ana), ProfileGetIn())

        assert result.model_dump() == {
            "id": ana.pk,
            "email": "ana@example.com",
            "email_verified": True,
            "pending_email": None,
            "first_name": "Ana",
            "last_name": "García",
            "full_name": "Ana García",
            "photo": None,
            "has_password": True,
            "date_joined": ana.date_joined,
        }

    def test_an_address_on_record_counts_once_proven(self, ana):
        """The same rule the invitations apply (``queries.email_is_proven``), so the panel can offer to
        verify exactly when a business would refuse the account (the pending list of hubs/README.md)."""
        EmailAddress.objects.create(user=ana, email=ana.email, verified=False, primary=True)
        assert queries.profile_get(ctx_for(ana), ProfileGetIn()).email_verified is False

        EmailAddress.objects.filter(user=ana).update(verified=True)
        assert queries.profile_get(ctx_for(ana), ProfileGetIn()).email_verified is True

    def test_the_pending_email_is_the_change_waiting_in_this_session_only(self, ana):
        """``accounts.email.change`` keeps it in the session that asked (``test_email_change``); an unproven
        address on record (allauth's own pages) is no change of the sign-in email."""
        EmailAddress.objects.create(user=ana, email=ana.email, verified=True, primary=True)
        EmailAddress.objects.create(user=ana, email="ana@new.example", verified=False, primary=False)

        result = queries.profile_get(ctx_for(ana), ProfileGetIn())

        assert (result.email, result.pending_email) == ("ana@example.com", None)

    def test_an_account_without_a_password_says_so(self, ana):
        ana.set_unusable_password()
        ana.save()

        assert queries.profile_get(ctx_for(ana), ProfileGetIn()).has_password is False

    def test_without_names_the_full_name_is_empty(self, ana):
        ana.first_name = ana.last_name = ""
        ana.save()

        assert queries.profile_get(ctx_for(ana), ProfileGetIn()).full_name == ""

    def test_an_anonymous_visitor_is_refused(self, db):
        with pytest.raises(PermissionDenied):
            queries.profile_get(ctx_for(None), ProfileGetIn())


class TestUpdating:
    def test_the_names_change_trimmed(self, ana):
        result = services.profile_update(ctx_for(ana), ProfileUpdateIn(first_name="  Ana María ", last_name=" Ruiz "))

        ana.refresh_from_db()
        assert (ana.first_name, ana.last_name) == ("Ana María", "Ruiz")
        assert (result.first_name, result.full_name) == ("Ana María", "Ana María Ruiz")

    def test_names_can_be_cleared(self, ana):
        services.profile_update(ctx_for(ana), ProfileUpdateIn(first_name="", last_name=""))

        ana.refresh_from_db()
        assert (ana.first_name, ana.last_name) == ("", "")

    def test_a_change_is_recorded_and_re_runs_the_live_profile(self, ana):
        from live.models import OutboxEvent

        services.profile_update(ctx_for(ana), ProfileUpdateIn(first_name="Ana", last_name="G."))

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == [events.PROFILE_UPDATED]
        assert "accounts.profile.get" in live_registry.affected([events.PROFILE_UPDATED])


class TestOverHttp:
    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_get(client, PROFILE).status_code == 401
        assert api_post(client, PROFILE, {"first_name": "X", "last_name": "Y"}).status_code == 401

    def test_get_and_update(self, client, ana):
        client.force_login(ana)

        assert api_get(client, PROFILE).json()["full_name"] == "Ana García"
        response = api_post(client, PROFILE, {"first_name": "Ana", "last_name": "Gil"})

        assert response.status_code == 200
        assert response.json()["full_name"] == "Ana Gil"

    def test_the_email_is_not_changed_here(self, client, ana):
        """saas#2536: the sign-in email has its own door (``accounts.email.change``, with the password and a
        link to the new address); sent here, it is a 422 and nothing changes."""
        client.force_login(ana)

        response = api_post(client, PROFILE, {"first_name": "Ana", "last_name": "Gil", "email": "evil@example.com"})

        assert response.status_code == 422
        assert "email" in response.json()["error"]["fields"]
        ana.refresh_from_db()
        assert (ana.email, ana.last_name) == ("ana@example.com", "García")

    def test_a_name_too_long_is_a_422_on_its_field(self, client, ana):
        client.force_login(ana)

        response = api_post(client, PROFILE, {"first_name": "A" * 151, "last_name": "Gil"})

        assert response.status_code == 422
        assert list(response.json()["error"]["fields"]) == ["first_name"]
