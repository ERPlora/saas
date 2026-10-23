"""WHATSAPP-G07 · ``manage.py whatsapp_deliver``: every minute in ``saas-cron``, what still waits for the Hub (it was
off, without the inbox, or answered 5xx) is pushed again once its growing wait passed (``gateway.deliver``), so a
message Meta reported is never lost while the Hub is away.

One pass at a time (FIX-SAAS-WHATSAPP-DELIVER-OVERLAP): under the advisory lock of its name, and each pass pushes only
what fits in its time, inside the lease of what it claimed. A slow Hub is played by a clock moved by hand (``Clock``):
its slowness costs the tests no real time.
"""

import threading
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from base.tests.conftest import other_session  # noqa: F401 - a second session, as another saas-cron task
from whatsapp import gateway, hub_client
from whatsapp.models import Delivery
from whatsapp.tests.test_gateway import number  # noqa: F401 - shared fixture
from whatsapp.tests.test_parse import messages, text
from whatsapp.tests.test_services import ingest

pytestmark = pytest.mark.django_db

#: The advisory lock a pass holds (``hubs.services.run_exclusively``, as ``whatsapp_refresh_tokens``).
LOCK_KEY = "hashtext('erplora.saas.whatsapp_deliver')"
INBOUND = r"^/internal/whatsapp/inbound$"
MINUTE = timedelta(minutes=1)


def run(stdout=None) -> str:
    out = stdout or StringIO()
    call_command("whatsapp_deliver", stdout=out)
    return out.getvalue()


class Clock:
    """The wall clock every piece reads (``timezone.now``: the lease, what is due, the pass's time), moved by hand.
    It starts a second ahead of the real one: what is parked meanwhile carries the real time (the model's default),
    and is due."""

    def __init__(self, monkeypatch):
        self.now = timezone.now() + timedelta(seconds=1)
        monkeypatch.setattr(timezone, "now", lambda: self.now)


class SlowHub:
    """The Hub's door 1 taking ``slowness`` per message: each push moves the clock that much, and is noted with the
    pass that made it and whether it ended inside the lease of its row (past it, another run may take the row)."""

    def __init__(self, monkeypatch, clock: Clock, slowness: timedelta):
        self.clock, self.slowness = clock, slowness
        self.pushes: list[tuple[str, str]] = []
        self.late: list[str] = []
        self.after_each = lambda: None
        real = hub_client._post

        def post(path, payload):
            answer = real(path, payload)
            self.clock.now += self.slowness
            wamid = payload["wa_message_id"]
            self.pushes.append((threading.current_thread().name, wamid))
            if self.clock.now > Delivery.objects.get(wa_message_id=wamid).next_attempt_at:
                self.late.append(wamid)
            self.after_each()
            return answer

        monkeypatch.setattr(hub_client, "_post", post)

    def repeated(self) -> list[str]:
        wamids = [wamid for _, wamid in self.pushes]
        return sorted({wamid for wamid in wamids if wamids.count(wamid) > 1})


def test_what_waits_is_pushed_and_counted(number, hub_double):
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    ingest(messages(text("wamid.1")))

    output = run()

    assert "delivered=1" in output
    assert Delivery.objects.get().delivered_at is not None


def test_a_hub_still_away_is_retried_later_without_failing_the_task(number, offline_hub):
    ingest(messages(text("wamid.1")))

    output = run()

    row = Delivery.objects.get()
    assert "retried=1" in output
    assert (row.delivered_at, row.attempts) == (None, 1)


def test_a_full_batch_is_followed_by_the_next_one(number, hub_double):
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    ingest(messages(*(text(f"wamid.{n}") for n in range(12))))

    output = run()

    assert "delivered=12" in output
    assert not Delivery.objects.filter(delivered_at__isnull=True).exists()


def test_a_second_run_returns_at_once_while_one_holds_the_lock(number, hub_double, other_session):
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    ingest(messages(text("wamid.1")))
    other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

    output = run()

    assert "already running" in output
    assert hub_double.calls == []
    assert Delivery.objects.get().delivered_at is None
    other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")


def test_the_lock_is_released_after_a_run(number, hub_double, other_session):
    run()

    assert other_session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[0] is True
    other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")


@pytest.mark.django_db(transaction=True)
def test_two_passes_a_minute_apart_against_a_slow_hub_push_each_message_once(number, hub_double, monkeypatch):
    """The symptom: 100 messages wait, the Hub takes 5 s for each and saas-cron starts the next pass a minute after
    the first, beside it if the first still runs (its own task, its own connection). Before, the first pass leased 50
    for 2 minutes and spent 250 s pushing them: the second took again what the first had not pushed yet, and the Hub
    got those twice. Now the first pass is over before the minute, with every push inside its lease, and the second
    does its own share: nothing is pushed twice and the two never push at the same time."""
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    ingest(messages(*(text(f"wamid.{n}") for n in range(100))))
    clock = Clock(monkeypatch)
    start = clock.now
    hub = SlowHub(monkeypatch, clock, timedelta(seconds=5))
    outputs: dict[str, str] = {}
    ended: dict[str, object] = {}

    def a_pass(name):
        try:
            outputs[name] = run()
            ended[name] = clock.now
        finally:
            connection.close()

    passes = {name: threading.Thread(target=a_pass, args=(name,), name=name) for name in ("first", "second")}

    def at_the_minute():
        if clock.now >= start + MINUTE and passes["second"].ident is None:
            passes["second"].start()
            passes["second"].join(60)

    hub.after_each = at_the_minute
    passes["first"].start()
    passes["first"].join(60)
    if passes["second"].ident is None:
        clock.now = start + MINUTE
        passes["second"].start()
        passes["second"].join(60)

    assert hub.repeated() == []
    assert hub.late == []
    assert ended["first"] <= start + MINUTE
    assert "already running" not in outputs["second"]
    assert {name for name, _ in hub.pushes} == {"first", "second"}


@pytest.mark.django_db(transaction=True)
def test_the_webhook_pushes_inside_the_lease_even_at_the_hubs_slowest(number, hub_double, monkeypatch):
    """Meta's webhook pushes up to 20 of what it parked before answering (``gateway.ingest``), without the pass's
    lock: at the Hub's slowest (5 s to connect and 5 s more to answer, each call) its last push still ends inside the
    lease, so saas-cron's pass never takes a row the webhook is still pushing."""
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    clock = Clock(monkeypatch)
    hub = SlowHub(monkeypatch, clock, hub_client.LONGEST_CALL)

    gateway.ingest(messages(*(text(f"wamid.{n}") for n in range(gateway.WEBHOOK_DELIVERIES))))

    assert len(hub.pushes) == gateway.WEBHOOK_DELIVERIES
    assert hub.late == []
