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

    def test_a_downgrade_waiting_in_a_schedule_is_left_alone_on_the_subscription(self, shop, stripe_double):
        """The schedule holds the items of every phase: the subscription is never changed directly under it
        (the phase change would undo it); its phases are retaxed instead (``TestADowngradeWaiting``)."""
        paid = on_starter(shop, stripe_double)
        waiting(paid, stripe_double, current=[], following=[])

        services.retax_subscription(paid)

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


def waiting(
    hub,
    stripe_double,
    *,
    current,
    following,
    past=None,
    current_prices=("price_standard_month",),
    following_prices=("price_starter_month",),
):
    """A downgrade (Standard → Starter) waiting in the Stripe schedule ``sub_sched_1``, as Stripe returns it:
    each phase's items with the price as an id and the rates as objects; ``past`` adds a phase already over."""
    from django.utils import timezone

    from billing.tests.stripe_double import DAY, MONTH_END, MONTH_START

    PlanChangeSchedule.objects.create(
        hub=hub, stripe_schedule_id="sub_sched_1", plan_slug="starter", interval="month", starts_at=timezone.now()
    )

    def phase(prices, rates, start, end):
        items = [
            {"price": price, "quantity": 1, "tax_rates": [{"id": rate, "object": "tax_rate"} for rate in rates]}
            for price in prices
        ]
        return {"start_date": start, "end_date": end, "items": items, "trial_end": None, "proration_behavior": "none"}

    phases = [
        phase(current_prices, current, MONTH_START, MONTH_END),
        phase(following_prices, following, MONTH_END, MONTH_END + 30 * DAY),
    ]
    if past is not None:
        phases.insert(0, phase(current_prices, past, MONTH_START - 30 * DAY, MONTH_START))
    schedule = {"id": "sub_sched_1", "object": "subscription_schedule", "status": "active", "subscription": "sub_1",
                "end_behavior": "release", "phases": phases}
    stripe_double.answer("subscription_schedules.retrieve", schedule)
    stripe_double.answer("subscription_schedules.update", schedule)
    return schedule


class TestADowngradeWaiting:
    """A downgrade held in a Stripe schedule: the first invoice of the new plan is billed by its NEXT phase,
    whose items carry the rates fixed when it was scheduled. Moving to Las Palmas meanwhile must reach that
    invoice too, so every phase still to run takes today's rates (checked against Stripe's test API: phases
    are re-stated whole, so an empty list of rates is none, and the current phase changes the subscription at
    once)."""

    def test_every_phase_still_to_run_takes_todays_rate(self, shop, stripe_double):
        from billing.tests.stripe_double import DAY, MONTH_END, MONTH_START

        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(move(shop, "ES", "35001"), stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[rate])

        outcome = services.retax_subscription(paid)

        assert outcome == "retaxed"
        sent = stripe_double.last("subscription_schedules.update")
        assert sent.args == ("sub_sched_1",)
        assert sent.params == {
            "end_behavior": "release",
            "phases": [
                {"items": [{"price": "price_standard_month", "quantity": 1, "tax_rates": []}],
                 "start_date": MONTH_START, "end_date": MONTH_END, "proration_behavior": "none"},
                {"items": [{"price": "price_starter_month", "quantity": 1, "tax_rates": []}],
                 "start_date": MONTH_END, "end_date": MONTH_END + 30 * DAY, "proration_behavior": "none"},
            ],
        }

    def test_a_phase_already_over_is_not_restated(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(move(shop, "ES", "35001"), stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[rate], past=[rate])

        services.retax_subscription(paid)

        phases = stripe_double.last("subscription_schedules.update").params["phases"]
        assert [phase["items"][0]["price"] for phase in phases] == ["price_standard_month", "price_starter_month"]

    def test_the_rates_already_held_send_nothing(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(shop, stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[rate])

        assert services.retax_subscription(paid) == "unchanged"
        assert stripe_double.calls_to("subscription_schedules.update") == []

    def test_a_madrid_payer_gets_the_spanish_rate_on_the_phase_that_lacked_it(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(shop, stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[])

        services.retax_subscription(paid)

        phases = stripe_double.last("subscription_schedules.update").params["phases"]
        assert [phase["items"][0]["tax_rates"] for phase in phases] == [[rate], [rate]]

    def test_the_simplified_invoice_limit_is_on_the_whole_renewal_of_a_phase(self, shop, stripe_double, inventory, caplog):
        """Starter annual (299.90 €) and a module (100 €) are 483.88 € with VAT together, each under 400 € alone:
        without the payer's tax ID the phase is not retaxed (its invoice must name the buyer)."""
        paid = on_starter(shop, stripe_double)
        annual = ("price_starter_year", "price_inventory_year")
        waiting(paid, stripe_double, current=[], following=[], current_prices=annual, following_prices=annual)

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            outcome = services.retax_subscription(paid)

        assert outcome == "refused"
        assert [r.code for r in caplog.records if getattr(r, "event", "") == "billing.retax_refused"] == [
            "billing.tax_id_required"
        ]
        assert stripe_double.calls_to("subscription_schedules.update") == []

    def test_with_the_tax_id_on_file_that_phase_is_retaxed(self, shop, stripe_double, inventory):
        shop.billing_profile.tax_id = "12345678Z"
        shop.billing_profile.save()
        paid = on_starter(shop, stripe_double)
        annual = ("price_starter_year", "price_inventory_year")
        waiting(paid, stripe_double, current=[], following=[], current_prices=annual, following_prices=annual)

        assert services.retax_subscription(paid) == "retaxed"

    def test_a_price_no_plan_nor_module_has_keeps_its_rates(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(shop, stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[rate], current_prices=("price_unknown",))

        assert services.retax_subscription(paid) == "unchanged"

    def test_a_trial_and_an_open_end_are_restated_as_they_are(self, shop, stripe_double):
        """A phase in trial keeps its ``trial_end`` (without it Stripe would end the trial); a last phase
        without an end keeps none."""
        from billing.tests.stripe_double import MONTH_END

        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(move(shop, "ES", "35001"), stripe_double, rates=[rate])
        schedule = waiting(paid, stripe_double, current=[rate], following=[rate])
        schedule["phases"][0]["trial_end"] = MONTH_END
        schedule["phases"][1]["end_date"] = None
        stripe_double.answer("subscription_schedules.retrieve", schedule)

        services.retax_subscription(paid)

        current, following = stripe_double.last("subscription_schedules.update").params["phases"]
        assert current["trial_end"] == MONTH_END
        assert "end_date" not in following and "trial_end" not in following

    def test_a_place_that_is_not_sold_to_keeps_the_schedule_as_it_was(self, shop, stripe_double):
        rate = spanish_rate(stripe_double, shop)
        paid = on_starter(move(shop, "US", "10001"), stripe_double, rates=[rate])
        waiting(paid, stripe_double, current=[rate], following=[rate])

        assert services.retax_subscription(paid) == "refused"
        assert stripe_double.calls_to("subscription_schedules.update") == []


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
