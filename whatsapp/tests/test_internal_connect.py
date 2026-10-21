"""WHATSAPP-G11, WHATSAPP-G01, WHATSAPP-G02 · Doors 10–12: what the Hub needs to open Meta's window
(``POST /internal/whatsapp/config``), connecting the number the window chose (``…/connect``) and disconnecting it
(``…/disconnect``).

Proposed doors, signed as every ``/internal`` call: the Hub's contract (doors 1–9) has none for connecting, and
PLAN-SAAS (block 12) gives erplora.com no WhatsApp screen, so the Hub opens Meta's window (Embedded Signup) with
door 10 and hands its one-time code to door 11. Meta is replaced at the HTTP border only (``respx``), with bodies of
Meta's documentation. Cases of the old product's ``test_embedded_signup.py``, ``test_coexistence.py`` and
``test_disconnect.py``, plus what its WORKFLOW left ``parcial``: a number the window chose that is not in the account
is refused, never swapped for another; a subscription or a registration Meta refused saves nothing; disconnecting
forgets the permission and unsubscribes the app.
"""

import json
import logging
import re

import httpx
import pytest
import respx

from hubs.models import Hub
from whatsapp.models import PhoneNumber
from whatsapp.tests.conftest import APP_ID, APP_SECRET, CONFIG_ID, GRAPH, VERIFY_TOKEN
from whatsapp.tests.test_internal import SECRET, door, error_code

pytestmark = pytest.mark.django_db

WABA = "102290129340398"
PHONE_ID = "106540352242922"
OTHER_PHONE_ID = "106540352242923"
NUMBERS = {
    "data": [
        {"verified_name": "Bar Manolo", "display_phone_number": "+34 910 00 00 00", "id": PHONE_ID,
         "quality_rating": "GREEN"},
        {"verified_name": "Bar Manolo Terraza", "display_phone_number": "+34 910 00 00 01", "id": OTHER_PHONE_ID,
         "quality_rating": "GREEN"},
    ]
}
CODE = "AQBx-one-time-code"
TOKEN = "EAAG-business-token"
EXPIRES_AT = 1_800_000_000
OAUTH_ERROR = {"error": {"message": "This authorization code has expired.", "type": "OAuthException", "code": 100,
                         "error_subcode": 36007, "fbtrace_id": "A1"}}
PIN_MISMATCH = {"error": {"message": "(#133005) Two step verification PIN Mismatch", "type": "OAuthException",
                          "code": 133005, "error_user_msg": "The PIN does not match the one set for this number.",
                          "fbtrace_id": "A2"}}


@pytest.fixture
def internal(settings, whatsapp_on):
    settings.INTERNAL_SHARED_SECRET = SECRET
    return settings


def config(client, hub="bar-manolo", **kwargs):
    return door(client, "/internal/whatsapp/config", {"hub": hub}, key=None, **kwargs)


def connect(client, **fields):
    payload = {"hub": "bar-manolo", "code": CODE, "event": "FINISH", "waba_id": WABA, "phone_number_id": PHONE_ID,
               "business_id": "5550001", **fields}
    return door(client, "/internal/whatsapp/connect", payload, key=None)


def disconnect(client, hub="bar-manolo"):
    return door(client, "/internal/whatsapp/disconnect", {"hub": hub}, key=None)


def meta_happy(numbers=NUMBERS):
    """Meta answering every step of a connection as its documentation shows."""
    routes = {
        "exchange": respx.get(f"{GRAPH}/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer"})
        ),
        "debug": respx.get(f"{GRAPH}/debug_token").mock(
            return_value=httpx.Response(200, json={"data": {"is_valid": True, "expires_at": EXPIRES_AT}})
        ),
        "numbers": respx.get(f"{GRAPH}/{WABA}/phone_numbers").mock(return_value=httpx.Response(200, json=numbers)),
        "subscribe": respx.post(f"{GRAPH}/{WABA}/subscribed_apps").mock(
            return_value=httpx.Response(200, json={"success": True})
        ),
        "register": respx.post(re.compile(rf"{re.escape(GRAPH)}/\d+/register")).mock(
            return_value=httpx.Response(200, json={"success": True})
        ),
        "sync": respx.post(re.compile(rf"{re.escape(GRAPH)}/\d+/smb_app_data")).mock(
            return_value=httpx.Response(200, json={"messaging_product": "whatsapp", "request_id": "r-1"})
        ),
    }
    return routes


