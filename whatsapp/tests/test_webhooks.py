"""WHATSAPP-G13, WHATSAPP-G07 · Meta's webhook at ``/webhooks/whatsapp/``: proving the address is ours, and taking
what Meta reports to the business's Hub.

Cases of the old product's ``test_webhook_fail_closed.py``, ``test_webhook_echo_ingest.py`` and
``test_webhook_coexistence_fields.py``, with the new contract: what arrives is pushed to the Hub's door 1 (or door 2
for a status) right after the COMMIT, and kept and retried while the Hub does not take it (a Hub of ``main`` without
the doors answers 404). Meta is the client here (its signed POST); the Hub is the real-HTTP double.
"""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from whatsapp.models import Delivery, PhoneNumber, Send
from whatsapp.tests.conftest import APP_SECRET, VERIFY_TOKEN
from whatsapp.tests.test_parse import BUSINESS, CUSTOMER, PHONE_NUMBER_ID, WABA, messages, text, webhook

URL = "/webhooks/whatsapp/"
HOST = {"HTTP_HOST": "localhost"}


def signed(client, payload, *, secret=APP_SECRET, raw: bytes | None = None, signature: str | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(URL, data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature, **HOST)


@pytest.fixture
def number(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business,
        phone_number_id=PHONE_NUMBER_ID,
        display_phone="+34 910 00 00 00",
        waba_id=WABA,
        access_token="EAAG-token",
    )


@pytest.fixture
def hub_takes_it(hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"id": "1", "conversation_id": "2", "created": True})
    hub_double.answer("POST", r"^/internal/whatsapp/status$", 200, {"updated": True, "status": "read"})
    return hub_double


