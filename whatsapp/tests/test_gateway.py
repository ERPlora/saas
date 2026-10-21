"""FIX-SAAS-WHATSAPP-GATEWAY-DOORS · ``gateway.deliver``: what waits reaches the Hub's doors 1 and 2, and how each
answer of the Hub is read (contract: 200 taken; 422 the body does not hold, never retried; 404 ``app_inactive``, a
404 of a Hub without the door, 5xx or no answer: kept and retried with a growing wait)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from whatsapp import gateway
from whatsapp.models import Delivery, PhoneNumber
from whatsapp.tests.test_parse import PHONE_NUMBER_ID, WABA, messages, text
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
    ten minutes it is a message the Hub never sent (the business's phone app) and it is dropped."""
    status = {"id": "wamid.phone", "status": "delivered", "timestamp": "1760522405", "recipient_id": "34600111222"}
    ingest(messages(statuses=[status]))

    assert gateway.deliver()["retried"] == 1

    Delivery.objects.update(next_attempt_at=timezone.now(), received_at=timezone.now() - timedelta(minutes=11))
    assert gateway.deliver()["dropped"] == 1
    assert not Delivery.objects.exists()
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []
