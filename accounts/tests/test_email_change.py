"""Account → Profile → «Change» the email: ``accounts.email.change`` and ``accounts.email.verify`` (plan
2026-10-13, L3-A).

Ported from ERPlora/saas ``apps/dashboard/profile/tests/test_change_email.py`` (24; saas#2536,
SAAS_DASHBOARD-F204). Two locks, as Google, GitHub, Shopify and Stripe do it:

1. a recent sign-in (allauth's reauthentication: the password typed again, not just an open session);
2. the new address only counts once the code mailed to it is typed, in the same session: until then the account
   keeps its address, so «Forgot your password?» cannot be pointed at an address nobody proved, and a code that
   reached the wrong mailbox (a typo) is of no use anywhere else. The tries are counted in the database (three
   per code, consumed atomically) and per account (a budget a minute and an hour), never in the session, which a
   racing request could save back older. The old SaaS used allauth's verification by code for the change too;
   here allauth's mandatory verification by code (``ACCOUNT_EMAIL_VERIFICATION = "mandatory"``) proves the
   address of a sign-up, while allauth's own email API is closed (``accounts.doors.closed``, 404) and the change's
   code is accounts' own (``services.email_change``), with the locks above.

Dropped, with their reason: the template pages and their htmx (the SPA's) and the account surface's mark on
the way (``base.surface`` keeps it in the session). «Use a different email» lives on the sign-up's code page
(``VerifyEmailPage.vue``), not here. The second way around of ``TestAllauthSetPasswordPage…`` is closed: an
account without a password does not set one with the session alone, allauth.headless's
``account/password/change`` answers it 403 (``accounts.doors.password_change``, ``test_doors``).
"""

import re

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import Client

from accounts.tests.conftest import BROWSER, HOST, REAUTHENTICATE, api_get, api_post, sign_in

pytestmark = pytest.mark.django_db

CHANGE = "/api/accounts/email/change"
VERIFY = "/api/accounts/email/verify"
PROFILE = "/api/accounts/profile"
NEW = "ana.garcia@new.example"


def _code_in(message) -> str:
    match = re.search(r"^(\d{6})$", message.body, re.MULTILINE)
    assert match, message.body
    return match.group(1)


def _verify(client, code):
    return api_post(client, VERIFY, {"code": code})


class TestARecentSignInIsNeeded:
    def test_an_old_sign_in_is_asked_for_the_password_and_nothing_is_sent(self, signed_in_long_ago, ana):
        response = api_post(signed_in_long_ago, CHANGE, {"email": NEW})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "reauthentication_required"
        assert mail.outbox == []

    def test_the_password_lets_it_through(self, signed_in_long_ago, password):
        signed_in_long_ago.post(REAUTHENTICATE, {"password": password}, content_type="application/json", HTTP_HOST=HOST)

        assert api_post(signed_in_long_ago, CHANGE, {"email": NEW}).status_code == 200

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_post(client, CHANGE, {"email": NEW}).json()["error"]["code"] == "unauthorized"

    def test_an_account_without_a_password_sets_one_first(self, client, ana):
        """Without a password there is nothing to confirm with (allauth lets it through), so the session alone
        would change the address: it is refused, and «Forgot your password?» gives the account one."""
        ana.set_unusable_password()
        ana.save()
        client.force_login(ana)

        response = api_post(client, CHANGE, {"email": NEW})

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.password_required")
        assert mail.outbox == []

    def test_changes_are_rate_limited_per_account(self, signed_in):
        """allauth's budget for an account's addresses (``manage_email``, 10 a minute): the same one its own
        email page spends."""
        for index in range(10):
            assert api_post(signed_in, CHANGE, {"email": f"ana{index}@new.example"}).status_code == 200

        response = api_post(signed_in, CHANGE, {"email": "ana10@new.example"})

        assert (response.status_code, response.json()["error"]["code"]) == (429, "accounts.too_many_attempts")


