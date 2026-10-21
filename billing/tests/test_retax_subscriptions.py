"""The live subscription takes the rate the payer's place calls for today (BILLING-F02, BILLING-F06).

Ported from ERPlora/saas ``apps/dashboard/fiscal/services/oss_subscription_retax.py`` (saas#2293, saas#2301,
saas#2308; origin/develop). The checkout and the plan change fix OUR rate on every item and Stripe charges
that same rate on every renewal, so without this a payer who moves from Madrid to Las Palmas keeps paying
21 %, and a consumer in Berlin keeps Spanish VAT after the year crosses the OSS threshold.

Adapted to the new design: one subscription per business (the plan and its modules are items of it), the
same engine as the sale (``services.price_sale``), the next invoice charges the new rate (no proration: the
paid period is not touched). Two doors: right after the owner saves the billing details, and the daily
``manage.py retax_subscriptions`` (an address change whose push failed, a crossing of the threshold, a rate
the table schedules). Instead of a trail row per subscription (old ``OssSubscriptionRetax``), the rates
Stripe holds are compared with the ones due: equal is «unchanged», nothing is sent twice.
"""

import logging

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from billing import services
from billing.models import FiscalPolicy, PlanChangeSchedule
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import item, subscription

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def on_starter(shop, stripe_double, *modules, rates=(), status="active"):
    """The business paying Starter (and ``modules``), each item in Stripe holding ``rates``."""
    paid = pay(shop, modules=modules, status=status)
    lines = [item("si_plan", "price_starter_month", tax_rates=list(rates))] + [
        item(f"si_{slug}", f"price_{slug}_month", tax_rates=list(rates)) for slug in modules
    ]
    stripe_double.answer("subscriptions.retrieve", subscription(items=lines, status=status))
    stripe_double.answer("subscriptions.update", subscription(items=lines, status=status))
    return paid


def move(hub, country, postal_code, tax_id=""):
    profile = hub.billing_profile
    profile.billing_country = country
    profile.billing_postal_code = postal_code
    profile.tax_id = tax_id
    profile.save()
    hub.refresh_from_db()
    return hub


def spanish_rate(stripe_double, shop):
    """The id of the account's ES 21 % rate, as the sale makes it."""
    on_starter(shop, stripe_double)
    services.retax_subscription(shop)
    return stripe_double.last("subscriptions.update").params["items"][0]["tax_rates"][0]


