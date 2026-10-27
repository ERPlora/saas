"""HUBS-F20: a business suspended for an unpaid plan is warned and, at the end, deleted (``services.age_suspended``).

PLAN-SAAS §1.1, round 2026-10-15b: «tras ``suspended``, los dos avisos y la baja a los 180 días por el camino de
§3.4 (90 días para recuperar y paquete de salida), dentro de ``sweep_unpaid``»; block 13: «un negocio suspendido
recibe los avisos de los días 30 y 150 y se da de baja el 180 por §3.4 (test con reloj)». Cases ported from
ERPlora/saas ``apps/dashboard/hubs/main/tests/test_suspended_hub_lifecycle.py`` (origin/develop): suspending dates
the clock and paying again stops it and forgets the notices; nothing before the first threshold; each notice goes
out once and names the date; at the end the business is deleted the way its owner deletes it; a suspension nobody
dated is never deleted; one business that fails never stops the pass. Dropped with their reason: the reduced
suspension rate, the demo and the platform hub (none of them is a suspended business of the SaaS), the backup, the
exit package and the server (the Hub's, PLAN-DB «Exports», phase 2) and the beat schedule (``sweep_unpaid`` runs
hourly from ``saas-cron``).
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from hubs import services
from hubs.models import Hub, Plan, Subscription
from hubs.schemas import SubscriptionApplyIn
from hubs.services import (
    SUSPENDED_DELETE_DAYS,
    SUSPENDED_FINAL_NOTICE_DAYS,
    SUSPENDED_WARN_DAYS,
)
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid(business):
    """The owner's business on Starter, paid in Stripe and active."""
    Subscription.objects.filter(hub=business).update(
        plan=Plan.objects.get(slug="starter"), stripe_subscription_id="sub_live"
    )
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.ACTIVE, ready_at=timezone.now())
    business.refresh_from_db()
    return business


def suspend(hub):
    services.subscription_apply(services.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, standing="suspended"))
    hub.refresh_from_db()
    return hub


def suspended_for(hub, days, **notices):
    """``hub`` suspended ``days`` ago, with the notices already sent."""
    Hub.objects.filter(pk=hub.pk).update(
        status=Hub.Status.SUSPENDED, suspended_at=timezone.now() - timedelta(days=days), **notices
    )
    # The unpaid episode that suspended it (billing writes it with ``hubs.subscription.apply``).
    Subscription.objects.filter(hub=hub).update(
        unpaid_reason=Subscription.UnpaidReason.PAYMENT_FAILED, unpaid_since=timezone.now() - timedelta(days=days + 7)
    )
    hub.refresh_from_db()
    return hub


class TestTheClock:
    def test_suspending_for_an_unpaid_plan_starts_it(self, paid):
        before = timezone.now()

        hub = suspend(paid)

        assert hub.status == Hub.Status.SUSPENDED
        assert hub.suspended_at >= before
        assert (hub.suspension_warned_at, hub.suspension_final_notice_at) == (None, None)

    def test_paying_again_stops_it_and_forgets_the_notices(self, paid):
        hub = suspended_for(paid, 160, suspension_warned_at=timezone.now(), suspension_final_notice_at=timezone.now())

        services.subscription_apply(services.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, standing="good"))
        hub.refresh_from_db()

        assert hub.status == Hub.Status.ACTIVE
        assert (hub.suspended_at, hub.suspension_warned_at, hub.suspension_final_notice_at) == (None, None, None)

    def test_a_second_suspension_of_the_same_episode_keeps_its_date(self, paid):
        hub = suspend(paid)
        dated = hub.suspended_at

        assert suspend(hub).suspended_at == dated


class TestTheNotices:
    def test_nothing_happens_before_the_first_threshold(self, paid):
        suspended_for(paid, SUSPENDED_WARN_DAYS - 1)

        counts = services.age_suspended()

        assert (counts["warned"], counts["final_notice"], counts["expired"]) == (0, 0, 0)
        assert mail.outbox == []

    def test_the_first_notice_goes_out_once_and_names_the_deletion_date(self, paid, owner):
        hub = suspended_for(paid, SUSPENDED_WARN_DAYS)

        assert services.age_suspended()["warned"] == 1
        assert services.age_suspended()["warned"] == 0
        hub.refresh_from_db()

        assert hub.suspension_warned_at is not None
        assert [message.to for message in mail.outbox] == [[owner.email]]
        delete_on = hub.suspended_at + timedelta(days=SUSPENDED_DELETE_DAYS)
        assert str(delete_on.year) in mail.outbox[0].body
        assert f"/dashboard/billing/invoices?business={hub.id}" in mail.outbox[0].body

    def test_the_final_notice_goes_out_once(self, paid):
        hub = suspended_for(paid, SUSPENDED_FINAL_NOTICE_DAYS, suspension_warned_at=timezone.now())

        assert services.age_suspended()["final_notice"] == 1
        assert services.age_suspended()["final_notice"] == 0
        hub.refresh_from_db()

        assert hub.suspension_final_notice_at is not None
        assert len(mail.outbox) == 1

    def test_a_late_pass_sends_only_the_notice_that_is_due(self, paid):
        suspended_for(paid, SUSPENDED_FINAL_NOTICE_DAYS + 3)

        counts = services.age_suspended()

        assert (counts["warned"], counts["final_notice"]) == (0, 1)
        assert len(mail.outbox) == 1

    def test_the_notice_speaks_the_owners_language(self, paid, owner):
        suspended_for(paid, SUSPENDED_WARN_DAYS)

        services.age_suspended()

        assert owner.language == "es"
        assert "sigue suspendido" in mail.outbox[0].subject
        assert "se eliminará el" in mail.outbox[0].body

    def test_a_notice_that_cannot_leave_is_sent_again_on_the_next_pass(self, paid):
        hub = suspended_for(paid, SUSPENDED_WARN_DAYS)

        # A mailer that cannot connect (nothing listens there).
        with override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                                                    "OPTIONS": {"host": "127.0.0.1", "port": 9, "timeout": 1}}}):
            counts = services.age_suspended()
        hub.refresh_from_db()

        assert (counts["warned"], counts["mail_failed"], hub.suspension_warned_at) == (0, 1, None)
        assert services.age_suspended()["warned"] == 1


