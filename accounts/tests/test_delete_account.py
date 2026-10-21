"""ACCOUNTS-F27 · Account → Profile → «Delete account»: ``accounts.profile.delete`` (plan 2026-10-13, L3-A).

Ported from ERPlora/saas ``apps/dashboard/profile/tests/test_delete_account_sole_owner.py`` (15) and the
deletion cases of ``test_views.py``:

- While the account owns a business that is not deleted, it cannot go (409 ``accounts.owns_businesses``,
  with the businesses): nobody would be left to run, pay or close it (saas#2567). Checked before the
  password is asked: a refusal never tests one. The businesses come from ``hubs.business.list`` (called by
  its name: accounts never imports hubs) — a business has one owner (PLAN-SAAS §3.6 point 8), so «co-owner»
  cases of the original become «admin of someone else's business».
- Then a recent sign-in (allauth's reauthentication, ``ACCOUNT_REAUTHENTICATION_TIMEOUT``): an open session
  alone does not delete; ``POST /_allauth/browser/v1/auth/reauthenticate`` with the password lets it through.
- Deleting ends every session of the SaaS, asks every business to end its sessions (``signals``) and
  deletes the account with what hangs from it.

Dropped, with their reason: the template pages and the account surface's «deleted» page (the SPA's), the
invoices' anonymisation (the invoices are ``billing``'s, L3-C).
"""

import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from accounts import signals
from accounts.models import ApiKey, ProfilePhoto, UserPreferences
from accounts.tests.conftest import HOST, REAUTHENTICATE, age_sign_in, api_get, api_post, sign_in
from hubs.tests.conftest import add_member, create_business, plans  # noqa: F401 - the plans fixture

pytestmark = pytest.mark.django_db

DELETE = "/api/accounts/profile/delete"
PROFILE = "/api/accounts/profile"


@pytest.fixture
def received():
    """What the signals of accounts carried during the test."""
    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(("sessions_ended", user_id))

    def account_deleting(sender, user_id, **kwargs):
        calls.append(("account_deleting", user_id))

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-sessions-ended")
    signals.account_deleting.connect(account_deleting, dispatch_uid="test-account-deleting")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-sessions-ended")
    signals.account_deleting.disconnect(dispatch_uid="test-account-deleting")


def _exists(user) -> bool:
    return get_user_model().objects.filter(pk=user.pk).exists()


class TestOwnersFirstHandTheirBusinessesOver:
    def test_the_owner_of_a_business_is_refused_with_its_businesses_and_nothing_changes(
        self, signed_in, ana, make_owner, plans  # noqa: F811
    ):
        from hubs.models import HubMember

        business = create_business(ana, name="Panadería López")
        # A second one, handed over to her (one free business per account is created, not owned).
        other = create_business(make_owner, name="Café Central")
        HubMember.objects.filter(hub=other, user=make_owner).update(role=HubMember.Role.ADMIN)
        add_member(other, ana, HubMember.Role.OWNER)

        response = api_post(signed_in, DELETE)

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "accounts.owns_businesses"
        assert sorted(error["businesses"], key=lambda row: row["name"]) == [
            {"id": str(other.pk), "name": "Café Central"},
            {"id": str(business.pk), "name": "Panadería López"},
        ]
        assert _exists(ana)

    def test_refused_before_the_password_is_asked(self, signed_in_long_ago, ana, plans):  # noqa: F811
        """A refusal never tests a password: the 409 comes before the reauthentication."""
        create_business(ana)

        response = api_post(signed_in_long_ago, DELETE)

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.owns_businesses")

    def test_the_refusal_does_not_sign_the_person_out(self, signed_in, ana, plans):  # noqa: F811
        create_business(ana)

        api_post(signed_in, DELETE)

        assert api_get(signed_in, PROFILE).status_code == 200

    def test_the_refusal_speaks_spanish(self, signed_in, ana, plans):  # noqa: F811
        create_business(ana)

        response = signed_in.post(DELETE, {}, content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

        assert response.json()["error"]["message"] == (
            "Eres propietario de negocios: transfiérelos o elimínalos antes de eliminar tu cuenta."
        )

    def test_a_deleted_business_does_not_hold_the_account(self, signed_in, ana, plans):  # noqa: F811
        """A business in its 90 days of recovery is no longer run by anybody: the account may go (and with it
        the chance to recover it)."""
        from hubs.models import Hub

        business = create_business(ana)
        # As hubs.business.delete leaves it (the owner is its payer too: neither holds the account).
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())

        assert api_post(signed_in, DELETE).status_code == 200
        assert not _exists(ana)

    def test_an_admin_of_someone_elses_business_can_go_and_the_business_keeps_its_owner(
        self, signed_in, ana, make_owner, plans  # noqa: F811
    ):
        from hubs.models import HubMember

        business = create_business(make_owner)
        add_member(business, ana, HubMember.Role.ADMIN, invited_by=make_owner)

        assert api_post(signed_in, DELETE).status_code == 200
        assert list(HubMember.objects.filter(hub=business).values_list("user__email", flat=True)) == [
            "olga@example.com"
        ]

    def test_an_account_without_businesses_can_go(self, signed_in, ana):
        assert api_post(signed_in, DELETE).status_code == 200
        assert not _exists(ana)