class TestRetaxingOneBusiness:
    def test_an_item_without_our_rate_gets_it_from_the_next_invoice(self, shop, stripe_double):
        paid = on_starter(shop, stripe_double)

        outcome = services.retax_subscription(paid)

        assert outcome == "retaxed"
        sent = stripe_double.last("subscriptions.update")
        assert sent.args == ("sub_1",)
        rate = stripe_double.tax_rates[0]
        assert (rate["country"], rate["percentage"]) == ("ES", 21.0)
        assert sent.params == {
            "items": [{"id": "si_plan", "tax_rates": [rate["id"]]}],
            "proration_behavior": "none",
        }

    def test_a_payer_who_moves_to_the_canary_islands_stops_paying_vat(self, shop, stripe_double):
        """An empty list sends nothing (the SDK drops it) and Stripe keeps the old rate: an empty string is
        what removes it."""
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(move(shop, "ES", "35001"), stripe_double, rates=[rate])

        outcome = services.retax_subscription(paid)

        assert outcome == "retaxed"
        assert stripe_double.last("subscriptions.update").params["items"] == [
            {"id": "si_plan", "tax_rates": ""}
        ]

    def test_the_plan_and_every_module_are_retaxed(self, shop, stripe_double, inventory):
        paid = on_starter(shop, stripe_double, "inventory")

        services.retax_subscription(paid)

        items = stripe_double.last("subscriptions.update").params["items"]
        assert [line["id"] for line in items] == ["si_plan", "si_inventory"]
        assert all(len(line["tax_rates"]) == 1 for line in items)

    def test_the_right_rate_already_held_sends_nothing(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(shop, stripe_double, rates=[rate])
        sent_before = len(stripe_double.calls_to("subscriptions.update"))

        outcome = services.retax_subscription(paid)

        assert outcome == "unchanged"
        assert len(stripe_double.calls_to("subscriptions.update")) == sent_before

    def test_a_business_without_a_paid_plan_is_skipped_without_asking_stripe(self, shop, stripe_double):
        assert services.retax_subscription(shop) == "skipped"
        assert stripe_double.paths() == []

    def test_a_cancelled_subscription_is_skipped(self, shop, stripe_double):
        paid = on_starter(shop, stripe_double, status="canceled")

        assert services.retax_subscription(paid) == "skipped"
        assert stripe_double.calls_to("subscriptions.update") == []

    def test_a_downgrade_waiting_in_a_schedule_is_left_to_the_schedule(self, shop, stripe_double):
        """The schedule holds the items of the next phase: changing the subscription now would be undone at
        the phase change. The daily pass retaxes it once the schedule has let it go."""
        from django.utils import timezone

        paid = on_starter(shop, stripe_double)
        PlanChangeSchedule.objects.create(
            hub=paid,
            stripe_schedule_id="sub_sched_1",
            plan_slug="starter",
            interval="month",
            starts_at=timezone.now(),
        )

        assert services.retax_subscription(paid) == "skipped"
        assert stripe_double.calls_to("subscriptions.update") == []

    def test_a_place_that_is_not_sold_to_keeps_the_old_rate_and_says_so(self, shop, stripe_double, caplog):
        paid = on_starter(move(shop, "US", "10001"), stripe_double)

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            outcome = services.retax_subscription(paid)

        assert outcome == "refused"
        assert stripe_double.calls_to("subscriptions.update") == []
        refused = [record for record in caplog.records if getattr(record, "event", "") == "billing.retax_refused"]
        assert refused and refused[0].code == "billing.tax_engine_missing"

    def test_a_consumer_in_another_member_state_takes_its_rate_once_oss_applies(self, shop, stripe_double):
        """The year crosses the threshold (or ERPlora registers in the OSS): the consumer in Berlin pays
        German VAT from the next invoice."""
        FiscalPolicy.objects.update(oss_registered=True)
        paid = on_starter(move(shop, "DE", "10115"), stripe_double)

        services.retax_subscription(paid)

        rate_id = stripe_double.last("subscriptions.update").params["items"][0]["tax_rates"][0]
        rate = next(rate for rate in stripe_double.tax_rates if rate["id"] == rate_id)
        assert (rate["country"], rate["percentage"]) == ("DE", 19.0)


class TestSavingTheBillingDetails:
    def test_the_live_subscription_is_retaxed_after_the_commit(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        from hubs import services as hub_services
        from hubs.schemas import BillingProfileIn

        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(shop, stripe_double, rates=[rate])
        sent_before = len(stripe_double.calls_to("subscriptions.update"))

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            hub_services.billing_profile_update(
                ctx_for(owner),
                BillingProfileIn(
                    hub_id=paid.id,
                    billing_name="Panadería López SL",
                    billing_address="Calle Triana 1",
                    billing_city="Las Palmas",
                    billing_postal_code="35001",
                    billing_country="ES",
                ),
            )
        assert len(stripe_double.calls_to("subscriptions.update")) == sent_before
        for callback in callbacks:
            callback()

        assert stripe_double.last("subscriptions.update").params["items"] == [
            {"id": "si_plan", "tax_rates": ""}
        ]

    def test_stripe_failing_after_the_save_keeps_the_save_and_is_logged(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks, caplog
    ):
        from billing.tests.stripe_double import connection_error
        from hubs import services as hub_services
        from hubs.models import BillingProfile
        from hubs.schemas import BillingProfileIn

        paid = on_starter(shop, stripe_double)
        stripe_double.answer("subscriptions.retrieve", connection_error())

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            with django_capture_on_commit_callbacks(execute=True):
                hub_services.billing_profile_update(
                    ctx_for(owner),
                    BillingProfileIn(
                        hub_id=paid.id,
                        billing_name="Panadería López SL",
                        billing_postal_code="35001",
                        billing_country="ES",
                    ),
                )

        assert BillingProfile.objects.get(pk=paid.billing_profile_id).billing_postal_code == "35001"
        assert any(getattr(record, "event", "") == "billing.retax_failed" for record in caplog.records)


class TestTheDailyPass:
    def test_it_retaxes_every_live_subscription_and_counts(self, shop, stripe_double, capsys):
        on_starter(shop, stripe_double)
        out = _run()

        assert "retaxed=1" in out
        assert "errors=0" in out

    def test_a_business_it_could_not_retax_ends_the_run_with_an_error(self, shop, stripe_double):
        on_starter(move(shop, "US", "10001"), stripe_double)

        with pytest.raises(CommandError) as failure:
            _run()

        assert "refused=1" in str(failure.value)

    def test_stripe_failing_on_one_business_does_not_stop_the_pass(self, shop, stripe_double):
        from billing.tests.stripe_double import connection_error

        on_starter(shop, stripe_double)
        stripe_double.answer("subscriptions.retrieve", connection_error())

        with pytest.raises(CommandError) as failure:
            _run()

        assert "errors=1" in str(failure.value)


def _run() -> str:
    from io import StringIO

    out = StringIO()
    call_command("retax_subscriptions", stdout=out)
    return out.getvalue()
