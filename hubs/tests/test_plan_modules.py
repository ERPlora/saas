"""The modules a plan includes are rights of the business too: ``SubscriptionItem(source="plan")`` (PLAN-SAAS
§2.2 and §2.6, ADR-0474).

A plan includes every paid module (``apps.Module``) whose ``tier`` its ``included_level`` reaches, in the order
free < basic < pro < enterprise. Those rows are recomputed whenever the plan of the business may change
(``hubs.subscription.apply``, the sign-up, the restore, the end of a trial), so the snapshot's ``modules[]``
carries ``{id, source: "plan", valid_until}`` for the included ones next to ``source: "purchase"`` for the
bought ones. The rights follow the plan the business has now (``Subscription.effective_plan``): during the
sign-up's trial of Starter, what only the trial includes lasts until ``trial_end``. A module Stripe bills
stays bought (it has a Stripe item to cancel), even when the plan includes it too; when Stripe stops billing
it, the plan's right takes over at once.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.models import Module
from hubs import queries, services
from hubs.models import Hub, Subscription, SubscriptionItem
from hubs.schemas import ModuleRightIn, SubscriptionApplyIn
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db

#: One paid module per tier.
TIERS = {"loyalty": "free", "inventory": "basic", "kitchen": "pro", "franchise": "enterprise"}


@pytest.fixture
def catalog(db):
    return {slug: Module.objects.create(slug=slug, tier=tier) for slug, tier in TIERS.items()}


def apply(hub, **fields):
    return services.subscription_apply(services.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, **fields))


NOW = timezone.now().replace(microsecond=0)


def paid(plan, **extra):
    now = NOW
    return {
        "plan": plan,
        "billing_interval": "month",
        "status": "active",
        "stripe_customer_id": "cus_1",
        "stripe_subscription_id": "sub_1",
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "trial_start": None,
        "trial_end": None,
        **extra,
    }


def rights(hub):
    """``{slug: (source, valid_until)}`` of the business's rows."""
    return {
        item.module_slug: (item.source, item.valid_until)
        for item in SubscriptionItem.objects.filter(subscription__hub=hub)
    }


def plan_rights(hub):
    return sorted(slug for slug, (source, _) in rights(hub).items() if source == "plan")


@pytest.mark.parametrize(
    ("plan", "included"),
    [
        ("starter", ["inventory", "loyalty"]),
        ("standard", ["inventory", "loyalty"]),
        ("pro", ["inventory", "kitchen", "loyalty"]),
        ("enterprise", ["franchise", "inventory", "kitchen", "loyalty"]),
        ("max", ["franchise", "inventory", "kitchen", "loyalty"]),
    ],
)
def test_a_paid_plan_includes_every_module_its_level_reaches(business, catalog, plan, included):
    apply(business, **paid(plan))

    assert plan_rights(business) == included
    assert queries.hub_snapshot(business.id)["modules"] == [
        {"id": slug, "source": "plan", "valid_until": None} for slug in included
    ]


def test_free_includes_only_the_free_tier(business, catalog):
    Subscription.objects.filter(hub=business).update(trial_plan=None, trial_end=None)

    apply(business, plan="free")

    assert rights(business) == {"loyalty": ("plan", None)}


def test_a_bought_module_stays_bought_next_to_the_included_ones(business, catalog):
    apply(business, **paid("starter"), modules=[ModuleRightIn(module_slug="kitchen", stripe_item_id="si_k")])

    assert rights(business) == {
        "inventory": ("plan", None),
        "kitchen": ("purchase", None),
        "loyalty": ("plan", None),
    }
    assert [(m["id"], m["source"]) for m in queries.hub_snapshot(business.id)["modules"]] == [
        ("inventory", "plan"),
        ("kitchen", "purchase"),
        ("loyalty", "plan"),
    ]


