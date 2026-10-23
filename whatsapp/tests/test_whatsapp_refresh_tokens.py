"""WHATSAPP-G12 · Renew Meta's permission before it expires and tell the owner when it cannot be
(``manage.py whatsapp_refresh_tokens``, once a day; ``gateway.renew_tokens``).

Cases of the old product's ``test_token_refresh.py``: inside the last 14 days the token is exchanged for a fresh one
and its new deadline stored; Meta refusing marks the number «needs reconnecting» and mails the owner once per
incident; no answer from Meta is no verdict, unless 3 days or less remain; a number still not renewed inside the last
week is an error in the log. Its two ``parcial`` are fixed: the mail goes in the owner's language, and the number of
a business that left is not renewed any more. Meta is replaced at the HTTP border only (``respx``).
"""

from datetime import timedelta
from io import StringIO

import httpx
import pytest
import respx
from django.core import mail
from django.core.management import CommandError, call_command
from django.utils import timezone

from hubs.models import Hub
from whatsapp import gateway, meta
from whatsapp.models import PhoneNumber
from whatsapp.tests.conftest import GRAPH

EXCHANGE = f"{GRAPH}/oauth/access_token"
DEBUG = f"{GRAPH}/debug_token"
LATER = 1_900_000_000


def make_number(hub, *, days=10, **fields):
    expires = None if days is None else timezone.now() + timedelta(days=days)
    values = {"phone_number_id": f"pn-{hub.slug}", "display_phone": "+34 910 00 00 00", "waba_id": "W",
              "access_token": "EAAG-old", "token_expires_at": expires, **fields}
    return PhoneNumber.objects.create(hub=hub, **values)


def meta_renews(token="EAAG-new"):
    exchange = respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"access_token": token}))
    respx.get(DEBUG).mock(return_value=httpx.Response(200, json={"data": {"is_valid": True, "expires_at": LATER}}))
    return exchange


def meta_refuses():
    error = {"error": {"message": "Error validating access token", "type": "OAuthException", "code": 190}}
    return respx.get(EXCHANGE).mock(return_value=httpx.Response(400, json=error))


@pytest.mark.django_db
class TestRenewing:
    @respx.mock
    def test_a_token_inside_the_window_is_exchanged_and_stored(self, whatsapp_on, business):
        number = make_number(business, days=10)
        exchange = meta_renews()

        counts = gateway.renew_tokens()

        number.refresh_from_db()
        assert counts["renewed"] == 1
        assert exchange.calls.last.request.url.params["fb_exchange_token"] == "EAAG-old"
        assert number.access_token == "EAAG-new"
        assert int(number.token_expires_at.timestamp()) == LATER

    @pytest.mark.parametrize("days", [30, None])
    @respx.mock
    def test_a_token_far_from_its_deadline_or_that_never_expires_is_left_alone(self, whatsapp_on, business, days):
        make_number(business, days=days)
        exchange = meta_renews()

        gateway.renew_tokens()

        assert not exchange.called

    @respx.mock
    def test_a_disconnected_number_is_left_alone(self, whatsapp_on, business):
        make_number(business, is_active=False)
        exchange = meta_renews()

        gateway.renew_tokens()

        assert not exchange.called

    @respx.mock
    def test_the_number_of_a_business_that_left_is_not_renewed(self, whatsapp_on, business):
        make_number(business)
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)
        exchange = meta_renews()

        gateway.renew_tokens()

        assert not exchange.called

    @respx.mock
    def test_a_renewal_clears_the_mark_so_the_next_incident_speaks(self, whatsapp_on, business):
        number = make_number(business, needs_reconnect=True, reconnect_alerted_at=timezone.now())
        meta_renews()
        before = Hub.objects.get(pk=business.pk).state_version

        gateway.renew_tokens()

        number.refresh_from_db()
        assert (number.needs_reconnect, number.reconnect_alerted_at) == (False, None)
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_renewing_one_business_never_touches_anothers_token(self, whatsapp_on, business, other_business):
        make_number(business, days=10)
        other = make_number(other_business, days=40, access_token="EAAG-other")
        meta_renews()

        gateway.renew_tokens()

        other.refresh_from_db()
        assert other.access_token == "EAAG-other"


@pytest.mark.django_db
class TestWhenMetaSaysNo:
    @respx.mock
    def test_a_refusal_marks_the_number_and_tells_the_owner(self, whatsapp_on, business, owner):
        number = make_number(business)
        meta_refuses()
        before = Hub.objects.get(pk=business.pk).state_version

        counts = gateway.renew_tokens()

        number.refresh_from_db()
        assert counts["needs_reconnect"] == 1
        assert number.needs_reconnect is True and number.reconnect_alerted_at is not None
        assert [message.to for message in mail.outbox] == [[owner.email]]
        assert "+34 910 00 00 00" in mail.outbox[0].subject
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_the_owner_is_told_once_per_incident(self, whatsapp_on, business):
        make_number(business)
        meta_refuses()

        gateway.renew_tokens()
        gateway.renew_tokens()

        assert len(mail.outbox) == 1

    @respx.mock
    def test_a_mail_that_did_not_leave_is_tried_again_next_time(self, whatsapp_on, business, monkeypatch):
        number = make_number(business)
        meta_refuses()
        monkeypatch.setattr("django.core.mail.EmailMessage.send", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))

        gateway.renew_tokens()

        number.refresh_from_db()
        assert number.needs_reconnect is True and number.reconnect_alerted_at is None

    @respx.mock
    def test_the_mail_goes_in_the_owners_language(self, whatsapp_on, business, owner):
        owner.language = "es"
        owner.save(update_fields=["language"])
        make_number(business)
        meta_refuses()

        gateway.renew_tokens()

        assert mail.outbox[0].subject.startswith("Hay que actuar")


@pytest.mark.django_db
class TestWhenMetaDoesNotAnswer:
    @pytest.mark.parametrize(
        "answer",
        [httpx.ConnectError("down"), httpx.Response(500), httpx.Response(429, json={"error": {"code": 4}}),
         httpx.Response(200, json={})],
    )
    @respx.mock
    def test_no_verdict_is_not_a_dead_token(self, whatsapp_on, business, answer):
        number = make_number(business, days=10)
        route = respx.get(EXCHANGE)
        route.mock(side_effect=answer) if isinstance(answer, Exception) else route.mock(return_value=answer)

        counts = gateway.renew_tokens()

        number.refresh_from_db()
        assert counts["unverified"] == 1
        assert number.needs_reconnect is False and number.access_token == "EAAG-old"
        assert mail.outbox == []

    @pytest.mark.parametrize("days", [2, -1])
    @respx.mock
    def test_but_once_the_runway_is_gone_the_owner_is_told_anyway(self, whatsapp_on, business, days):
        number = make_number(business, days=days)
        respx.get(EXCHANGE).mock(side_effect=httpx.ConnectError("down"))

        gateway.renew_tokens()

        number.refresh_from_db()
        assert number.needs_reconnect is True
        assert len(mail.outbox) == 1

    @respx.mock
    def test_a_token_renewed_without_its_deadline_keeps_metas_expires_in(self, whatsapp_on, business):
        number = make_number(business)
        respx.get(EXCHANGE).mock(return_value=httpx.Response(200, json={"access_token": "EAAG-new", "expires_in": 5184000}))
        respx.get(DEBUG).mock(return_value=httpx.Response(500))

        gateway.renew_tokens()

        number.refresh_from_db()
        assert number.access_token == "EAAG-new"
        assert number.token_expires_at > timezone.now() + timedelta(days=59)

    @respx.mock
    def test_a_number_still_not_renewed_inside_the_last_week_is_an_error_in_the_log(self, whatsapp_on, business, caplog):
        make_number(business, days=5)
        respx.get(EXCHANGE).mock(side_effect=httpx.ConnectError("down"))

        gateway.renew_tokens()

        assert "whatsapp.token.running_out" in caplog.text
        assert "EAAG" not in caplog.text

    @respx.mock
    def test_a_clean_round_stays_quiet(self, whatsapp_on, business, caplog):
        make_number(business, days=5)
        meta_renews()

        gateway.renew_tokens()

        assert "running_out" not in caplog.text

    @respx.mock
    def test_a_surprise_on_one_number_does_not_stop_the_others(self, whatsapp_on, business, other_business, monkeypatch):
        first = make_number(business)
        second = make_number(other_business, access_token="EAAG-second")
        meta_renews()
        real = gateway._renew

        def renew(token):
            if token == "EAAG-old":
                raise RuntimeError("surprise")
            return real(token)

        monkeypatch.setattr(gateway, "_renew", renew)

        counts = gateway.renew_tokens()

        first.refresh_from_db(), second.refresh_from_db()
        assert (first.access_token, second.access_token) == ("EAAG-old", "EAAG-new")
        assert (counts["failed"], counts["renewed"]) == (1, 1)


#: What leaves a number out of today's round: none at all, one far from its deadline, one disconnected.
NOTHING_DUE = [None, {"days": 30}, {"is_active": False}]


def without_metas_app(settings):
    settings.WHATSAPP_APP_ID = ""
    settings.WHATSAPP_APP_SECRET = ""


@pytest.mark.django_db
class TestWithoutMetasApp:
    """Until Meta's app is loaded nobody can connect a number: an empty round is not an incident for the team."""

    @pytest.mark.parametrize("number", NOTHING_DUE)
    @respx.mock
    def test_a_round_with_nothing_due_needs_no_credentials(self, whatsapp_on, business, number):
        without_metas_app(whatsapp_on)
        if number is not None:
            make_number(business, **number)
        exchange = meta_renews()

        counts = gateway.renew_tokens()

        assert counts["due"] == 0 and sum(counts.values()) == 0
        assert not exchange.called

    @respx.mock
    def test_a_number_due_is_still_refused_before_meta_is_asked(self, whatsapp_on, business):
        without_metas_app(whatsapp_on)
        number = make_number(business, days=10)
        exchange = meta_renews()

        with pytest.raises(meta.NotConfigured):
            gateway.renew_tokens()

        number.refresh_from_db()
        assert not exchange.called
        assert (number.access_token, number.needs_reconnect) == ("EAAG-old", False)


@pytest.mark.django_db
class TestTheCommand:
    @respx.mock
    def test_it_renews_and_says_how_it_went(self, whatsapp_on, business):
        make_number(business)
        meta_renews()
        out = StringIO()

        call_command("whatsapp_refresh_tokens", stdout=out)

        assert "due=1" in out.getvalue() and "renewed=1" in out.getvalue()

    def test_without_metas_app_it_fails_visibly(self, whatsapp_on, settings, business, caplog):
        settings.WHATSAPP_APP_SECRET = ""
        make_number(business)

        with pytest.raises(CommandError):
            call_command("whatsapp_refresh_tokens", stdout=StringIO())

        assert "whatsapp.token.not_configured" in caplog.text

    @pytest.mark.parametrize("number", NOTHING_DUE)
    def test_without_metas_app_and_nothing_due_it_ends_well_and_says_so(self, whatsapp_on, business, caplog, number):
        without_metas_app(whatsapp_on)
        if number is not None:
            make_number(business, **number)
        out = StringIO()

        call_command("whatsapp_refresh_tokens", stdout=out)

        assert "due=0" in out.getvalue()
        assert "whatsapp.token.not_configured" not in caplog.text
