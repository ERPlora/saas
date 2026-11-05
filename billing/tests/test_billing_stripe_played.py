"""BILLING-F11 and BILLING-F14 · The Stripe of ``tests/e2e/panel/billing-downgrade.spec.ts``
(``tests/e2e/panel/billing_stripe_played.py``), kept honest here because the CI does not run the e2e: the panel's real
routes answer, with only Stripe doubled, and nothing of the double stays behind.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from apps.models import Module
from billing import stripe_service
from billing.models import PlanChangeSchedule, WebhookEvent
from billing.tests.conftest import pay
from hubs.models import Plan, Subscription, SubscriptionItem

SCRIPT = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel" / "billing_stripe_played.py"
SUB, CUSTOMER = "sub_e2e_billing_bakery", "cus_e2e_billing"

pytestmark = pytest.mark.django_db


def _load():
    spec = importlib.util.spec_from_file_location("billing_stripe_played", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def played(monkeypatch, hub_double):
    """The script as a module, its Hub the tests' double; pytest set Django up already."""
    module = _load()
    monkeypatch.setattr(module, "setup_django", lambda: None)
    return module


@pytest.fixture
def standard(shop):
    """On Standard as ``billing_seed.py`` leaves it, Plan rows without a Stripe price as the e2e's database has them."""
    paid = pay(shop, plan="standard", sub_id=SUB, customer=CUSTOMER)
    Plan.objects.update(stripe_price_id="", stripe_price_id_annual="")
    return paid


def call(played, hub_double, owner, operation, body):
    return played.api(owner.email, f"/api/billing/{operation}", body, hub_double.url)


def downgrade_of(paid) -> dict:
    return {"hub_id": str(paid.id), "plan": "starter", "interval": "month"}


class TestTheRoutes:
    def test_the_preview_of_a_downgrade_charges_nothing_today(self, played, hub_double, owner, standard):
        answer = call(played, hub_double, owner, "checkout/start", downgrade_of(standard))

        assert answer["status"] == 200, answer
        held = Subscription.objects.get(hub=standard)
        assert answer["body"]["flow"] == "confirm"
        assert answer["body"]["preview"]["amount_due_cents"] == 0
        assert answer["body"]["preview"]["charge_starts_at"] == int(held.current_period_end.timestamp())

    def test_the_change_waits_as_the_server_writes_it(self, played, hub_double, owner, standard):
        preview = call(played, hub_double, owner, "checkout/start", downgrade_of(standard))["body"]["preview"]

        answer = call(
            played, hub_double, owner, "plan/change", downgrade_of(standard) | {"proration_date": preview["proration_date"]}
        )

        assert answer["status"] == 200, answer
        assert (answer["body"]["plan"], answer["body"]["scheduled_change"]["plan"]) == ("standard", "starter")
        assert PlanChangeSchedule.objects.get(hub=standard).plan_slug == "starter"
        assert Subscription.objects.get(hub=standard).plan.slug == "standard"

    def test_keeping_the_plan_undoes_it(self, played, hub_double, owner, standard):
        preview = call(played, hub_double, owner, "checkout/start", downgrade_of(standard))["body"]["preview"]
        call(played, hub_double, owner, "plan/change", downgrade_of(standard) | {"proration_date": preview["proration_date"]})

        answer = call(played, hub_double, owner, "plan/keep", {"hub_id": str(standard.id)})

        assert answer["status"] == 200, answer
        assert answer["body"]["scheduled_change"] is None
        assert not PlanChangeSchedule.objects.exists()

    def test_a_refusal_answers_as_the_route_does(self, played, hub_double, standard):
        stranger = get_user_model().objects.create_user(email="stranger@example.com", password=None)

        answer = call(played, hub_double, stranger, "plan/keep", {"hub_id": str(standard.id)})

        assert answer["status"] >= 400, answer
        assert answer["body"]["error"]["code"]

    def test_nothing_of_the_double_stays_behind(self, played, hub_double, owner, standard):
        client = stripe_service.client

        call(played, hub_double, owner, "checkout/start", downgrade_of(standard))

        assert stripe_service.client is client
        assert set(Plan.objects.values_list("stripe_price_id", "stripe_price_id_annual")) == {("", "")}


class TestTheArrival:
    @pytest.fixture
    def waiting(self, played, hub_double, owner, standard):
        preview = call(played, hub_double, owner, "checkout/start", downgrade_of(standard))["body"]["preview"]
        call(played, hub_double, owner, "plan/change", downgrade_of(standard) | {"proration_date": preview["proration_date"]})
        return standard

    def test_the_new_phase_applies_it_through_the_signed_webhook(self, played, hub_double, waiting):
        played.arrive(str(waiting.id), hub_double.url)

        assert Subscription.objects.get(hub=waiting).plan.slug == "starter"
        assert not PlanChangeSchedule.objects.exists()
        assert not WebhookEvent.objects.exists()

    def test_a_bought_module_stays_bought(self, played, hub_double, owner, standard):
        Module.objects.create(
            slug="e2e_bought", tier=Module.Tier.ENTERPRISE, price_monthly_cents=900, price_annual_cents=9000,
            stripe_price_id_monthly="price_e2e_bought_month", stripe_price_id_annual="price_e2e_bought_year",
        )
        SubscriptionItem.objects.create(
            subscription=Subscription.objects.get(hub=standard), module_slug="e2e_bought",
            source=SubscriptionItem.Source.PURCHASE, stripe_item_id="si_e2e_bought",
        )
        preview = call(played, hub_double, owner, "checkout/start", downgrade_of(standard))["body"]["preview"]
        call(played, hub_double, owner, "plan/change", downgrade_of(standard) | {"proration_date": preview["proration_date"]})

        played.arrive(str(standard.id), hub_double.url)

        kept = SubscriptionItem.objects.get(subscription__hub=standard, module_slug="e2e_bought")
        assert (kept.source, kept.stripe_item_id) == (SubscriptionItem.Source.PURCHASE, "si_e2e_bought")


def test_it_refuses_to_run_without_debug(played, settings):
    settings.DEBUG = False

    with pytest.raises(SystemExit):
        played.main(["arrive", "any", "http://127.0.0.1:9"])