class TestAPlanChange:
    def test_an_upgrade_adds_what_the_new_level_reaches_and_tells_the_hub(
        self, business, catalog, hub_double, django_capture_on_commit_callbacks
    ):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call="")
        apply(business, **paid("starter"))
        version = Hub.objects.get(pk=business.pk).state_version

        with django_capture_on_commit_callbacks(execute=True):
            apply(business, plan="pro")

        assert plan_rights(business) == ["inventory", "kitchen", "loyalty"]
        snapshot = hub_double.calls_to("PUT", "/state")[-1].body
        assert snapshot["version"] == version + 1
        assert [m["id"] for m in snapshot["modules"]] == ["inventory", "kitchen", "loyalty"]

    def test_a_downgrade_takes_away_what_the_old_level_reached(self, business, catalog):
        apply(business, **paid("enterprise"))

        apply(business, plan="starter")

        assert plan_rights(business) == ["inventory", "loyalty"]

    def test_the_end_of_the_subscription_leaves_the_free_tier(self, business, catalog):
        apply(business, **paid("pro"))

        apply(
            business,
            plan="free",
            status="active",
            stripe_subscription_id="",
            current_period_start=None,
            current_period_end=None,
            modules=[],
        )

        assert plan_rights(business) == ["loyalty"]

    def test_the_same_plan_again_changes_nothing(self, business, catalog):
        apply(business, **paid("pro"))
        version = Hub.objects.get(pk=business.pk).state_version

        result = apply(business, **paid("pro"))

        assert result.changed is False
        assert Hub.objects.get(pk=business.pk).state_version == version


class TestBoughtAndIncluded:
    def test_a_module_stripe_still_bills_stays_bought_after_an_upgrade_includes_it(self, business, catalog):
        """It has a Stripe item: cancelling it (billing) must still find it."""
        kitchen = ModuleRightIn(module_slug="kitchen", stripe_item_id="si_k")
        apply(business, **paid("starter"), modules=[kitchen])

        apply(business, plan="pro", modules=[kitchen])

        assert rights(business)["kitchen"] == ("purchase", None)
        assert SubscriptionItem.objects.get(subscription__hub=business, module_slug="kitchen").stripe_item_id == "si_k"

    def test_when_stripe_stops_billing_it_the_plan_takes_over_at_once(self, business, catalog):
        apply(business, **paid("pro"), modules=[ModuleRightIn(module_slug="kitchen", stripe_item_id="si_k")])

        apply(business, modules=[])

        assert rights(business)["kitchen"] == ("plan", None)

    def test_a_cancelled_purchase_the_plan_includes_yields_to_the_plan_at_once(self, business, catalog):
        """Cancelled after an upgrade that includes it: the right never lapses at the end of its period."""
        apply(business, **paid("pro"), modules=[ModuleRightIn(module_slug="kitchen", stripe_item_id="si_k")])

        apply(business, modules=[ModuleRightIn(module_slug="kitchen", valid_until=NOW + timedelta(days=30))])

        assert rights(business)["kitchen"] == ("plan", None)

    def test_a_module_stripe_bills_takes_over_the_plans_row(self, business, catalog):
        apply(business, **paid("starter"))

        apply(business, modules=[ModuleRightIn(module_slug="inventory", stripe_item_id="si_inv")])

        item = SubscriptionItem.objects.get(subscription__hub=business, module_slug="inventory")
        assert (item.source, item.stripe_item_id) == ("purchase", "si_inv")


class TestTheSignUpTrial:
    def test_the_sign_up_writes_them(self, catalog, owner, plans):
        business = create_business(owner, name="Bar Nuevo")
        trial_end = Subscription.objects.get(hub=business).trial_end

        assert rights(business) == {"inventory": ("plan", trial_end), "loyalty": ("plan", None)}
        assert [(m["id"], m["valid_until"]) for m in queries.hub_snapshot(business.id)["modules"]] == [
            ("inventory", trial_end.isoformat()),
            ("loyalty", None),
        ]

    def test_paying_the_plan_makes_its_modules_open_ended(self, business, catalog):
        services.sync_plan_modules(Subscription.objects.get(hub=business))

        apply(business, **paid("starter"))

        assert rights(business) == {"inventory": ("plan", None), "loyalty": ("plan", None)}

    def test_the_end_of_the_trial_takes_them_away(self, business, catalog, offline_hub):
        services.sync_plan_modules(Subscription.objects.get(hub=business))
        Subscription.objects.filter(hub=business).update(trial_end=timezone.now() - timedelta(seconds=1))
        version = Hub.objects.get(pk=business.pk).state_version

        counts = services.reconcile()

        assert counts["trials_ended"] == 1
        assert rights(business) == {"loyalty": ("plan", None)}
        assert Hub.objects.get(pk=business.pk).state_version > version
