"""What the Store sells a business and what that business already has: ``billing.store.catalog`` (lot L2-D).

The Store (``billing/frontend/pages/StorePage.vue``, mockups ``store.html``) paints the plans of
``hubs.plan.list`` and the modules of ``apps.app.list`` (name, summary, icon) joined by slug with this
query: every paid module on sale (``apps.Module``: net prices in cents, as Stripe charges them) and, for
the business chosen above, its plan and billing, whether Stripe already bills it (a change is confirmed
with its proration; otherwise the Embedded Checkout) and which modules it has, bought or included in its
plan, cancelled ones with the date they end. Only the owner buys for a business (round 17 §2.7), so only
the owner reads it. A read: nothing here asks Stripe.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import NotFound, OperationError, PermissionDenied

from apps.icons import FALLBACK_ICON_SVG
from apps.tests.factories import CUBE_SVG, make_app
from billing import queries
from billing.schemas import StoreCatalogIn
from billing.tests.conftest import ctx_for, pay
from hubs.models import HubMember, SubscriptionItem
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def catalog(user, hub) -> dict:
    return queries.store_catalog(
        ctx_for(user), StoreCatalogIn(hub_id=hub.id)
    ).model_dump(mode="json")


@pytest.fixture
def reports(db):
    """A second paid module on sale, monthly only (no annual price)."""
    from apps.models import Module

    return Module.objects.create(
        slug="reports",
        tier=Module.Tier.BASIC,
        price_monthly_cents=700,
        price_annual_cents=0,
        stripe_price_id_monthly="price_reports_month",
    )


class TestWhatIsOnSale:
    def test_a_free_business_sees_every_module_on_sale_with_its_net_prices_in_cents(
        self, shop, owner, inventory, reports
    ):
        answer = catalog(owner, shop)

        assert answer["hub_id"] == str(shop.id)
        assert answer["modules"] == [
            {
                "slug": "inventory",
                "tier": "enterprise",
                "price_monthly_cents": 1000,
                "price_annual_cents": 10000,
                "owned": False,
                "source": None,
                "valid_until": None,
                "on_sale": True,
                "name": "inventory",
                "summary": "",
                "icon_svg": FALLBACK_ICON_SVG,
            },
            {
                "slug": "reports",
                "tier": "basic",
                "price_monthly_cents": 700,
                "price_annual_cents": 0,
                "owned": False,
                "source": None,
                "valid_until": None,
                "on_sale": True,
                "name": "reports",
                "summary": "",
                "icon_svg": FALLBACK_ICON_SVG,
            },
        ]

    def test_a_module_off_sale_is_not_sold(self, shop, owner, inventory, reports):
        reports.is_active = False
        reports.save()

        assert [module["slug"] for module in catalog(owner, shop)["modules"]] == [
            "inventory"
        ]

    def test_a_module_off_sale_the_business_still_pays_is_listed_to_cancel_it(
        self, shop, owner, inventory, reports
    ):
        """BILLING-G61, saas#2589: taking a module off sale stops new purchases, never the charge of the
        businesses that have it, so the Store still shows it to them (not on sale) to cancel it."""
        paid = pay(shop, modules=["reports"])
        reports.is_active = False
        reports.save()

        modules = {module["slug"]: module for module in catalog(owner, paid)["modules"]}

        assert (modules["reports"]["on_sale"], modules["reports"]["owned"]) == (False, True)
        assert modules["reports"]["source"] == "purchase"
        assert modules["inventory"]["on_sale"] is True

    def test_each_module_says_its_apps_name_summary_and_icon_in_the_persons_language(
        self, shop, owner, inventory
    ):
        """BILLING-G61, saas#2589: the catalog's own texts, also for an app the Hub retired from the store
        (not listed), whose module a business may still have."""
        make_app("inventory", name_es="Inventario", summary_es="El stock al día.", premium=True, listed=False)

        [module] = queries.store_catalog(
            ctx_for(owner, language="es"), StoreCatalogIn(hub_id=shop.id)
        ).model_dump(mode="json")["modules"]

        assert (module["name"], module["summary"]) == ("Inventario", "El stock al día.")
        assert module["icon_svg"] == CUBE_SVG

    def test_a_free_business_is_not_billed_by_stripe_yet(self, shop, owner, inventory):
        subscription = catalog(owner, shop)["subscription"]

        assert subscription["plan"] == "free"
        assert subscription["billing_interval"] == "month"
        assert subscription["paying"] is False
        assert subscription["cancel_at_period_end"] is False
        # No trial since 2026-10-15 (the Free plan is the way in).
        assert (subscription["trial_plan"], subscription["trial_end"]) == (None, None)


class TestWhichPlansAreOffered:
    """Audit 2 S-03 (Ioan's decision through the coordinator, 2026-10-14): a business Stripe does not bill
    (Free) is offered the plans sold at sign-up only; the ``upgrade_only`` ones (Pro, Enterprise, Max) are
    an upgrade of a business that already pays (the catalogue, ``hubs/0013``)."""

    def test_a_free_business_is_offered_only_the_plans_sold_at_sign_up(self, shop, owner):
        assert catalog(owner, shop)["offered_plans"] == ["starter", "standard"]

    def test_a_paying_business_is_offered_the_upgrades_too(self, shop, owner):
        paid = pay(shop)

        assert catalog(owner, paid)["offered_plans"] == [
            "starter",
            "standard",
            "pro",
            "enterprise",
            "max",
        ]

    def test_a_business_whose_stripe_subscription_ended_is_back_to_the_sign_up_plans(
        self, shop, owner
    ):
        ended = pay(shop, status="canceled")

        assert catalog(owner, ended)["offered_plans"] == ["starter", "standard"]

    def test_a_plan_off_sale_or_internal_is_never_offered(self, shop, owner):
        from hubs.models import Plan

        Plan.objects.filter(slug="standard").update(is_active=False)
        paid = pay(shop)

        offered = catalog(owner, paid)["offered_plans"]
        assert "standard" not in offered
        assert "payment-test" not in offered
        assert "free" not in offered


class TestWhatTheBusinessHas:
    def test_a_paying_business_says_its_plan_its_billing_and_its_renewal(
        self, shop, owner, inventory
    ):
        paid = pay(shop, plan="starter", interval="year")

        subscription = catalog(owner, paid)["subscription"]

        assert subscription["plan"] == "starter"
        assert subscription["billing_interval"] == "year"
        assert subscription["paying"] is True
        assert subscription["status"] == "active"
        assert subscription["current_period_end"] is not None

    def test_a_bought_module_is_owned(self, shop, owner, inventory):
        paid = pay(shop, modules=["inventory"])

        [module] = catalog(owner, paid)["modules"]

        assert (module["owned"], module["source"], module["valid_until"]) == (
            True,
            "purchase",
            None,
        )

    def test_a_cancelled_module_is_still_owned_until_it_ends(
        self, shop, owner, inventory
    ):
        paid = pay(shop, modules=["inventory"])
        until = timezone.now() + timedelta(days=12)
        SubscriptionItem.objects.filter(
            subscription__hub=paid, module_slug="inventory"
        ).update(valid_until=until)

        [module] = catalog(owner, paid)["modules"]

        assert module["owned"] is True
        assert module["valid_until"] == until.isoformat().replace("+00:00", "Z")

    def test_a_module_whose_period_ended_is_for_sale_again(
        self, shop, owner, inventory
    ):
        paid = pay(shop, modules=["inventory"])
        SubscriptionItem.objects.filter(
            subscription__hub=paid, module_slug="inventory"
        ).update(valid_until=timezone.now() - timedelta(minutes=1))

        [module] = catalog(owner, paid)["modules"]

        assert (module["owned"], module["source"], module["valid_until"]) == (
            False,
            None,
            None,
        )

    def test_a_module_the_plan_includes_is_owned_through_the_plan(
        self, shop, owner, inventory
    ):
        paid = pay(shop)
        SubscriptionItem.objects.create(
            subscription=paid.subscription,
            module_slug="inventory",
            source=SubscriptionItem.Source.PLAN,
        )

        [module] = catalog(owner, paid)["modules"]

        assert (module["owned"], module["source"]) == (True, "plan")

    def test_a_cancelled_plan_says_so(self, shop, owner, inventory):
        paid = pay(shop, cancel_at_period_end=True)

        assert catalog(owner, paid)["subscription"]["cancel_at_period_end"] is True


class TestOnlyTheOwnerBuys:
    def test_an_admin_is_refused(self, shop, make_user, inventory):
        admin = make_user("admin@example.com")
        add_member(shop, admin, HubMember.Role.ADMIN)

        with pytest.raises(PermissionDenied):
            catalog(admin, shop)

    def test_a_stranger_learns_nothing(self, shop, make_user, inventory):
        with pytest.raises(NotFound):
            catalog(make_user("stranger@example.com"), shop)

    def test_a_visitor_reads_nothing(self, shop, inventory):
        # Without a session there is no permission: the operation's gate refuses before it reads (the
        # route answers the 401 envelope, TestTheRoute).
        with pytest.raises(PermissionDenied):
            catalog(None, shop)

    def test_a_deleted_business_buys_nothing(self, shop, owner, inventory):
        shop.status = shop.Status.DELETING
        shop.save(update_fields=["status"])

        with pytest.raises(OperationError) as error:
            catalog(owner, shop)
        assert error.value.code == "hubs.business_deleted"


class TestTheRoute:
    def test_the_owner_reads_it_at_its_route(self, client, shop, owner, inventory):
        client.force_login(owner)

        response = client.get(f"/api/billing/store?hub_id={shop.id}", HTTP_HOST=HOST)

        assert response.status_code == 200, response.content
        assert [module["slug"] for module in response.json()["modules"]] == [
            "inventory"
        ]

    def test_a_visitor_gets_the_401_envelope(self, client, shop):
        response = client.get(f"/api/billing/store?hub_id={shop.id}", HTTP_HOST=HOST)

        assert response.status_code == 401