class TestProvingTheAddressIsOurs:
    def verify(self, client, **params):
        query = {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1158201444", **params}
        return client.get(URL, query, **HOST)

    def test_the_right_token_gets_the_challenge_back(self, client, whatsapp_on):
        response = self.verify(client)

        assert (response.status_code, response.content) == (200, b"1158201444")
        assert response["Content-Type"].startswith("text/plain")

    def test_another_token_is_refused(self, client, whatsapp_on):
        assert self.verify(client, **{"hub.verify_token": "guess"}).status_code == 403

    def test_another_mode_is_refused(self, client, whatsapp_on):
        assert self.verify(client, **{"hub.mode": "unsubscribe"}).status_code == 403

    def test_without_a_token_configured_it_fails_visibly_and_an_empty_one_never_opens(self, client, whatsapp_on, settings):
        """#971 of the old product: an empty token never matches an empty setting."""
        settings.WHATSAPP_VERIFY_TOKEN = ""

        response = self.verify(client, **{"hub.verify_token": ""})

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "whatsapp.not_configured"


@pytest.mark.django_db
class TestMetasSignature:
    def test_without_the_apps_secret_nothing_is_read(self, client, whatsapp_on, settings, number):
        settings.WHATSAPP_APP_SECRET = ""

        response = signed(client, messages(text()), secret="whatever")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "whatsapp.not_configured"
        assert not Delivery.objects.exists()

    @pytest.mark.parametrize("signature", ["", "sha256=", "sha256=00ff", "md5=abc", "nonsense"])
    def test_an_unsigned_or_badly_signed_post_is_refused(self, client, number, signature):
        response = signed(client, messages(text()), signature=signature)

        assert response.status_code == 403
        assert not Delivery.objects.exists()

    def test_another_secret_is_refused(self, client, number):
        assert signed(client, messages(text()), secret="not-metas").status_code == 403

    def test_a_signed_body_that_is_not_json_is_a_bad_request(self, client, number):
        assert signed(client, None, raw=b"not json").status_code == 400

    def test_a_body_over_the_limit_is_refused_before_it_is_read(self, client, number, settings):
        settings.WHATSAPP_WEBHOOK_MAX_BYTES = 1000

        response = signed(client, None, raw=b"{" + b" " * 2000 + b"}")

        assert response.status_code == 413

    def test_no_throttle_spends_metas_traffic_before_the_signature(self, client, number, hub_takes_it):
        """saas#2571, saas#2531: the old webhook counted 200 POST a minute per address BEFORE the signature, so at a
        busy hour Meta's own notices were refused; anybody could spend that budget with unsigned posts. Here no
        budget exists: a burst of unsigned posts is refused one by one and Meta's next, signed one gets in."""
        for _ in range(250):
            assert signed(client, {}, signature="sha256=00").status_code == 403

        assert signed(client, messages(text())).status_code == 200


@pytest.mark.django_db
class TestACustomersMessageReachesTheHub:
    def test_it_is_pushed_to_door_1_and_marked_taken(self, client, number, hub_takes_it):
        response = signed(client, messages(text(), contacts=[{"profile": {"name": "Ana"}, "wa_id": CUSTOMER}]))

        assert response.status_code == 200
        (call,) = hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")
        assert call.signed_v2
        assert call.body["hub"] == "bar-manolo"
        assert (call.body["wa_message_id"], call.body["from"], call.body["contact_name"]) == ("wamid.A", CUSTOMER, "Ana")
        delivery = Delivery.objects.get()
        assert delivery.delivered_at is not None and delivery.attempts == 0

    def test_an_attachment_goes_with_erploras_own_address(self, client, number, hub_takes_it, settings):
        settings.WHATSAPP_MEDIA_BASE_URL = "https://erplora.com"
        photo = {"from": CUSTOMER, "id": "wamid.P", "timestamp": "1760522400", "type": "image",
                 "image": {"id": "1479537139650973", "mime_type": "image/jpeg", "caption": "Mi pelo"}}

        signed(client, messages(photo))

        (call,) = hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")
        delivery = Delivery.objects.get()
        assert call.body["media"] == {
            "url": f"https://erplora.com/whatsapp/media/{delivery.id}",
            "mime_type": "image/jpeg",
            "filename": "",
            "caption": "Mi pelo",
        }
        assert delivery.media_id == "1479537139650973"

    def test_a_hub_without_the_door_keeps_it_and_retries_later(self, client, number, hub_double):
        """A Hub of ``main`` answers 404 until FIX-HUB-INTERNAL-WHATSAPP-RECEIVERS: Meta still gets its 200, the
        message stays here and the next attempt waits."""
        before = timezone.now()

        assert signed(client, messages(text())).status_code == 200

        delivery = Delivery.objects.get()
        assert (delivery.delivered_at, delivery.attempts) == (None, 1)
        assert "404" in delivery.last_error
        assert before + timedelta(seconds=29) <= delivery.next_attempt_at <= timezone.now() + timedelta(seconds=31)

    def test_metas_retry_is_one_message_pushed_once(self, client, number, hub_takes_it):
        payload = messages(text())

        signed(client, payload)
        signed(client, payload)

        assert Delivery.objects.count() == 1
        assert len(hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")) == 1

    def test_a_number_not_connected_is_dropped_with_a_200(self, client, number, hub_takes_it):
        PhoneNumber.objects.filter(pk=number.pk).update(is_active=False)

        assert signed(client, messages(text())).status_code == 200

        assert not Delivery.objects.exists()
        assert hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound") == []

    def test_a_business_that_left_takes_nothing(self, client, number, business, hub_takes_it):
        """The old product kept parking the messages of a business being deleted until its purge, for nobody."""
        from hubs.models import Hub

        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert signed(client, messages(text())).status_code == 200
        assert not Delivery.objects.exists()

    def test_two_businesses_in_one_notice_each_get_their_own(self, client, number, other_business, hub_takes_it):
        PhoneNumber.objects.create(
            hub=other_business, phone_number_id="2", display_phone="+34 2", waba_id="W2", access_token="t"
        )
        first = messages(text("wamid.1"))
        second = messages(text("wamid.2"))
        second["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "2"
        payload = {"object": "whatsapp_business_account", "entry": first["entry"] + second["entry"]}

        signed(client, payload)

        hubs = {call.body["wa_message_id"]: call.body["hub"] for call in hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")}
        assert hubs == {"wamid.1": "bar-manolo", "wamid.2": "bar-pepe"}

    def test_the_owners_reply_from_the_phone_reaches_the_hub_as_the_business(self, client, number, hub_takes_it):
        echo = {"from": BUSINESS, "to": CUSTOMER, "id": "wamid.E", "timestamp": "1760522400", "type": "text", "text": {"body": "Sí"}}
        payload = webhook(
            "smb_message_echoes",
            {"metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID}, "message_echoes": [echo]},
        )

        signed(client, payload)

        (call,) = hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")
        assert (call.body["direction"], call.body["from"]) == ("outbound", CUSTOMER)

    def test_a_history_photo_completed_later_is_pushed_again_with_its_attachment(self, client, number, hub_takes_it):
        placeholder = {"from": CUSTOMER, "id": "wamid.M", "timestamp": "1739230970", "type": "media_placeholder"}
        chunk = webhook(
            "history",
            {
                "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
                "history": [{"metadata": {}, "threads": [{"id": CUSTOMER, "messages": [placeholder]}]}],
            },
        )
        follow_up = webhook(
            "history",
            {
                "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
                "messages": [{"from": CUSTOMER, "id": "wamid.M", "timestamp": "1739230970", "type": "image",
                              "image": {"id": "555", "mime_type": "image/jpeg"}}],
            },
        )

        signed(client, chunk)
        signed(client, follow_up)

        first, second = hub_takes_it.calls_to("POST", "/internal/whatsapp/inbound")
        assert (first.body["type"], second.body["type"]) == ("media_placeholder", "image")
        assert second.body["media"]["url"].endswith(str(Delivery.objects.get().id))
        assert Delivery.objects.get().media_id == "555"


def status_notice(state, wamid="wamid.S", **extra):
    return messages(statuses=[{"id": wamid, "status": state, "timestamp": "1760522405", "recipient_id": CUSTOMER, **extra}])


@pytest.mark.django_db
class TestADeliveryStatusReachesTheHub:
    @pytest.fixture
    def sent(self, number, business):
        return Send.objects.create(
            hub=business, idempotency_key="0199e7c2-0000-7000-8000-000000000001", state=Send.State.SENT,
            wa_message_id="wamid.S", month="2025-10",
        )

    def test_it_goes_to_door_2_with_the_hubs_key(self, client, sent, hub_takes_it):
        signed(client, status_notice("delivered"))

        (call,) = hub_takes_it.calls_to("POST", "/internal/whatsapp/status")
        assert call.body == {
            "hub": "bar-manolo",
            "wa_message_id": "wamid.S",
            "client_message_id": "0199e7c2-0000-7000-8000-000000000001",
            "status": "delivered",
            "error": None,
            "status_at": "2025-10-15T10:00:05Z",
        }

    def test_a_failure_carries_metas_code(self, client, sent, hub_takes_it):
        signed(client, status_notice("failed", errors=[{"code": 131047, "title": "Re-engagement message"}]))

        (call,) = hub_takes_it.calls_to("POST", "/internal/whatsapp/status")
        assert call.body["error"] == {"code": "131047", "message": "Re-engagement message"}

    def test_a_late_older_status_never_undoes_a_newer_one(self, client, sent, hub_takes_it):
        signed(client, status_notice("read"))
        signed(client, status_notice("delivered"))

        statuses = [call.body["status"] for call in hub_takes_it.calls_to("POST", "/internal/whatsapp/status")]
        assert statuses == ["read"]
        assert Delivery.objects.get(kind=Delivery.Kind.STATUS).body["status"] == "read"

    def test_a_status_of_a_message_the_hub_did_not_send_is_not_pushed(self, client, number, hub_takes_it):
        """Sent from the WhatsApp Business app with the same number: the Hub has no key for it."""
        signed(client, status_notice("delivered", wamid="wamid.phone"))

        assert hub_takes_it.calls_to("POST", "/internal/whatsapp/status") == []
