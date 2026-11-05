"""WHATSAPP-F07 · The queue the ``saas-worker`` drains (saas#305): the rows of ``Delivery`` still waiting for the Hub.

- Each business's messages reach its Hub in the order they arrived: one the Hub did not take holds the newer ones of
  that business back (in the same batch, held with its wait, and in the passes after it) until it goes, for
  ``services.IN_ORDER_ATTEMPTS`` failed attempts at most (about an hour); another business never waits for it, and a
  status (the furthest one of a message, whatever its order) is never held back.
- What a claim leases nobody else pushes (``SKIP LOCKED`` and the lease): two deliverers at once push each row once.
- What makes a row due or moves its wait wakes the worker after the COMMIT (``NOTIFY whatsapp_delivery``), and
  ``whatsapp.delivery.next_due`` tells it when the next one is due, so it sleeps until then without looking.
"""

import threading
import time
from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from whatsapp import gateway, hub_client, services
from whatsapp.models import Delivery
from whatsapp.queries import delivery_next_due
from whatsapp.schemas import ClaimIn, DueNowIn, HeldDelivery, HoldIn, NextDueIn, RecordIn
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another process
from whatsapp.tests.test_gateway import number  # noqa: F401 - shared fixture
from whatsapp.tests.test_parse import messages, text
from whatsapp.tests.test_services import ingest

pytestmark = pytest.mark.django_db
CTX = services.platform_context()
NOTHING = {"delivered": 0, "retried": 0, "refused": 0, "dropped": 0, "held": 0}


def park(hub, wamid, *, kind="message", ago=0.0, **fields):
    """A row waiting for ``hub``'s Hub, received ``ago`` seconds before now (due now unless ``fields`` say)."""
    return Delivery.objects.create(
        hub=hub,
        kind=kind,
        wa_message_id=wamid,
        body={"wa_message_id": wamid, "type": "text", "text": {"body": "Hola"}},
        received_at=fields.pop("received_at", None) or timezone.now() - timedelta(seconds=ago),
        **fields,
    )


def claim(**fields):
    return services.delivery_claim(CTX, ClaimIn(**fields)).deliveries


def wamids(deliveries) -> list[str]:
    return [delivery.body["wa_message_id"] for delivery in deliveries]


def row(wamid) -> Delivery:
    return Delivery.objects.get(wa_message_id=wamid)


def next_due():
    return delivery_next_due(CTX, NextDueIn()).at


class Clock:
    """``timezone.now`` moved by hand (a second ahead of the real one, so what the model stamps is due)."""

    def __init__(self, monkeypatch):
        self.now = timezone.now() + timedelta(seconds=1)
        monkeypatch.setattr(timezone, "now", lambda: self.now)


class Hub:
    """The Hub's doors 1 and 2, answering 503 for the businesses in ``failing`` and 200 for the others; each push
    noted as ``(slug, wamid)``, in order."""

    def __init__(self, monkeypatch, failing=(), after_each=lambda: None, slowness=0.0):
        self.failing = set(failing)
        self.pushes: list[tuple[str, str]] = []
        self.after_each = after_each
        self._lock = threading.Lock()

        def post(body):
            if slowness:
                time.sleep(slowness)
            with self._lock:
                self.pushes.append((body["hub"], body["wa_message_id"]))
            self.after_each()
            return hub_client.Answer(503 if body["hub"] in self.failing else 200, {})

        monkeypatch.setattr(hub_client, "post_inbound", post)
        monkeypatch.setattr(hub_client, "post_status", post)


# --- The order of each business's messages ----------------------------------------------------------------------


def test_a_message_waits_behind_an_older_one_of_its_business_that_still_waits(business, other_business):
    park(business, "wamid.1", ago=30, attempts=1, next_attempt_at=timezone.now() + timedelta(seconds=30))
    park(business, "wamid.2", ago=20)
    park(business, "wamid.status", kind="status", ago=10)
    park(other_business, "wamid.9", ago=5)

    assert wamids(claim()) == ["wamid.status", "wamid.9"]


def test_a_message_waits_while_an_older_one_of_its_business_is_being_pushed(business):
    park(business, "wamid.1", ago=20)
    park(business, "wamid.2", ago=10)

    assert wamids(claim(limit=1)) == ["wamid.1"]
    assert claim() == []


def test_messages_received_at_the_same_instant_go_in_the_order_they_were_parked(business):
    at = timezone.now()
    for n in range(3):
        park(business, f"wamid.{n}", received_at=at)

    assert wamids(claim(limit=1)) == ["wamid.0"]
    assert claim() == []


@pytest.mark.parametrize(("failed", "claimed"), [(services.IN_ORDER_ATTEMPTS - 1, []), (services.IN_ORDER_ATTEMPTS, ["wamid.2"])])
def test_a_message_the_hub_keeps_failing_on_stops_holding_the_newer_ones_back_after_about_an_hour(
    business, failed, claimed
):
    """A message the Hub cannot take that is not a 422 (a bug of the Hub's on that body) never silences the
    business's inbox: past about an hour of tries, the newer ones go on, each with its own wait."""
    park(business, "wamid.1", ago=7200, attempts=failed, next_attempt_at=timezone.now() + timedelta(hours=1))
    park(business, "wamid.2", ago=10)

    assert wamids(claim()) == claimed
    tried_for = sum((services.retry_wait(n) for n in range(1, services.IN_ORDER_ATTEMPTS)), timedelta())
    assert timedelta(hours=1) <= tried_for <= timedelta(hours=1, minutes=10)


