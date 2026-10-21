"""The operations behind Meta's webhook and the deliveries to the Hub (WHATSAPP-G07; FIX-SAAS-WHATSAPP-GATEWAY-DOORS).

- ``whatsapp.webhook.ingest`` parks what Meta reported for each active number, once per message;
- ``whatsapp.delivery.claim`` leases what is due, so two processes (the webhook's COMMIT and ``whatsapp_deliver``)
  never push the same thing at once;
- ``whatsapp.delivery.record`` writes how the push ended: taken, retried with a growing wait, refused for good
  (the Hub's 422) or dropped (a status of a message the Hub did not send).
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.context import Scope, system_context

from whatsapp import services
from whatsapp.models import Delivery, PhoneNumber
from whatsapp.schemas import ClaimIn, IngestIn, RecordIn
from whatsapp.tests.test_parse import PHONE_NUMBER_ID, WABA, messages, text

pytestmark = pytest.mark.django_db
CTX = system_context(Scope("platform", "whatsapp"))


@pytest.fixture
def number(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id=PHONE_NUMBER_ID, display_phone="+34 910", waba_id=WABA, access_token="t"
    )


def ingest(payload):
    return services.webhook_ingest(CTX, IngestIn(payload=payload))


def claim(**fields):
    return services.delivery_claim(CTX, ClaimIn(**fields)).deliveries


def record(delivery, outcome, error=""):
    return services.delivery_record(CTX, RecordIn(id=delivery.id, revision=delivery.revision, outcome=outcome, error=error))


def test_ingest_parks_each_message_once_and_names_its_business(number):
    first = ingest(messages(text("wamid.1"), text("wamid.2")))
    again = ingest(messages(text("wamid.1")))

    assert (first.parked, first.hub_ids) == (2, [number.hub_id])
    assert (again.parked, again.hub_ids) == (0, [])
    assert Delivery.objects.count() == 2


def test_ingest_records_its_event_without_the_customers_words(number):
    from live.models import OutboxEvent

    ingest(messages(text("wamid.1", body="Mi secreto")))

    (event,) = OutboxEvent.objects.filter(name="whatsapp.webhook.ingested")
    assert event.payload == {"parked": 1, "statuses": 0, "verdicts": 0, "discarded": 0}
    assert "secreto" not in str(event.payload)


def test_a_claim_leases_what_is_due_so_a_second_claim_gets_nothing(number):
    ingest(messages(text("wamid.1")))

    (delivery,) = claim()

    assert delivery.body["hub"] == "bar-manolo"
    assert claim() == []


def test_a_claim_can_be_narrowed_to_some_businesses(number, other_business):
    ingest(messages(text("wamid.1")))

    assert claim(hub_ids=[other_business.id]) == []
    assert len(claim(hub_ids=[number.hub_id])) == 1


@pytest.mark.parametrize(("attempts", "seconds"), [(1, 30), (2, 60), (3, 120), (6, 960), (7, 1920), (8, 3600), (20, 3600)])
def test_a_retry_waits_longer_each_time_up_to_an_hour(number, attempts, seconds):
    ingest(messages(text("wamid.1")))
    Delivery.objects.update(attempts=attempts - 1)
    (delivery,) = claim()

    before = timezone.now()
    record(delivery, "retry", "HTTP 404")

    row = Delivery.objects.get()
    assert row.attempts == attempts and row.last_error == "HTTP 404"
    assert before + timedelta(seconds=seconds - 1) <= row.next_attempt_at <= timezone.now() + timedelta(seconds=seconds + 1)


def test_a_refused_body_is_never_retried(number):
    ingest(messages(text("wamid.1")))
    (delivery,) = claim()

    record(delivery, "refused", "HTTP 422 invalid_payload")

    row = Delivery.objects.get()
    assert (row.delivered_at, row.next_attempt_at) == (None, None)
    Delivery.objects.update(next_attempt_at=None)
    assert claim() == []


def test_a_status_that_moved_on_during_the_push_stays_due(number, business):
    from whatsapp.models import Send

    Send.objects.create(hub=business, idempotency_key="k", state=Send.State.SENT, wa_message_id="wamid.S", month="2025-10")
    status = {"id": "wamid.S", "status": "delivered", "timestamp": "1760522405", "recipient_id": "34600111222"}
    ingest(messages(statuses=[status]))
    (delivered,) = claim()

    ingest(messages(statuses=[{**status, "status": "read"}]))
    record(delivered, "delivered")

    row = Delivery.objects.get()
    assert row.delivered_at is None and row.body["status"] == "read"
    (again,) = claim()
    assert again.body["status"] == "read" and again.body["client_message_id"] == "k"


def test_a_taken_delivery_is_marked(number):
    ingest(messages(text("wamid.1")))
    (delivery,) = claim()

    record(delivery, "delivered")

    assert Delivery.objects.get().delivered_at is not None


def test_a_dropped_delivery_is_gone(number):
    ingest(messages(text("wamid.1")))
    (delivery,) = claim()

    record(delivery, "drop")

    assert not Delivery.objects.exists()


def test_writing_for_business_b_never_touches_business_a(number, other_business):
    """Tenancy (working rules §4b.4): a notice of B's number parks only for B and leases only B's."""
    PhoneNumber.objects.create(hub=other_business, phone_number_id="2", display_phone="+34 2", waba_id="W2", access_token="t")
    notice = messages(text("wamid.B"))
    notice["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "2"

    out = ingest(notice)

    assert out.hub_ids == [other_business.id]
    assert claim(hub_ids=[number.hub_id]) == []
    assert [d.body["hub"] for d in claim()] == ["bar-pepe"]