def version(hub) -> int:
    return Hub.objects.get(pk=hub.pk).state_version


class TestDoor10Config:
    def test_what_opens_metas_window_and_nothing_secret(self, client, internal, business):
        response = config(client)

        assert response.status_code == 200
        assert response.json() == {
            "configured": True, "app_id": APP_ID, "config_id": CONFIG_ID, "graph_version": "v25.0"
        }
        assert APP_SECRET not in response.content.decode() and VERIFY_TOKEN not in response.content.decode()

    @pytest.mark.parametrize("missing", ["WHATSAPP_APP_ID", "WHATSAPP_APP_SECRET", "WHATSAPP_CONFIG_ID"])
    def test_without_metas_app_it_says_not_configured_with_empty_ids(self, client, internal, business, missing):
        setattr(internal, missing, "")

        assert config(client).json() == {"configured": False, "app_id": "", "config_id": "", "graph_version": "v25.0"}

    def test_a_business_the_saas_does_not_know_is_404(self, client, internal, business):
        response = config(client, hub="nobody")

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")

    def test_an_unsigned_call_is_refused(self, client, internal, business):
        response = config(client, secret="another-secret")

        assert (response.status_code, error_code(response)) == (401, "unauthorized")


class TestDoor11Connect:
    @respx.mock
    def test_a_new_number_is_subscribed_registered_and_kept_with_its_permission_encrypted(
        self, client, internal, business
    ):
        meta = meta_happy()
        before = version(business)

        response = connect(client)

        assert response.status_code == 200
        assert response.json() == {
            "connected": True, "phone_number": "+34910000000", "display_name": "Bar Manolo", "history_requested": False
        }
        exchange = meta["exchange"].calls.last.request.url.params
        assert (exchange["code"], exchange["client_id"], exchange["client_secret"]) == (CODE, APP_ID, APP_SECRET)
        assert meta["subscribe"].calls.last.request.headers["Authorization"] == f"Bearer {TOKEN}"
        register = meta["register"].calls.last.request
        assert str(register.url) == f"{GRAPH}/{PHONE_ID}/register"
        pin = json.loads(register.content)["pin"]
        assert json.loads(register.content)["messaging_product"] == "whatsapp" and re.fullmatch(r"\d{6}", pin)
        assert not meta["sync"].called
        number = PhoneNumber.objects.get()
        assert (number.hub, number.phone_number_id, number.waba_id, number.business_id) == (
            business, PHONE_ID, WABA, "5550001"
        )
        assert (number.access_token, number.registration_pin, number.is_on_biz_app) == (TOKEN, pin, False)
        assert number.token_expires_at.timestamp() == EXPIRES_AT
        assert (number.display_phone, number.display_name, number.is_active) == ("+34 910 00 00 00", "Bar Manolo", True)
        assert TOKEN not in response.content.decode() and pin not in response.content.decode()
        assert version(business) == before + 1

    @respx.mock
    def test_the_token_and_the_pin_are_encrypted_in_the_column(self, client, internal, business):
        from django.db import connection

        meta_happy()
        connect(client)

        with connection.cursor() as cursor:
            cursor.execute("SELECT access_token, registration_pin FROM whatsapp_phonenumber")
            token, pin = cursor.fetchone()
        assert TOKEN not in token and token.startswith("gAAAA") and pin.startswith("gAAAA")

    @respx.mock
    def test_a_number_from_the_business_app_is_never_registered_and_its_history_is_asked(
        self, client, internal, business
    ):
        meta = meta_happy()

        response = connect(client, event="FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING")

        assert response.status_code == 200 and response.json()["history_requested"] is True
        assert not meta["register"].called
        kinds = [json.loads(call.request.content)["sync_type"] for call in meta["sync"].calls]
        assert kinds == ["smb_app_state_sync", "history"]
        number = PhoneNumber.objects.get()
        assert (number.is_on_biz_app, number.registration_pin) == (True, "")

    @respx.mock
    def test_a_history_meta_does_not_take_keeps_the_connection_and_says_so(self, client, internal, business, caplog):
        meta = meta_happy()
        meta["sync"].mock(return_value=httpx.Response(500, json={}))

        response = connect(client, event="FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING")

        assert response.status_code == 200 and response.json()["history_requested"] is False
        assert PhoneNumber.objects.get().is_active
        assert "whatsapp.connect.history_not_requested" in caplog.text

    @respx.mock
    def test_without_a_number_named_the_only_one_of_the_account_is_taken(self, client, internal, business):
        meta_happy({"data": NUMBERS["data"][:1]})

        response = connect(client, phone_number_id="")

        assert response.status_code == 200
        assert PhoneNumber.objects.get().phone_number_id == PHONE_ID

    @respx.mock
    def test_without_a_number_named_and_several_in_the_account_nothing_is_guessed(self, client, internal, business):
        meta = meta_happy()

        response = connect(client, phone_number_id="")

        assert (response.status_code, error_code(response)) == (409, "whatsapp.number_not_chosen")
        assert not meta["subscribe"].called and not PhoneNumber.objects.exists()

    @respx.mock
    def test_a_number_the_account_does_not_have_is_refused_never_swapped(self, client, internal, business):
        meta = meta_happy()

        response = connect(client, phone_number_id="999999999")

        assert (response.status_code, error_code(response)) == (409, "whatsapp.number_not_in_account")
        assert not meta["subscribe"].called and not PhoneNumber.objects.exists()

    @respx.mock
    def test_an_account_without_numbers_is_refused(self, client, internal, business):
        meta_happy({"data": []})

        response = connect(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.number_not_in_account")

    @respx.mock
    def test_a_subscription_meta_refused_saves_nothing(self, client, internal, business):
        meta = meta_happy()
        meta["subscribe"].mock(return_value=httpx.Response(400, json=OAUTH_ERROR))

        response = connect(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_rejected")
        assert not meta["register"].called and not PhoneNumber.objects.exists()

    @respx.mock
    def test_a_registration_meta_refused_saves_nothing_and_says_metas_reason(self, client, internal, business):
        meta = meta_happy()
        meta["register"].mock(return_value=httpx.Response(400, json=PIN_MISMATCH))
        before = version(business)

        response = connect(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_rejected")
        assert "PIN does not match" in response.json()["error"]["message"]
        assert not PhoneNumber.objects.exists() and version(business) == before

    @respx.mock
    def test_an_expired_code_is_metas_refusal(self, client, internal, business):
        meta = meta_happy()
        meta["exchange"].mock(return_value=httpx.Response(400, json=OAUTH_ERROR))

        response = connect(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_rejected")
        assert not meta["numbers"].called

    @respx.mock
    def test_an_exchange_without_a_token_is_a_bad_answer_of_meta(self, client, internal, business):
        meta = meta_happy()
        meta["exchange"].mock(return_value=httpx.Response(200, json={"token_type": "bearer"}))

        response = connect(client)

        assert (response.status_code, error_code(response)) == (502, "whatsapp.meta_no_token")

    @respx.mock
    def test_meta_unreachable_is_503_and_can_be_retried(self, client, internal, business):
        meta = meta_happy()
        meta["numbers"].mock(side_effect=httpx.ConnectError("down"))

        response = connect(client)

        assert (response.status_code, error_code(response)) == (503, "whatsapp.meta_unreachable")
        assert not PhoneNumber.objects.exists()

    @respx.mock
    def test_meta_throttling_is_429(self, client, internal, business):
        meta = meta_happy()
        meta["subscribe"].mock(return_value=httpx.Response(429, json={"error": {"message": "Too many", "code": 4}}))

        response = connect(client)

        assert (response.status_code, error_code(response)) == (429, "whatsapp.meta_rate_limited")

    def test_without_metas_app_nothing_is_called(self, client, internal, business):
        internal.WHATSAPP_APP_SECRET = ""

        with respx.mock(assert_all_called=False) as router:
            response = connect(client)

        assert (response.status_code, error_code(response)) == (503, "whatsapp.not_configured")
        assert not router.calls

    def test_a_business_the_saas_does_not_know_is_404_and_meta_never_called(self, client, internal, business):
        with respx.mock(assert_all_called=False) as router:
            response = connect(client, hub="nobody")

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")
        assert not router.calls

    def test_without_the_code_the_body_is_not_the_contract(self, client, internal, business):
        response = connect(client, code="")

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")

    @respx.mock
    def test_connecting_again_replaces_the_permission_ends_the_incident_and_reuses_the_pin(
        self, client, internal, business
    ):
        from django.utils import timezone

        PhoneNumber.objects.create(
            hub=business, phone_number_id=PHONE_ID, display_phone="+34 910 00 00 00", waba_id=WABA,
            access_token="EAAG-old", registration_pin="246810", needs_reconnect=True,
            reconnect_alerted_at=timezone.now(),
        )
        meta = meta_happy()

        assert connect(client).status_code == 200

        number = PhoneNumber.objects.get()
        assert (number.access_token, number.needs_reconnect, number.reconnect_alerted_at) == (TOKEN, False, None)
        assert json.loads(meta["register"].calls.last.request.content)["pin"] == "246810"

    @respx.mock
    def test_a_number_connected_by_another_business_moves_and_both_hubs_learn_it(
        self, client, internal, business, other_business
    ):
        PhoneNumber.objects.create(
            hub=other_business, phone_number_id=PHONE_ID, display_phone="+34 910 00 00 00", waba_id=WABA,
            access_token="EAAG-theirs",
        )
        meta_happy()
        before = (version(business), version(other_business))

        assert connect(client).status_code == 200

        assert PhoneNumber.objects.get().hub == business
        assert (version(business), version(other_business)) == (before[0] + 1, before[1] + 1)

    @respx.mock
    def test_the_businesss_previous_number_is_disconnected_and_forgets_its_permission(
        self, client, internal, business
    ):
        PhoneNumber.objects.create(
            hub=business, phone_number_id="555", display_phone="+34 600 00 00 00", waba_id="W0", access_token="EAAG-0"
        )
        meta_happy()

        assert connect(client).status_code == 200

        old = PhoneNumber.objects.get(phone_number_id="555")
        assert (old.is_active, old.access_token) == (False, "")
        assert old.disconnected_at is not None
        assert PhoneNumber.objects.get(phone_number_id=PHONE_ID).is_active

    @respx.mock
    def test_the_token_never_reaches_a_log(self, client, internal, business, caplog):
        meta_happy()
        caplog.set_level(logging.DEBUG)

        connect(client)

        assert TOKEN not in caplog.text and CODE not in caplog.text and APP_SECRET not in caplog.text


class TestDoor12Disconnect:
    def number(self, hub, **fields):
        return PhoneNumber.objects.create(
            hub=hub, phone_number_id=fields.pop("phone_number_id", PHONE_ID), display_phone="+34 910 00 00 00",
            waba_id=WABA, access_token="EAAG-token", registration_pin="246810", **fields
        )

    @respx.mock
    def test_the_number_stops_its_permission_is_forgotten_and_the_app_unsubscribed(self, client, internal, business):
        self.number(business)
        unsubscribe = respx.delete(f"{GRAPH}/{WABA}/subscribed_apps").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        before = version(business)

        response = disconnect(client)

        assert (response.status_code, response.json()) == (200, {"disconnected": True})
        assert unsubscribe.calls.last.request.headers["Authorization"] == "Bearer EAAG-token"
        number = PhoneNumber.objects.get()
        assert (number.is_active, number.access_token, number.registration_pin) == (False, "", "246810")
        assert number.disconnected_at is not None
        assert version(business) == before + 1

    def test_without_a_connected_number_nothing_changes(self, client, internal, business):
        with respx.mock(assert_all_called=False) as router:
            response = disconnect(client)

        assert (response.status_code, response.json()) == (200, {"disconnected": False})
        assert not router.calls

    @respx.mock
    def test_meta_not_answering_the_unsubscription_still_disconnects_and_says_so(
        self, client, internal, business, caplog
    ):
        self.number(business)
        respx.delete(f"{GRAPH}/{WABA}/subscribed_apps").mock(side_effect=httpx.ConnectError("down"))

        assert disconnect(client).json() == {"disconnected": True}

        assert not PhoneNumber.objects.get().is_active
        assert "whatsapp.disconnect.unsubscribe_failed" in caplog.text

    def test_an_account_another_active_number_still_uses_stays_subscribed(
        self, client, internal, business, other_business
    ):
        self.number(business)
        self.number(other_business, phone_number_id=OTHER_PHONE_ID)

        with respx.mock(assert_all_called=False) as router:
            assert disconnect(client).json() == {"disconnected": True}

        assert not router.calls
        assert PhoneNumber.objects.get(phone_number_id=OTHER_PHONE_ID).is_active

    def test_a_business_the_saas_does_not_know_is_404(self, client, internal, business):
        response = disconnect(client, hub="nobody")

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")