class TestTheEnd:
    def test_it_is_deleted_the_way_its_owner_deletes_it(self, paid, owner, django_capture_on_commit_callbacks):
        hub = suspended_for(paid, SUSPENDED_DELETE_DAYS, suspension_warned_at=timezone.now(), suspension_final_notice_at=timezone.now())

        with django_capture_on_commit_callbacks(execute=True):
            counts = services.age_suspended()
        hub.refresh_from_db()

        assert counts["expired"] == 1
        assert hub.status == Hub.Status.DELETING
        assert hub.deletion_requested_at is not None and hub.pending_hub_call == "delete"
        # Its plan goes back to Free and Stripe's subscription ends in the same sweep (billing).
        subscription = Subscription.objects.get(hub=hub)
        assert (subscription.plan.slug, subscription.cancel_requested_at is not None) == ("free", True)
        # The owner is told until when it can be recovered.
        assert [message.to for message in mail.outbox] == [[owner.email]]
        assert str(hub.purge_after.year) in mail.outbox[0].body
        # And why: it stayed suspended for an unpaid invoice (not the owner's own deletion).
        assert f"Llevaba {SUSPENDED_DELETE_DAYS} días suspendido" in mail.outbox[0].body

    def test_not_without_its_last_notice(self, paid):
        hub = suspended_for(paid, SUSPENDED_DELETE_DAYS + 5, suspension_warned_at=timezone.now())

        counts = services.age_suspended()
        hub.refresh_from_db()

        assert (counts["expired"], counts["final_notice"], hub.status) == (0, 1, Hub.Status.SUSPENDED)

    def test_a_suspension_nobody_dated_is_never_deleted(self, paid):
        Hub.objects.filter(pk=paid.pk).update(status=Hub.Status.SUSPENDED, suspended_at=None)

        counts = services.age_suspended()
        paid.refresh_from_db()

        assert (counts["undated"], paid.status) == (1, Hub.Status.SUSPENDED)
        assert mail.outbox == []

    def test_only_suspended_businesses_enter(self, paid, owner, make_user):
        Hub.objects.filter(pk=paid.pk).update(suspended_at=timezone.now() - timedelta(days=SUSPENDED_DELETE_DAYS + 1))
        create_business(make_user("other@example.com"), name="Otro Bar")

        counts = services.age_suspended()

        assert sum(counts.values()) == 0

    def test_a_business_that_fails_never_stops_the_pass(self, paid, make_user):
        other = suspended_for(
            Hub.objects.get(pk=create_business(make_user("other@example.com"), name="Otro Bar").pk), SUSPENDED_WARN_DAYS
        )
        suspended_for(paid, SUSPENDED_WARN_DAYS)
        real = services.business_age_suspension

        def flaky(ctx, data):
            if data.id == paid.id:
                raise RuntimeError("boom")
            return real(ctx, data)

        with mock.patch.object(services, "business_age_suspension", side_effect=flaky):
            counts = services.age_suspended()
        other.refresh_from_db()

        assert (counts["errors"], counts["warned"], other.suspension_warned_at is not None) == (1, 1, True)


def test_only_the_platform_runs_a_step(paid, owner):
    from live.errors import PermissionDenied

    from hubs.schemas import ByIdIn
    from hubs.tests.conftest import ctx_for

    suspended_for(paid, SUSPENDED_DELETE_DAYS, suspension_final_notice_at=timezone.now())

    with pytest.raises(PermissionDenied) as refused:
        services.business_age_suspension(ctx_for(owner), ByIdIn(id=paid.id))

    assert refused.value.code == "internal_command"


def test_the_hourly_sweep_runs_the_clock(paid):
    """``billing.services.sweep_unpaid`` (hourly, ``saas-cron``) runs it: PLAN-SAAS §1.1 «dentro de sweep_unpaid»."""
    from billing import services as billing_services

    suspended_for(paid, SUSPENDED_WARN_DAYS)

    counts = billing_services.sweep_unpaid()

    assert counts["warned"] == 1
