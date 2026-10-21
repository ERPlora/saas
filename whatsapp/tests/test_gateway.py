"""FIX-SAAS-WHATSAPP-GATEWAY-DOORS · ``gateway.deliver``: what waits reaches the Hub's doors 1 and 2, and how each
answer of the Hub is read (contract: 200 taken; 422 the body does not hold, never retried; 404 ``app_inactive``, a
404 of a Hub without the door, 5xx or no answer: kept and retried with a growing wait)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from whatsapp import gateway
from whatsapp.models import Delivery, PhoneNumber
from whatsapp.tests.test_parse import BUSINESS, CUSTOMER, PHONE_NUMBER_ID, WABA, messages, text, webhook
from whatsapp.tests.test_services import ingest

pytestmark = pytest.mark.django_db


@pytest.fixture
def number(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id=PHONE_NUMBER_ID, display_phone="+34 910", waba_id=WABA, access_token="t"
    )


def test_a_due_delivery_reaches_door_1(number, hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    ingest(messages(text("wamid.1")))

    assert gateway.deliver() == {"delivered": 1, "retried": 0, "refused": 0, "dropped": 0}

    assert Delivery.objects.get().delivered_at is not None


@pytest.mark.parametrize(
    ("status", "body"),
    [(404, {"error": {"code": "app_inactive", "message": "Off."}}), (500, {}), (503, {}), (401, {})],
)
def test_anything_but_200_or_422_is_retried(number, hub_double, status, body):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", status, body)
    ingest(messages(text("wamid.1")))

    assert gateway.deliver()["retried"] == 1

    row = Delivery.objects.get()
    assert row.delivered_at is None and row.next_attempt_at > timezone.now()
    assert str(status) in row.last_error


def test_a_422_is_not_retried(number, hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 422, {"error": {"code": "invalid_payload", "message": "x"}})
    ingest(messages(text("wamid.1")))

    assert gateway.deliver()["refused"] == 1

    assert Delivery.objects.get().next_attempt_at is None


def test_no_hub_at_all_is_retried(number, offline_hub):
    ingest(messages(text("wamid.1")))

    assert gateway.deliver()["retried"] == 1
    assert "Unreachable" in Delivery.objects.get().last_error or "POST" in Delivery.objects.get().last_error


def test_what_is_not_due_yet_waits(number, hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    ingest(messages(text("wamid.1")))
    Delivery.objects.update(next_attempt_at=timezone.now() + timedelta(minutes=5))

    assert gateway.deliver()["delivered"] == 0
    assert hub_double.calls_to("POST", "/internal/whatsapp/inbound") == []


def test_a_status_without_the_hubs_key_waits_ten_minutes_then_goes(number, hub_double):
    """The answer of a send may be stored a moment after Meta's status arrives: the key is looked for again; after
    ten minutes it is of a message the Hub never had (neither sent nor handed over) and it is dropped."""
    status = {"id": "wamid.phone", "status": "delivered", "timestamp": "1760522405", "recipient_id": "34600111222"}
    ingest(messages(statuses=[status]))

    assert gateway.deliver()["retried"] == 1

    Delivery.objects.update(next_attempt_at=timezone.now(), received_at=timezone.now() - timedelta(minutes=11))
    assert gateway.deliver()["dropped"] == 1
    assert not Delivery.objects.exists()
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []


def owner_replies_from_the_phone(wamid="wamid.echo"):
    """Meta's echo of what the owner wrote in the WhatsApp Business app (coexistence): the Hub keeps it as theirs."""
    echo = {"from": BUSINESS, "to": CUSTOMER, "id": wamid, "timestamp": "1760522400", "type": "text", "text": {"body": "Sí"}}
    return webhook(
        "smb_message_echoes",
        {"metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID}, "message_echoes": [echo]},
    )


def read(wamid="wamid.echo"):
    return messages(statuses=[{"id": wamid, "status": "read", "timestamp": "1760522405", "recipient_id": CUSTOMER}])


def test_the_status_of_the_owners_reply_from_the_phone_reaches_the_hub_without_a_key(number, hub_double):
    """The Hub shows the owner's replies from the phone in the conversation («Sent», hub#127) and takes their status
    without a key of its own (it never sent them): once erplora.com handed the echo over, its «read» follows."""
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    hub_double.answer("POST", r"^/internal/whatsapp/status$", 200, {"updated": True, "status": "read"})
    ingest(owner_replies_from_the_phone())
    assert gateway.deliver()["delivered"] == 1

    ingest(read())

    assert gateway.deliver() == {"delivered": 1, "retried": 0, "refused": 0, "dropped": 0}
    [call] = hub_double.calls_to("POST", "/internal/whatsapp/status")
    assert call.body["wa_message_id"] == "wamid.echo" and call.body["status"] == "read"
    assert "client_message_id" not in call.body


def test_the_status_of_a_reply_still_waiting_for_the_hub_waits_with_it(number, hub_double):
    """Sent before its echo, the Hub would answer «unknown message» and the «read» would be lost: it waits for the
    echo however long the Hub keeps it waiting, past the ten minutes of a status without a key."""
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 503, {})
    hub_double.answer("POST", r"^/internal/whatsapp/status$", 200, {"updated": False, "status": None})
    ingest(owner_replies_from_the_phone())
    ingest(read())
    Delivery.objects.update(received_at=timezone.now() - timedelta(minutes=30))

    assert gateway.deliver() == {"delivered": 0, "retried": 2, "refused": 0, "dropped": 0}
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []
    assert "reply" in Delivery.objects.get(kind="status").last_error


def test_the_status_of_a_reply_the_hub_refused_has_nowhere_to_go(number, hub_double):
    """A reply the Hub refused as it was (422) never reaches it: its status is one of a message the Hub does not
    have, and goes after the ten minutes."""
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 422, {"error": {"code": "invalid_payload", "message": "x"}})
    ingest(owner_replies_from_the_phone())
    assert gateway.deliver()["refused"] == 1
    ingest(read())
    Delivery.objects.filter(kind="status").update(received_at=timezone.now() - timedelta(minutes=11))

    assert gateway.deliver() == {"delivered": 0, "retried": 0, "refused": 0, "dropped": 1}
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []


def test_a_status_naming_a_customers_message_is_not_the_business_reply(number, hub_double):
    """Meta reports the status of what the business sends: one naming a customer's message is of no message of
    the business the Hub has, and waits for a key like any unknown one."""
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    ingest(messages(text("wamid.customer")))
    assert gateway.deliver()["delivered"] == 1

    ingest(read("wamid.customer"))

    assert gateway.deliver()["retried"] == 1
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []
