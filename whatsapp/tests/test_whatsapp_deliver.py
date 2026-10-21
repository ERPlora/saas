"""WHATSAPP-G07 · ``manage.py whatsapp_deliver``: every minute in ``saas-cron``, what still waits for the Hub (it was
off, without the inbox, or answered 5xx) is pushed again once its growing wait passed (``gateway.deliver``), so a
message Meta reported is never lost while the Hub is away."""

from io import StringIO

import pytest
from django.core.management import call_command

from whatsapp.models import Delivery
from whatsapp.tests.test_gateway import number  # noqa: F401 - shared fixture
from whatsapp.tests.test_parse import messages, text
from whatsapp.tests.test_services import ingest

pytestmark = pytest.mark.django_db


def test_what_waits_is_pushed_and_counted(number, hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    ingest(messages(text("wamid.1")))
    out = StringIO()

    call_command("whatsapp_deliver", stdout=out)

    assert "delivered=1" in out.getvalue()
    assert Delivery.objects.get().delivered_at is not None


def test_a_hub_still_away_is_retried_later_without_failing_the_task(number, offline_hub):
    ingest(messages(text("wamid.1")))
    out = StringIO()

    call_command("whatsapp_deliver", stdout=out)

    row = Delivery.objects.get()
    assert "retried=1" in out.getvalue()
    assert (row.delivered_at, row.attempts) == (None, 1)


def test_a_full_batch_is_followed_by_the_next_one(number, hub_double, monkeypatch):
    from whatsapp.management.commands import whatsapp_deliver

    monkeypatch.setattr(whatsapp_deliver, "BATCH", 1)
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
    ingest(messages(text("wamid.1"), text("wamid.2")))
    out = StringIO()

    call_command("whatsapp_deliver", stdout=out)

    assert "delivered=2" in out.getvalue()
    assert not Delivery.objects.filter(delivered_at__isnull=True).exists()