def test_a_business_whose_hub_fails_keeps_its_next_messages_and_the_others_go_on(business, other_business, monkeypatch):
    hub = Hub(monkeypatch, failing={business.slug})
    park(business, "wamid.a1", ago=40)
    park(other_business, "wamid.b1", ago=30)
    park(business, "wamid.a2", ago=20)
    park(other_business, "wamid.b2", ago=10)

    counts = gateway.deliver()

    assert counts == {**NOTHING, "delivered": 2, "retried": 1, "held": 1}
    assert hub.pushes == [(business.slug, "wamid.a1"), (other_business.slug, "wamid.b1"), (other_business.slug, "wamid.b2")]
    failed, held = row("wamid.a1"), row("wamid.a2")
    assert (failed.attempts, held.attempts) == (1, 0)
    assert held.next_attempt_at == failed.next_attempt_at > timezone.now()
    assert held.last_error == "" and held.delivered_at is None


def test_the_held_messages_go_after_the_one_that_failed_once_its_wait_passed(business, monkeypatch):
    clock = Clock(monkeypatch)
    hub = Hub(monkeypatch, failing={business.slug})
    park(business, "wamid.1", ago=20)
    park(business, "wamid.2", ago=10)
    gateway.deliver()
    park(business, "wamid.3")
    hub.pushes.clear()

    clock.now += services.FIRST_WAIT - timedelta(seconds=1)
    assert gateway.deliver([business.id]) == NOTHING
    assert hub.pushes == []

    hub.failing.clear()
    clock.now += timedelta(seconds=2)
    assert gateway.deliver()["delivered"] == 3
    assert hub.pushes == [(business.slug, "wamid.1"), (business.slug, "wamid.2"), (business.slug, "wamid.3")]


def test_a_stop_asked_during_a_batch_gives_back_what_it_has_not_pushed_yet(business, other_business, monkeypatch):
    """The worker asked to stop (a deploy) ends its batch after the push in course: the rest is due again at once for
    the next process, without an attempt counted."""
    stop = threading.Event()
    hub = Hub(monkeypatch, after_each=stop.set)
    for n, hub_row in enumerate((business, other_business, other_business)):
        park(hub_row, f"wamid.{n}", ago=30 - n)

    counts = gateway.deliver(stop=stop)

    assert counts == {**NOTHING, "delivered": 1, "held": 2}
    assert hub.pushes == [(business.slug, "wamid.0")]
    for wamid in ("wamid.1", "wamid.2"):
        assert row(wamid).attempts == 0 and row(wamid).next_attempt_at <= timezone.now()


# --- What record and hold write ---------------------------------------------------------------------------------


def test_a_record_answers_when_its_delivery_is_due_again(business):
    park(business, "wamid.1")
    (delivery,) = claim()

    out = services.delivery_record(
        CTX, RecordIn(id=delivery.id, revision=delivery.revision, outcome="retry", error="HTTP 503")
    )

    assert (out.next_attempt_at, out.attempts) == (row("wamid.1").next_attempt_at, 1)


def test_holding_gives_claimed_rows_back_without_an_attempt_and_leaves_a_newer_revision_due(business, other_business):
    park(business, "wamid.1", ago=20)
    park(other_business, "wamid.2", ago=10)
    first, second = claim()
    # The body of wamid.2 moved on meanwhile (a further status, a placeholder completed): it is due now, as it is.
    Delivery.objects.filter(pk=second.id).update(revision=F("revision") + 1, next_attempt_at=timezone.now())
    until = timezone.now() + timedelta(seconds=30)

    out = services.delivery_hold(
        CTX, HoldIn(deliveries=[HeldDelivery(id=d.id, revision=d.revision) for d in (first, second)], until=until)
    )

    assert out.held == 1
    assert (row("wamid.1").next_attempt_at, row("wamid.1").attempts) == (until, 0)
    assert row("wamid.2").next_attempt_at < until


def test_holding_without_a_time_makes_them_due_now(business):
    park(business, "wamid.1")
    (delivery,) = claim()

    services.delivery_hold(CTX, HoldIn(deliveries=[HeldDelivery(id=delivery.id, revision=delivery.revision)]))

    assert row("wamid.1").next_attempt_at <= timezone.now()


# --- Waking the worker ------------------------------------------------------------------------------------------


