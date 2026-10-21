"""The Stripe events erplora.com received are forgotten after 30 days (BILLING-F37; registry BILLING-G43, G35).

Ported from ERPlora/saas ``apps/dashboard/billing`` (``cleanup_old_webhook_events``, a weekly Celery beat task
there; fi:saas/support/billing-fiscal#task-cleanup_old_webhook_events, origin/develop): the idempotency rows
(``WebhookEvent``) older than 30 days are deleted. Stripe resends an event for 3 days at most and keeps it
30 days, so a row that old never guards a delivery again. Here a ``manage.py`` command run by saas-cron.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from billing import services
from billing.models import WebhookEvent

pytestmark = pytest.mark.django_db


def received(event_id: str, days_ago: float, **fields) -> WebhookEvent:
    event = WebhookEvent.objects.create(event_id=event_id, event_type="invoice.paid", **fields)
    # ``received_at`` is set on insert: moved back afterwards.
    WebhookEvent.objects.filter(pk=event.pk).update(received_at=timezone.now() - timedelta(days=days_ago))
    return event


class TestForgettingOldEvents:
    def test_events_older_than_30_days_are_deleted_the_rest_kept(self):
        received("evt_old", 31, success=True, outcome="processed")
        received("evt_old_failed", 45, success=False, error_message="boom")
        received("evt_recent", 29, success=True, outcome="processed")
        received("evt_today", 0)

        deleted = services.purge_webhook_events()

        assert deleted == 2
        assert sorted(WebhookEvent.objects.values_list("event_id", flat=True)) == ["evt_recent", "evt_today"]

    def test_nothing_old_deletes_nothing(self):
        received("evt_recent", 1)

        assert services.purge_webhook_events() == 0
        assert WebhookEvent.objects.count() == 1

    def test_the_window_is_30_days(self):
        assert services.WEBHOOK_EVENT_RETENTION == timedelta(days=30)


class TestTheCommand:
    def test_it_deletes_and_says_how_many(self, capsys):
        received("evt_old", 40)
        received("evt_recent", 2)

        call_command("purge_webhook_events")

        assert capsys.readouterr().out.strip() == "purge_webhook_events: deleted=1"
        assert list(WebhookEvent.objects.values_list("event_id", flat=True)) == ["evt_recent"]
