"""WHATSAPP-G14 · Forget what the Hub already took (``manage.py whatsapp_purge [--days N]``, once a day).

Cases of the old product's ``test_inbound_retention.py``: what the Hub took more than 30 days ago goes, and a delivery
status older than 30 days goes taken or not (a status is news only while its message is recent); the window can be
shortened by hand (1 to 30 days), never lengthened. Its ``parcial`` is fixed: what the Hub never takes (a Hub off, or
without the inbox) does not stay forever (saas#1930) but 30 days, and the keys of the sends and of the templates'
registrations go after 30 days too (saas#2662).
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from whatsapp import services
from whatsapp.models import Delivery, Send, TemplateSubmission
from whatsapp.schemas import PurgeIn

pytestmark = pytest.mark.django_db


def ago(days: float):
    return timezone.now() - timedelta(days=days)


def delivery(hub, wa_id, *, kind="message", received=1, delivered=None):
    return Delivery.objects.create(
        hub=hub, kind=kind, wa_message_id=wa_id, received_at=ago(received),
        delivered_at=None if delivered is None else ago(delivered),
    )


def purge(days=30):
    return services.retention_purge(services.platform_context(), PurgeIn(days=days))


def kept(hub) -> set[str]:
    return set(Delivery.objects.filter(hub=hub).values_list("wa_message_id", flat=True))


def test_what_the_hub_took_more_than_30_days_ago_goes(business):
    delivery(business, "old-taken", received=40, delivered=31)
    delivery(business, "recent-taken", received=40, delivered=29)

    out = purge()

    assert kept(business) == {"recent-taken"}
    assert out.deliveries == 1


def test_a_status_older_than_30_days_goes_taken_or_not(business):
    delivery(business, "old-status", kind="status", received=31)
    delivery(business, "new-status", kind="status", received=2)

    purge()

    assert kept(business) == {"new-status"}


def test_a_message_the_hub_never_took_goes_after_30_days_and_says_so(business, caplog):
    delivery(business, "never-taken", received=31)
    delivery(business, "waiting", received=29)

    out = purge()

    assert kept(business) == {"waiting"}
    assert out.never_taken == 1
    assert "whatsapp.retention.never_taken" in caplog.text


def test_the_keys_of_sends_and_registrations_go_after_30_days(business):
    old = Send.objects.create(hub=business, idempotency_key="old", month="2026-09", wa_message_id="wamid.1")
    Send.objects.filter(pk=old.pk).update(created_at=ago(31))
    Send.objects.create(hub=business, idempotency_key="new", month="2026-10")
    submission = TemplateSubmission.objects.create(hub=business, idempotency_key="old", state="done")
    TemplateSubmission.objects.filter(pk=submission.pk).update(created_at=ago(31))

    out = purge()

    assert list(Send.objects.values_list("idempotency_key", flat=True)) == ["new"]
    assert not TemplateSubmission.objects.exists()
    assert (out.sends, out.registrations) == (1, 1)


def test_a_shorter_window_by_hand(business):
    delivery(business, "taken-3-days-ago", received=4, delivered=3)

    purge(days=2)

    assert kept(business) == set()


def test_another_business_rows_follow_the_same_rule_and_nothing_else(business, other_business):
    delivery(business, "a", received=40, delivered=31)
    delivery(other_business, "b", received=2, delivered=1)

    purge()

    assert kept(other_business) == {"b"}


class TestTheCommand:
    def test_it_purges_and_says_what(self, business):
        delivery(business, "old-taken", received=40, delivered=31)
        out = StringIO()

        call_command("whatsapp_purge", stdout=out)

        assert "deliveries=1" in out.getvalue()
        assert kept(business) == set()

    @pytest.mark.parametrize("days", [0, 31])
    def test_a_window_out_of_1_to_30_days_deletes_nothing(self, business, days):
        delivery(business, "old-taken", received=40, delivered=31)

        with pytest.raises(CommandError):
            call_command("whatsapp_purge", "--days", str(days), stdout=StringIO())

        assert kept(business) == {"old-taken"}