def test_a_parked_message_wakes_the_worker_after_the_commit(number, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        ingest(messages(text("wamid.1")))

    assert services.wake_the_worker in callbacks


def test_a_webhook_that_parks_nothing_new_does_not_wake_it(number, django_capture_on_commit_callbacks):
    ingest(messages(text("wamid.1")))

    with django_capture_on_commit_callbacks() as callbacks:
        ingest(messages(text("wamid.1")))

    assert services.wake_the_worker not in callbacks


@pytest.mark.parametrize(("outcome", "wakes"), [("retry", True), ("delivered", False), ("refused", False), ("drop", False)])
def test_a_record_wakes_the_worker_when_the_row_waits_again(business, django_capture_on_commit_callbacks, outcome, wakes):
    park(business, "wamid.1")
    (delivery,) = claim()

    with django_capture_on_commit_callbacks() as callbacks:
        services.delivery_record(CTX, RecordIn(id=delivery.id, revision=delivery.revision, outcome=outcome))

    assert (services.wake_the_worker in callbacks) is wakes


def test_a_record_of_a_body_that_moved_on_wakes_the_worker(business, django_capture_on_commit_callbacks):
    park(business, "wamid.1")
    (delivery,) = claim()
    Delivery.objects.update(revision=F("revision") + 1)

    with django_capture_on_commit_callbacks() as callbacks:
        out = services.delivery_record(CTX, RecordIn(id=delivery.id, revision=delivery.revision, outcome="retry"))

    assert out.outcome == "stale"
    assert services.wake_the_worker in callbacks


def test_due_now_and_hold_wake_the_worker(business, django_capture_on_commit_callbacks):
    waiting = park(business, "wamid.1", attempts=1, next_attempt_at=timezone.now() + timedelta(minutes=5))

    with django_capture_on_commit_callbacks() as due_now:
        services.delivery_due_now(CTX, DueNowIn(ids=[waiting.id]))
    (claimed,) = claim()
    with django_capture_on_commit_callbacks() as held:
        services.delivery_hold(CTX, HoldIn(deliveries=[HeldDelivery(id=claimed.id, revision=claimed.revision)]))

    assert services.wake_the_worker in due_now
    assert services.wake_the_worker in held


def test_a_claim_does_not_wake_the_worker(business, django_capture_on_commit_callbacks):
    park(business, "wamid.1")

    with django_capture_on_commit_callbacks() as callbacks:
        claim()

    assert services.wake_the_worker not in callbacks


@pytest.mark.django_db(transaction=True)
def test_the_worker_hears_a_parked_message_once_it_is_committed(number, other_session):
    other_session.execute("LISTEN whatsapp_delivery")

    with transaction.atomic():
        ingest(messages(text("wamid.1")))
        before = list(other_session.notifies(timeout=0.2, stop_after=1))

    after = list(other_session.notifies(timeout=5, stop_after=1))
    assert before == []
    assert [notify.channel for notify in after] == [services.DELIVERY_CHANNEL] == ["whatsapp_delivery"]


# --- When the next one is due -----------------------------------------------------------------------------------


def test_next_due_is_the_soonest_wait_of_what_still_waits(business, other_business):
    assert next_due() is None
    now = timezone.now()
    soon, later = now + timedelta(seconds=40), now + timedelta(seconds=90)
    park(business, "wamid.1", ago=30, attempts=1, next_attempt_at=later)
    park(business, "wamid.2", ago=20)  # due now, but behind wamid.1: it goes when wamid.1 does
    park(other_business, "wamid.3", ago=10, attempts=1, next_attempt_at=soon)
    park(other_business, "wamid.4", ago=10, attempts=1, next_attempt_at=None)  # refused: never again
    park(other_business, "wamid.5", ago=10, delivered_at=now)  # taken

    assert next_due() == soon
    Delivery.objects.filter(wa_message_id="wamid.3").delete()
    assert next_due() == later


def test_next_due_is_now_or_before_when_something_is_due(business):
    park(business, "wamid.1", ago=5)

    assert next_due() <= timezone.now()


# --- Two deliverers at once -------------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_row_another_deliverer_holds_locked_is_skipped_not_pushed_twice(
    business, other_business, monkeypatch, other_session
):
    hub = Hub(monkeypatch)
    locked = park(business, "wamid.a")
    park(other_business, "wamid.b")

    with other_session.transaction():
        other_session.execute("SELECT id FROM whatsapp_delivery WHERE id = %s FOR UPDATE", [locked.id])
        counts = gateway.deliver()

    assert counts["delivered"] == 1
    assert hub.pushes == [(other_business.slug, "wamid.b")]
    assert row("wamid.a").next_attempt_at == locked.next_attempt_at


@pytest.mark.django_db(transaction=True)
def test_two_deliverers_at_once_push_each_message_once(business, other_business, monkeypatch):
    hub = Hub(monkeypatch, slowness=0.02)
    for n in range(12):
        park(business if n % 2 else other_business, f"wamid.{n}", ago=60 - n)
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def deliverer():
        try:
            start.wait(5)
            gateway.deliver()
            gateway.deliver()
        except BaseException as error:  # noqa: BLE001 - surfaced by the assert below
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=deliverer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert errors == []
    pushed = [wamid for _, wamid in hub.pushes]
    assert sorted(pushed) == sorted(f"wamid.{n}" for n in range(12))
    assert not Delivery.objects.filter(delivered_at__isnull=True).exists()
