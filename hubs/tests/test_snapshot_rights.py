"""HUBS-F34 (HUBS-G107, HUBS-G109, HUBS-G16): the paid apps a business may use, and why, travel in its own snapshot
only.

The old SaaS answered the Hub's «Plan» tab of an app with the purchase of THAT business (SAAS_DASHBOARD-F62) and gave
nothing for a purchase without one (SAAS_PUBLIC-F20: «1 compra = 1 hub»). Here a right is a row of the business's own
subscription: its ``modules[]`` say each app's ``source`` (``plan`` or ``purchase``) and until when it holds, and
neither a purchase nor the paid plan of another business, even of the same account, ever reaches it.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.models import Module
from hubs import queries, services
from hubs.models import Plan, Subscription, SubscriptionItem
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid_business(owner, business):
    """Two businesses of one account: the first on Standard (it pays, so a second one may be created) and the
    second on Free."""
    Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="standard"))
    return business, create_business(owner, name="Bar Manolo 2")


def module_ids(hub):
    return [module["id"] for module in queries.hub_snapshot(hub.id)["modules"]]


def test_a_purchase_reaches_only_the_business_it_was_bought_for(make_user, plans):
    Module.objects.create(slug="inventory", tier="basic")
    mine = create_business(make_user("ana@example.com"), name="Peluquería Ana")
    theirs = create_business(make_user("luis@example.com"), name="Bar Luis")
    SubscriptionItem.objects.create(
        subscription=mine.subscription, module_slug="inventory", source=SubscriptionItem.Source.PURCHASE
    )

    assert (module_ids(mine), module_ids(theirs)) == (["inventory"], [])


def test_the_paid_plan_of_one_business_gives_nothing_to_another_of_the_same_account(paid_business):
    Module.objects.create(slug="inventory", tier="basic")
    standard, free = paid_business
    services.sync_plan_modules(Subscription.objects.get(hub=standard))
    services.sync_plan_modules(Subscription.objects.get(hub=free))

    assert module_ids(standard) == ["inventory"]
    assert module_ids(free) == []
    assert queries.hub_snapshot(free.id)["plan"]["slug"] == "free"


def test_each_app_says_where_its_right_comes_from_and_until_when(business):
    Module.objects.create(slug="inventory", tier="basic")
    Module.objects.create(slug="loyalty", tier="free")
    until = timezone.now() + timedelta(days=12)
    SubscriptionItem.objects.create(
        subscription=business.subscription,
        module_slug="inventory",
        source=SubscriptionItem.Source.PURCHASE,
        valid_until=until,
    )
    services.sync_plan_modules(Subscription.objects.get(hub=business))

    assert queries.hub_snapshot(business.id)["modules"] == [
        {"id": "inventory", "source": "purchase", "valid_until": until.isoformat()},
        {"id": "loyalty", "source": "plan", "valid_until": None},
    ]
