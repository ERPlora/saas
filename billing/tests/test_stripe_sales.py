"""What a business buys, at which net price, and what its renewal charges, net: the plan Stripe bills and the modules
it bought, at the prices of a billing, with what is being bought. The simplified-invoice limit decides on that whole
renewal (``price_sale``)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.models import Module
from billing.services import stripe_sales
from billing.tests.conftest import pay
from hubs.models import Plan, Subscription, SubscriptionItem
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db


@pytest.fixture
def reports(db):
    """A second paid module on sale: 7 € a month, 70 € a year (net)."""
    return Module.objects.create(
        slug="reports",
        tier=Module.Tier.ENTERPRISE,
        price_monthly_cents=700,
        price_annual_cents=7000,
        stripe_price_id_monthly="price_reports_month",
        stripe_price_id_annual="price_reports_year",
    )


@pytest.fixture
def paying(shop, inventory):
    """``shop`` paying Starter (29.99 € a month, 299.90 € a year) and a module (10 €, 100 €)."""
    return local(pay(shop, modules=["inventory"]))


def local(hub) -> Subscription:
    return Subscription.objects.select_related("plan").get(hub=hub)


def renewal(subscription, interval="month", **asked) -> Decimal:
    return stripe_sales._recurring_net(subscription, interval, **asked)


class TestItsNetPrice:
    @pytest.mark.parametrize("interval,net", [("month", "29.99"), ("year", "299.90")])
    def test_a_plan_is_sold_at_that_billings(self, shop, interval, net):
        assert stripe_sales.plan_sale(shop, "starter", interval).net == Decimal(net)

    @pytest.mark.parametrize("interval,net", [("month", "10"), ("year", "100")])
    def test_a_module_is_sold_at_that_billings(self, inventory, interval, net):
        assert stripe_sales.module_sale("inventory", interval).net == Decimal(net)

    @pytest.mark.parametrize(
        "price_id,kind,slug,net",
        [
            ("price_starter_month", "plan", "starter", "29.99"),
            ("price_starter_year", "plan", "starter", "299.90"),
            ("price_inventory_month", "module", "inventory", "10"),
            ("price_inventory_year", "module", "inventory", "100"),
        ],
    )
    def test_what_stripe_bills_already_is_at_the_one_of_its_price(self, paying, price_id, kind, slug, net):
        sale = stripe_sales._item_sale(paying, {"id": "si_1", "price": {"id": price_id}})

        assert (sale.kind, sale.slug, sale.net) == (kind, slug, Decimal(net))


class TestWhatARenewalCharges:
    @pytest.mark.parametrize("interval,net", [("month", "39.99"), ("year", "399.90")])
    def test_the_plan_and_the_module_it_bought_at_the_prices_of_that_billing(self, paying, interval, net):
        assert renewal(paying, interval) == Decimal(net)

    def test_every_module_it_bought(self, shop, inventory, reports):
        assert renewal(local(pay(shop, modules=["inventory", "reports"]))) == Decimal("46.99")

    def test_the_plan_asked_for_instead_of_its_own(self, paying):
        assert renewal(paying, plan=Plan.objects.get(slug="standard")) == Decimal("64.99")

    def test_a_plan_without_a_price_for_that_billing_charges_nothing(self, paying):
        assert renewal(paying, "year", plan=Plan.objects.get(slug="payment-test")) == Decimal("100")

    def test_a_plan_stripe_bills_no_more_does_not_count(self, paying):
        Subscription.objects.filter(pk=paying.pk).update(status="canceled")

        assert renewal(local(paying.hub)) == Decimal("10")

    def test_without_a_subscription_it_charges_nothing(self):
        assert renewal(None) == 0


class TestWhichModulesRenew:
    def write(self, subscription, **fields):
        SubscriptionItem.objects.filter(subscription=subscription, module_slug="inventory").update(**fields)

    def test_one_its_plan_includes_is_not_charged(self, paying):
        self.write(paying, source=SubscriptionItem.Source.PLAN)

        assert renewal(paying) == Decimal("29.99")

    @pytest.mark.parametrize("days", [12, -1], ids=["still_working", "ended"])
    def test_a_cancelled_one_is_not_charged_again(self, paying, days):
        self.write(paying, valid_until=timezone.now() + timedelta(days=days))

        assert renewal(paying) == Decimal("29.99")

    def test_one_off_sale_is_still_charged(self, paying):
        Module.objects.update(is_active=False)

        assert renewal(paying) == Decimal("39.99")

    def test_one_that_left_the_catalogue_is_not_charged(self, paying):
        Module.objects.all().delete()

        assert renewal(paying) == Decimal("29.99")

    def test_another_businesss_are_its_own(self, paying, owner):
        other = pay(create_business(owner, name="Bar Norte"), sub_id="sub_2")

        assert renewal(local(other)) == Decimal("29.99")


class TestWhatIsBeingBought:
    def test_a_module_counts(self, paying, reports):
        assert renewal(paying, adding=stripe_sales.module_sale("reports", "month")) == Decimal("46.99")

    def test_a_plan_is_not_one_thing_more(self, paying):
        assert renewal(paying, adding=stripe_sales.plan_sale(paying.hub, "standard", "month")) == Decimal("39.99")

    def test_a_module_of_a_business_without_a_subscription(self, reports):
        assert renewal(None, adding=stripe_sales.module_sale("reports", "month")) == Decimal("7")