class TestTheNewAddressCountsOnlyOnceProven:
    def test_a_code_goes_to_the_new_address_and_the_account_keeps_the_old_one(self, signed_in, ana):
        response = api_post(signed_in, CHANGE, {"email": "  Ana.Garcia@NEW.example "})

        assert response.status_code == 200
        assert (response.json()["email"], response.json()["pending_email"]) == ("ana@example.com", NEW)
        [message] = mail.outbox
        assert message.to == [NEW]
        assert _code_in(message)
        ana.refresh_from_db()
        assert ana.email == "ana@example.com"
        assert not EmailAddress.objects.filter(email__iexact=NEW).exists()

    def test_the_profile_shows_the_address_waiting_for_its_code(self, signed_in):
        api_post(signed_in, CHANGE, {"email": NEW})

        assert api_get(signed_in, PROFILE).json()["pending_email"] == NEW

    def test_forgot_your_password_for_the_unproven_address_reaches_nobody(self, signed_in, client):
        api_post(signed_in, CHANGE, {"email": NEW})
        mail.outbox.clear()

        client.post(
            "/_allauth/browser/v1/auth/password/request", {"email": NEW}, content_type="application/json", HTTP_HOST=HOST
        )

        assert not [message for message in mail.outbox if "/password/reset/key/" in message.body]

    def test_typing_the_code_switches_the_account_to_the_new_address(self, signed_in, ana):
        api_post(signed_in, CHANGE, {"email": NEW})

        response = _verify(signed_in, _code_in(mail.outbox[0]))

        assert (response.status_code, response.json()["verified"]) == (200, True)
        profile = response.json()["profile"]
        assert (profile["email"], profile["pending_email"], profile["email_verified"]) == (NEW, None, True)
        ana.refresh_from_db()
        assert ana.email == NEW
        assert list(EmailAddress.objects.filter(user=ana).values_list("email", "verified", "primary")) == [
            (NEW, True, True)
        ]

    def test_the_old_address_is_told_once_it_is_done(self, signed_in, ana, django_capture_on_commit_callbacks):
        api_post(signed_in, CHANGE, {"email": NEW})
        with django_capture_on_commit_callbacks(execute=True):
            _verify(signed_in, _code_in(mail.outbox[0]))

        notice = mail.outbox[-1]
        assert notice.to == ["ana@example.com"]
        assert NEW in notice.body

    def test_allauths_signal_tells_who_keeps_a_copy_of_the_address(self, signed_in, ana):
        from allauth.account.signals import email_changed

        seen = []

        def changed(sender, user, from_email_address, to_email_address, **kwargs):
            seen.append((user.pk, getattr(from_email_address, "email", None), to_email_address.email))

        email_changed.connect(changed, dispatch_uid="test-email-changed")
        try:
            api_post(signed_in, CHANGE, {"email": NEW})
            _verify(signed_in, _code_in(mail.outbox[0]))
        finally:
            email_changed.disconnect(dispatch_uid="test-email-changed")

        assert seen == [(ana.pk, "ana@example.com", NEW)]

    def test_the_old_address_still_signs_in_until_the_code_is_typed(self, signed_in, ana, password):
        api_post(signed_in, CHANGE, {"email": NEW})

        sign_in(Client(), "ana@example.com", password)

    def test_a_wrong_code_says_so_with_the_tries_left_and_three_spend_the_change(self, signed_in, ana):
        """A wrong code is no error of the request: the answer says so, and the try it spent is saved (an error
        would roll it back, and the tries would never run out)."""
        api_post(signed_in, CHANGE, {"email": NEW})

        first, second, third = (_verify(signed_in, "000000") for _ in range(3))

        assert first.status_code == 200
        assert (first.json()["verified"], first.json()["attempts_left"]) == (False, 2)
        assert second.json()["attempts_left"] == 1
        assert (third.json()["verified"], third.json()["attempts_left"]) == (False, 0)
        late = _verify(signed_in, _code_in(mail.outbox[0]))
        assert (late.status_code, late.json()["error"]["code"]) == (409, "accounts.no_email_change")
        ana.refresh_from_db()
        assert ana.email == "ana@example.com"

    def test_the_tries_are_counted_outside_the_session(self, signed_in, ana):
        """A request that saves an older copy of the session (two requests racing) gives no try back."""
        api_post(signed_in, CHANGE, {"email": NEW})
        snapshot = dict(signed_in.session.items())
        _verify(signed_in, "000000")
        _verify(signed_in, "000001")

        session = signed_in.session
        session.update(snapshot)
        session.save()

        assert _verify(signed_in, "000002").json()["attempts_left"] == 0
        assert _verify(signed_in, _code_in(mail.outbox[0])).status_code == 409

    def test_two_tabs_of_the_session_share_the_tries(self, signed_in, ana):
        from django.conf import settings

        api_post(signed_in, CHANGE, {"email": NEW})
        other_tab = Client()
        other_tab.cookies[settings.SESSION_COOKIE_NAME] = signed_in.cookies[settings.SESSION_COOKIE_NAME].value

        answers = [_verify(tab, "000000").json()["attempts_left"] for tab in (signed_in, other_tab, signed_in)]

        assert answers == [2, 1, 0]

    def test_an_account_has_a_budget_of_tries(self, signed_in, ana, monkeypatch):
        from accounts import services

        monkeypatch.setattr(services, "EMAIL_CODE_TRIES_PER_MINUTE", "2/m")
        api_post(signed_in, CHANGE, {"email": NEW})
        _verify(signed_in, "000000")
        _verify(signed_in, "000001")

        response = _verify(signed_in, _code_in(mail.outbox[0]))

        assert (response.status_code, response.json()["error"]["code"]) == (429, "accounts.too_many_attempts")

    def test_one_address_gets_three_codes_an_hour(self, signed_in, ana, monkeypatch):
        """However many accounts or sessions ask: an address is nobody's inbox to flood."""
        import time

        # At the start of an hour: the budget's window (django-ratelimit's) is the clock's hour.
        moment = [time.time() // 3600 * 3600 + 1]
        monkeypatch.setattr(time, "time", lambda: moment[0])
        for _ in range(3):
            assert api_post(signed_in, CHANGE, {"email": NEW}).status_code == 200
            moment[0] += 61

        response = api_post(signed_in, CHANGE, {"email": NEW})

        assert (response.status_code, response.json()["error"]["code"]) == (429, "accounts.too_many_codes")
        assert len(mail.outbox) == 3
        assert api_post(signed_in, CHANGE, {"email": "another@new.example"}).status_code == 200

    def test_asking_records_an_event_so_the_live_profile_shows_the_address(self, signed_in):
        from live.live_registry import live_registry
        from live.models import OutboxEvent

        from accounts import events

        api_post(signed_in, CHANGE, {"email": NEW})

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == [events.EMAIL_CHANGE_REQUESTED]
        assert "accounts.profile.get" in live_registry.affected([events.EMAIL_CHANGE_REQUESTED])

    def test_another_session_does_not_see_the_waiting_address(self, signed_in, ana, password):
        api_post(signed_in, CHANGE, {"email": NEW})
        phone = sign_in(Client(), ana.email, password)

        assert api_get(phone, PROFILE).json()["pending_email"] is None

    def test_two_accounts_proving_the_same_address_at_once_is_a_409(self, signed_in, ana, monkeypatch):
        """The second to finish meets the database's unique address, not a 500."""
        from django.contrib.auth import get_user_model

        from accounts import services

        api_post(signed_in, CHANGE, {"email": NEW})
        get_user_model().objects.create_user(email=NEW, password=None)
        monkeypatch.setattr(services, "email_belongs_to_another_account", lambda user, email: False)

        response = _verify(signed_in, _code_in(mail.outbox[0]))

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.email_taken")
        ana.refresh_from_db()
        assert ana.email == "ana@example.com"

    def test_only_the_session_that_asked_can_type_the_code(self, signed_in, ana, password):
        api_post(signed_in, CHANGE, {"email": NEW})
        phone = sign_in(Client(), ana.email, password)

        response = _verify(phone, _code_in(mail.outbox[0]))

        assert response.json()["error"]["code"] == "accounts.no_email_change"
        ana.refresh_from_db()
        assert ana.email == "ana@example.com"

    def test_a_code_works_for_fifteen_minutes(self, signed_in, ana, monkeypatch):
        import time

        api_post(signed_in, CHANGE, {"email": NEW})
        later = time.time() + 15 * 60 + 1
        monkeypatch.setattr(time, "time", lambda: later)

        assert _verify(signed_in, _code_in(mail.outbox[0])).json()["error"]["code"] == "accounts.no_email_change"

    def test_asking_again_at_once_does_not_send_another_code(self, signed_in, ana):
        """A double click or an impatient second request: the code on its way keeps working."""
        api_post(signed_in, CHANGE, {"email": NEW})
        response = api_post(signed_in, CHANGE, {"email": NEW})

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert _verify(signed_in, _code_in(mail.outbox[0])).json()["verified"] is True

    def test_asking_again_a_minute_later_sends_a_new_code_and_the_old_one_stops(self, signed_in, ana, monkeypatch):
        import time

        api_post(signed_in, CHANGE, {"email": NEW})
        later = time.time() + 61
        monkeypatch.setattr(time, "time", lambda: later)
        api_post(signed_in, CHANGE, {"email": NEW})

        first, second = (_code_in(message) for message in mail.outbox)
        if first != second:
            assert _verify(signed_in, first).json()["verified"] is False
        assert _verify(signed_in, second).json()["verified"] is True

    def test_an_address_taken_meanwhile_is_refused_when_the_code_comes(self, signed_in, ana):
        from django.contrib.auth import get_user_model

        api_post(signed_in, CHANGE, {"email": NEW})
        get_user_model().objects.create_user(email=NEW, password=None)

        response = _verify(signed_in, _code_in(mail.outbox[0]))

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.email_taken")
        ana.refresh_from_db()
        assert ana.email == "ana@example.com"

    def test_verifying_without_asking_first(self, signed_in):
        response = _verify(signed_in, "123456")

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.no_email_change")


def _unprove(user) -> None:
    """The signed-in account's address is on record but never proven: a session opened before every account
    had to prove it (``ACCOUNT_EMAIL_VERIFICATION``), or a staff member's through Django's admin login."""
    EmailAddress.objects.filter(user=user).update(verified=False)


class TestProvingTheCurrentAddress:
    """An address the account never proved (``email_verified`` false) is proven the same way: the code goes to
    it. hubs needs it to accept an invitation (403 ``hubs.email_unverified``)."""

    def test_its_own_unproven_address_gets_a_code_and_is_proven(self, signed_in, ana):
        _unprove(ana)

        response = api_post(signed_in, CHANGE, {"email": "ana@example.com"})

        assert (response.status_code, response.json()["pending_email"]) == (200, "ana@example.com")
        [message] = mail.outbox
        assert message.to == ["ana@example.com"]
        assert _verify(signed_in, _code_in(message)).json()["profile"]["email_verified"] is True
        assert list(EmailAddress.objects.filter(user=ana).values_list("email", "verified", "primary")) == [
            ("ana@example.com", True, True)
        ]
        assert len(mail.outbox) == 1  # no «your email changed» notice: it did not change

    def test_proving_its_own_address_needs_no_recent_sign_in(self, signed_in_long_ago, ana):
        """A code to the account's own address hands nothing over: no password is asked for it."""
        _unprove(ana)

        response = api_post(signed_in_long_ago, CHANGE, {"email": "ana@example.com"})

        assert response.status_code == 200
        assert mail.outbox[0].to == ["ana@example.com"]


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        "email, message",
        [
            ("not-an-email", "Enter a valid email address."),
            ("ANA@example.com", "That is already your email."),
            (f"{'a' * 250}@new.example", "Enter a valid email address."),
        ],
    )
    def test_a_422_on_the_email_and_nothing_is_sent(self, english, signed_in, email, message):
        response = api_post(signed_in, CHANGE, {"email": email})

        assert response.status_code == 422
        assert response.json()["error"]["fields"] == {"email": message}
        assert mail.outbox == []

    @pytest.mark.parametrize("taken", ["bo@example.com", "BO@example.com"])
    def test_the_address_of_another_account_is_refused_in_any_letter_case(self, english, signed_in, taken):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(email="bo@example.com", password=None)

        response = api_post(signed_in, CHANGE, {"email": taken})

        assert response.json()["error"]["fields"] == {"email": "This email is already used by another account."}
        assert mail.outbox == []

    def test_the_address_on_record_of_another_account_is_refused_too(self, signed_in):
        from django.contrib.auth import get_user_model

        bo = get_user_model().objects.create_user(email="bo@example.com", password=None)
        EmailAddress.objects.create(user=bo, email="Bo.Old@Example.com", verified=True, primary=False)

        response = api_post(signed_in, CHANGE, {"email": "bo.old@example.com"})

        assert response.status_code == 422

    def test_the_refusals_speak_spanish(self, signed_in):
        response = signed_in.post(
            CHANGE,
            {"email": "ANA@example.com"},
            content_type="application/json",
            HTTP_HOST=HOST,
            HTTP_ACCEPT_LANGUAGE="es",
        )

        assert response.json()["error"]["fields"] == {"email": "Ese ya es tu correo."}


class TestAllauthsEmailPageIsNotASecondDoor:
    """Closed outright (``accounts.doors``), not only behind a recent sign-in: ``test_doors`` checks every method."""

    def test_adding_an_address_there_is_refused_even_after_an_old_sign_in(self, signed_in_long_ago):
        response = signed_in_long_ago.post(
            f"{BROWSER}/account/email", {"email": NEW}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 404
        assert mail.outbox == []
