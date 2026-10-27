"""BILLING-F33, F34 and F35 as the Hub receives them: the photo each moment of a paid app's end owes the business.

The Hub decides what a business may use from the last photo the SaaS pushed to it (``PUT /internal/hubs/{id}/state``;
the Hub's ``base/entitlement.py``, BASE-G12): a paid app runs while that photo names it, and one with ``valid_until``
until that instant, read against the Hub's clock (nobody pushes a photo when a cancelled module's period ends). The Hub
only takes a photo newer than the one it has. So each moment owes it a newer photo with the app's ``id``, ``source``
and ``valid_until`` as they stand:

- cancelling it (BILLING-F33) sends the end of what was paid, and keeping it sends it open-ended again;
- buying it again once that end passed (BILLING-F34) sends it open-ended;
- moving it to another business (BILLING-F35) leaves each business its own right: the end in the first, open-ended
  in the second, and neither photo names the other's.

Over the operations, with the Hub double taking the pushes each COMMIT queues, as in production.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from billing import services
from billing.schemas import CheckoutConfirmIn, ModuleIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import MONTH_END, item, subscription
from hubs import services as hub_services
from hubs.models import SubscriptionItem
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db

PLAN = item("si_plan", "price_starter_month")
INVENTORY = item("si_inventory", "price_inventory_month")


@pytest.fixture(autouse=True)
def _doubles(stripe_double, hub_double, issuer_identity):
    return stripe_double


@pytest.fixture
def committed(django_capture_on_commit_callbacks):
    """Run ``call`` and then the pushes its COMMIT queued, as a request does."""

    def run(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    return run


def photo(double, hub) -> dict:
    """The newest photo of ``hub`` the Hub took (a newer version than the one it had)."""
    sent = [call.body for call in double.calls_to("PUT", f"/internal/hubs/{hub.id}/state")]
    assert sent, f"no photo of {hub.slug} reached the Hub"
    assert sent[-1]["version"] == double.versions[str(hub.id)], "the Hub kept an older photo"
    return sent[-1]


def right(slug, valid_until=None) -> dict:
    return {"id": slug, "source": "purchase", "valid_until": valid_until.isoformat() if valid_until else None}


def bought(hub, slug="inventory") -> SubscriptionItem:
    return SubscriptionItem.objects.get(subscription__hub=hub, module_slug=slug)


def cancel(user, hub):
    return services.module_cancel(ctx_for(user), ModuleIn(hub_id=hub.id, module="inventory"))


def keep(user, hub):
    return services.module_keep(ctx_for(user), ModuleIn(hub_id=hub.id, module="inventory"))


def buy(user, hub):
    moment = int(timezone.now().timestamp())
    return services.checkout_confirm(
        ctx_for(user), CheckoutConfirmIn(hub_id=hub.id, module="inventory", proration_date=moment)
    )


def a_second_business_of(owner, committed):
    """Another business of the same owner, paying Starter on its own subscription, its payer in Madrid."""
    hub = create_business(owner, name="Café Central")
    profile = hub.billing_profile
    profile.billing_name = "Café Central SL"
    profile.billing_address = "Calle Mayor 2"
    profile.billing_city = "Madrid"
    profile.billing_postal_code = "28001"
    profile.save()
    return committed(lambda: pay(hub, sub_id="sub_2", customer="cus_2"))


class TestCancellingReachesTheBusiness:
    """BILLING-F33: «… sigue funcionando en … hasta el …; después se apaga»: the Hub learns the date when it is set."""

    def test_cancelling_sends_the_end_of_what_was_paid(self, shop, owner, inventory, stripe_double, hub_double,
                                                      committed):
        paid = committed(lambda: pay(shop, modules=["inventory"]))
        before = photo(hub_double, paid)
        assert before["modules"] == [right("inventory")]
        stripe_double.answer("subscriptions.retrieve", subscription(items=[PLAN, INVENTORY]))
        stripe_double.answer("subscriptions.update", subscription(items=[PLAN]))

        committed(lambda: cancel(owner, paid))

        until = bought(paid).valid_until
        assert int(until.timestamp()) == MONTH_END
        after = photo(hub_double, paid)
        assert after["version"] > before["version"]
        assert after["modules"] == [right("inventory", until)]

    def test_keeping_it_sends_it_open_ended_again(self, shop, owner, inventory, stripe_double, hub_double, committed):
        paid = committed(lambda: pay(shop, modules=["inventory"]))
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[PLAN, INVENTORY]),  # cancelling reads it
            subscription(items=[PLAN]),  # keeping reads it without the module
            subscription(items=[PLAN, INVENTORY]),  # and back with it
        )
        stripe_double.answer("subscriptions.update", subscription(items=[PLAN]))
        stripe_double.answer("subscription_items.create", INVENTORY)
        committed(lambda: cancel(owner, paid))
        cancelled = photo(hub_double, paid)
        assert cancelled["modules"][0]["valid_until"] is not None

        committed(lambda: keep(owner, paid))

        kept = photo(hub_double, paid)
        assert kept["version"] > cancelled["version"]
        assert kept["modules"] == [right("inventory")]


class TestTheEndReachesTheBusiness:
    """BILLING-F34: past its end the business is without it; bought again, the business has it again."""

    def test_buying_it_again_after_its_end_sends_it_open_ended(self, shop, owner, inventory, stripe_double,
                                                               hub_double, committed):
        paid = committed(lambda: pay(shop, modules=["inventory"]))
        # Cancelled, and its period over: it left Stripe and the Store sells it again.
        SubscriptionItem.objects.filter(subscription__hub=paid, module_slug="inventory").update(
            stripe_item_id="", valid_until=timezone.now() - timedelta(minutes=1)
        )
        # Whatever pushes the next photo (a member, the plan…): it no longer names it.
        hub_services.bump_state(paid.id)
        committed(lambda: hub_services.sync_hub(paid.id))
        ended = photo(hub_double, paid)
        assert ended["modules"] == []
        stripe_double.answer(
            "subscriptions.retrieve", subscription(items=[PLAN]), subscription(items=[PLAN, INVENTORY])
        )
        stripe_double.answer("subscription_items.create", INVENTORY)

        committed(lambda: buy(owner, paid))

        again = photo(hub_double, paid)
        assert again["version"] > ended["version"]
        assert again["modules"] == [right("inventory")]
        assert (bought(paid).valid_until, bought(paid).stripe_item_id) == (None, "si_inventory")


class TestMovingItToAnotherBusiness:
    """BILLING-F35: cancelled in one business and bought in another; each photo says its own business's right."""

    def test_the_first_keeps_it_until_its_end_and_the_second_has_it_open_ended(
        self, shop, owner, inventory, stripe_double, hub_double, committed
    ):
        first = committed(lambda: pay(shop, modules=["inventory"]))
        second = a_second_business_of(owner, committed)
        assert photo(hub_double, second)["modules"] == []
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[PLAN, INVENTORY]),  # cancelling in the first reads its subscription
            subscription("sub_2", customer="cus_2", items=[PLAN]),  # buying in the second reads its own
            subscription("sub_2", customer="cus_2", items=[PLAN, INVENTORY]),  # and back with the module
        )
        stripe_double.answer("subscriptions.update", subscription(items=[PLAN]))
        stripe_double.answer("subscription_items.create", INVENTORY)

        committed(lambda: cancel(owner, first))
        committed(lambda: buy(owner, second))

        until = bought(first).valid_until
        assert until is not None and int(until.timestamp()) == MONTH_END
        assert photo(hub_double, first)["modules"] == [right("inventory", until)]
        assert photo(hub_double, second)["modules"] == [right("inventory")]
        assert stripe_double.last("subscription_items.create").params["subscription"] == "sub_2"