class TestPayersFirstHandThePaymentOver:
    """After a hand-over the old owner may still pay for the business (its payer stays until the new owner writes
    its own): deleting the account would leave Stripe charging a card nobody can stop. Read from the business's
    row (``is_payer`` of ``hubs.business.list``)."""

    @pytest.fixture
    def handed_over(self, ana, make_owner, plans):  # noqa: F811
        from hubs.models import HubMember

        business = create_business(ana, name="Panadería López")
        HubMember.objects.filter(hub=business, user=ana).update(role=HubMember.Role.ADMIN)
        HubMember.objects.filter(hub=business, user=make_owner).delete()
        add_member(business, make_owner, HubMember.Role.OWNER)
        return business

    def test_the_payer_of_a_business_is_refused_with_it(self, signed_in, ana, handed_over):
        response = api_post(signed_in, DELETE)

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "accounts.pays_businesses"
        assert error["businesses"] == [{"id": str(handed_over.pk), "name": "Panadería López"}]
        assert _exists(ana)

    def test_refused_before_the_password_is_asked(self, signed_in_long_ago, handed_over):
        response = api_post(signed_in_long_ago, DELETE)

        assert response.json()["error"]["code"] == "accounts.pays_businesses"

    def test_in_spanish(self, signed_in, handed_over):
        response = signed_in.post(DELETE, {}, content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

        assert response.json()["error"]["message"] == (
            "Pagas negocios de otras personas: pide a su propietario que ponga sus datos de pago antes de eliminar "
            "tu cuenta."
        )

    def test_a_deleted_business_does_not_hold_its_payer(self, signed_in, ana, handed_over):
        from hubs.models import Hub

        Hub.objects.filter(pk=handed_over.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())

        assert api_post(signed_in, DELETE).status_code == 200


class TestARecentSignInIsNeeded:
    def test_an_old_sign_in_is_asked_for_the_password_and_nothing_changes(self, signed_in_long_ago, ana):
        response = api_post(signed_in_long_ago, DELETE)

        assert response.status_code == 401
        error = response.json()["error"]
        assert (error["code"], error["flows"], error["providers"]) == ("reauthentication_required", ["reauthenticate"], [])
        assert _exists(ana)

    def test_the_password_lets_it_through(self, signed_in_long_ago, ana, password):
        confirmed = signed_in_long_ago.post(
            REAUTHENTICATE, {"password": password}, content_type="application/json", HTTP_HOST=HOST
        )
        assert confirmed.status_code == 200

        assert api_post(signed_in_long_ago, DELETE).status_code == 200
        assert not _exists(ana)

    def test_guessing_the_password_with_an_open_session_is_throttled(self, signed_in_long_ago, ana, password):
        """saas#2664 (old SAAS_DASHBOARD-F208): a session left open is no way to try passwords without end. «Confirm
        it's you» is allauth's reauthentication, 10 tries a minute per account; past them, not even the right one."""
        tries = [
            signed_in_long_ago.post(REAUTHENTICATE, {"password": f"guess-{n}"}, content_type="application/json", HTTP_HOST=HOST)
            for n in range(10)
        ]
        assert {response.status_code for response in tries} == {400}

        right = signed_in_long_ago.post(REAUTHENTICATE, {"password": password}, content_type="application/json", HTTP_HOST=HOST)

        assert right.status_code == 429
        assert api_post(signed_in_long_ago, DELETE).status_code == 401
        assert _exists(ana)

    def test_a_session_opened_without_signing_in_is_not_recent(self, client, ana):
        """``force_login`` (or the admin's login) leaves no record of a sign-in: allauth asks again."""
        client.force_login(ana)

        assert api_post(client, DELETE).json()["error"]["code"] == "reauthentication_required"

    def test_an_account_that_only_signs_in_with_google_signs_in_with_google_again(self, client, ana):
        """allauth lets an account without a password nor a second factor through with nothing to confirm; here it
        signs in with Google again (allauth.headless's provider redirect, ``test_google``), which allauth records,
        and then it goes."""
        from allauth.socialaccount.models import SocialAccount

        from accounts.tests.conftest import AUTHENTICATION_RECORDS

        ana.set_unusable_password()
        ana.save()
        SocialAccount.objects.create(user=ana, provider="google", uid="1")
        client.force_login(ana)

        refused = api_post(client, DELETE)

        assert refused.status_code == 401
        error = refused.json()["error"]
        assert (error["flows"], error["providers"]) == (["provider_redirect"], ["google"])
        assert _exists(ana)

        session = client.session
        session[AUTHENTICATION_RECORDS] = [{"method": "socialaccount", "at": time.time(), "provider": "google", "uid": "1"}]
        session.save()

        assert api_post(client, DELETE).status_code == 200
        assert not _exists(ana)

    def test_a_password_account_with_google_may_confirm_either_way(self, signed_in_long_ago, ana):
        from allauth.socialaccount.models import SocialAccount

        SocialAccount.objects.create(user=ana, provider="google", uid="1")

        error = api_post(signed_in_long_ago, DELETE).json()["error"]

        assert (error["flows"], error["providers"]) == (["reauthenticate", "provider_redirect"], ["google"])


class TestWhatDeletingDoes:
    def test_the_answer_signs_the_person_out(self, signed_in, ana):
        response = api_post(signed_in, DELETE)

        assert response.json() == {"deleted": True}
        assert api_get(signed_in, PROFILE).status_code == 401

    def test_every_other_session_of_the_account_ends(self, signed_in, ana, password):
        phone = sign_in(Client(), ana.email, password)

        api_post(signed_in, DELETE)

        assert api_get(phone, PROFILE).status_code == 401
        assert not [s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(ana.pk)]

    def test_what_hangs_from_the_account_goes_with_it(self, signed_in, ana):
        UserPreferences.objects.create(user=ana, theme_mode="dark")
        ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"x")
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=ana, name="k", prefix=prefix, key_hash=key_hash)

        api_post(signed_in, DELETE)

        assert not (UserPreferences.objects.exists() or ProfilePhoto.objects.exists() or ApiKey.objects.exists())

    def test_the_outbox_keeps_its_id_not_its_address(self, signed_in, ana):
        """GDPR: the events it caused keep who they were by the account's id, never its email (``live`` writes
        ``str(actor)``, the email, as the actor; the account's own deletion is recorded the same way)."""
        from live.models import OutboxEvent

        api_post(signed_in, "/api/accounts/preferences", {"theme_mode": "dark"})
        assert OutboxEvent.objects.filter(actor="ana@example.com").exists()

        api_post(signed_in, DELETE)

        assert set(OutboxEvent.objects.values_list("actor", flat=True)) == {str(ana.pk)}

    def test_erploras_invoices_stay_with_their_recipient_as_issued(self, signed_in, ana, plans):  # noqa: F811
        """ACCOUNTS-F27: the law keeps ERPlora's invoices (PLAN-SAAS §4; GDPR art. 17.3.b), so deleting the account
        deletes the person, not its invoices: each keeps who it was issued to, only its link to the account goes."""
        from billing.models import Invoice
        from billing.tests.test_invoice_queries import issue
        from hubs.models import Hub

        business = create_business(ana, name="Panadería López")
        invoice = issue(business, 7, payer=ana, payer_tax_id="B12345678", payer_email="ana@example.com")
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED, deletion_requested_at=timezone.now())

        assert api_post(signed_in, DELETE).status_code == 200

        kept = Invoice.objects.get(pk=invoice.pk)
        assert (kept.number, kept.payer_tax_id, kept.payer_name, kept.total_cents) == (
            "ERP-2026-00007",
            "B12345678",
            "Panadería López SL",
            3629,
        )
        assert kept.payer_account_id is None
        assert kept.lines.count() == 1

    def test_the_businesses_are_asked_to_end_its_sessions(self, signed_in, ana, received):
        api_post(signed_in, DELETE)

        assert received == [("account_deleting", ana.pk), ("sessions_ended", ana.pk)]

    def test_nothing_is_signalled_when_it_is_refused(self, signed_in_long_ago, ana, received):
        api_post(signed_in_long_ago, DELETE)

        assert received == []

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        response = api_post(client, DELETE)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "unauthorized")


@pytest.fixture
def make_owner(db):
    return get_user_model().objects.create_user(email="olga@example.com", password=None, first_name="Olga")


def test_age_sign_in_moves_the_records_back(signed_in):
    before = signed_in.session["account_authentication_methods"][-1]["at"]

    age_sign_in(signed_in, 100)

    assert signed_in.session["account_authentication_methods"][-1]["at"] == before - 100
