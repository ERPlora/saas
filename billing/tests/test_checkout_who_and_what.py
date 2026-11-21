"""Who may buy for a business and what is on sale: only its owner, never Free, an upgrade-only plan only on top of a
paid one, the internal plan only for a business the staff marked, and always with the new owner's own payer
(``billing.checkout.start`` and ``billing.checkout.confirm``).
"""

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, NotFound, OperationError, PermissionDenied

from billing.models import CheckoutAttempt
from billing.schemas.checkout import CheckoutStartIn
from billing.tests.checkout_calls import NOW_TS, confirm, payer, paying, refused, session_params, start, transferred
from billing.tests.conftest import pay
from billing.tests.stripe_double import preview
from hubs.models import Hub, HubMember
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- Who may, and what -------------------------------------------------------------------------------


class TestWhoAndWhat:
    def test_only_the_owner_pays(self, shop, owner, make_user, stripe_double):
        admin = make_user("admin@example.com")
        add_member(shop, admin, HubMember.Role.ADMIN, invited_by=owner)

        with pytest.raises(PermissionDenied):
            start(admin, shop, plan="starter")

        assert stripe_double.calls == []

    def test_a_stranger_does_not_learn_the_business_exists(self, shop, make_user):
        with pytest.raises(NotFound):
            start(make_user("stranger@example.com"), shop, plan="starter")

    def test_a_deleted_business_buys_nothing(self, shop, owner):
        Hub.objects.filter(pk=shop.pk).update(
            status=Hub.Status.DELETING, deletion_requested_at=timezone.now()
        )

        refused("hubs.business_deleted", lambda: start(owner, shop, plan="starter"))

    def test_one_thing_at_a_time(self, shop):
        with pytest.raises(ValueError):
            CheckoutStartIn(hub_id=shop.id)
        with pytest.raises(ValueError):
            CheckoutStartIn(hub_id=shop.id, plan="starter", module="inventory")

    def test_free_is_not_sold(self, shop, owner):
        refused("billing.plan_is_free", lambda: start(owner, shop, plan="free"))

    def test_an_unknown_plan_is_an_invalid_field(self, shop, owner):
        with pytest.raises(InvalidPayload) as error:
            start(owner, shop, plan="platinum")

        assert set(error.value.fields) == {"plan"}
        # No form has a plan to mark: the reason itself is the notice.
        assert error.value.message == error.value.fields["plan"]

    def test_a_plan_without_its_stripe_price_is_not_on_sale(self, shop, owner):
        from hubs.models import Plan

        Plan.objects.filter(slug="starter").update(stripe_price_id_annual="")

        refused(
            "billing.not_on_sale",
            lambda: start(owner, shop, plan="starter", interval="year"),
        )

    def test_an_unknown_or_retired_module_is_an_invalid_field(
        self, shop, owner, inventory
    ):
        inventory.is_active = False
        inventory.save()

        for slug in ("nothing", "inventory"):
            with pytest.raises(InvalidPayload) as error:
                start(owner, shop, module=slug)
            assert set(error.value.fields) == {"module"}
            assert error.value.message == error.value.fields["module"]

    def test_a_module_the_business_has_is_not_sold_again(self, shop, owner, inventory):
        paid = pay(shop, modules=["inventory"])

        refused("billing.module_owned", lambda: start(owner, paid, module="inventory"))


class TestUpgradeOnlyPlans:
    """Pro, Enterprise and Max (``upgrade_only``) are an upgrade of a business that already pays;
    a Free business is refused them (the Store does not offer them, ``billing.store.catalog``)."""

    def test_a_free_business_is_refused_an_upgrade_only_plan(
        self, shop, owner, stripe_double
    ):
        error = refused(
            "billing.plan_upgrade_only", lambda: start(owner, shop, plan="pro")
        )

        assert error.status == 409
        assert not stripe_double.calls_to("checkout.sessions.create")

    def test_it_is_said_before_anything_about_its_price(self, shop, owner, stripe_double):
        """An upgrade without its Stripe price is still refused as an upgrade, not as «not on sale» (e2e found it)."""
        from hubs.models import Plan

        Plan.objects.filter(slug="pro").update(stripe_price_id="", stripe_price_id_annual="")

        refused("billing.plan_upgrade_only", lambda: start(owner, shop, plan="pro"))

    def test_it_says_so_in_spanish(self, shop, owner, stripe_double):
        from django.utils import translation

        with translation.override("es"), pytest.raises(OperationError) as error:
            start(owner, shop, plan="pro")

        assert error.value.message == (
            "Este plan es una mejora de un plan de pago: empieza por uno de los planes que se contratan al darse de alta."
        )

    def test_a_paying_business_previews_the_upgrade(
        self, shop, owner, stripe_double
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer("invoices.create_preview", preview())

        answer = start(owner, paid, plan="pro")

        assert answer["flow"] == "confirm"


class TestTheInternalPlan:
    """``payment-test`` (1 € + VAT: a real charge, a real invoice with its QR) is sold only to a business ERPlora's
    staff marked in the admin. Nobody else buys it, whatever they send: the refusal comes before Stripe."""

    def test_the_owner_of_a_marked_business_buys_it_in_the_embedded_checkout(self, marked, owner, stripe_double):
        answer = start(owner, marked, plan="payment-test")

        params = session_params(stripe_double)
        assert answer["flow"] == "checkout"
        assert [line["price"] for line in params["line_items"]] == ["price_payment-test_month"]
        assert params["metadata"]["plan"] == "payment-test"
        assert CheckoutAttempt.objects.get(hub=marked).plan_slug == "payment-test"

    def test_a_business_nobody_marked_is_refused_before_stripe(self, shop, owner, stripe_double):
        from hubs.models import Plan

        Plan.objects.filter(slug="payment-test").update(stripe_price_id="price_payment-test_month")

        with pytest.raises(InvalidPayload) as error:
            start(owner, shop, plan="payment-test")

        assert set(error.value.fields) == {"plan"}
        assert stripe_double.calls == []

    def test_the_mark_is_of_the_business_not_of_its_owner(self, marked, owner, stripe_double):
        from hubs.tests.conftest import create_business

        pay(marked)
        other = payer(
            create_business(owner, name="Otro Bar"),
            billing_name="Otro Bar SL",
            billing_address="Calle Mayor 2",
            billing_city="Madrid",
            billing_postal_code="28001",
        )

        with pytest.raises(InvalidPayload):
            start(owner, other, plan="payment-test")
        assert stripe_double.calls == []

    def test_a_paying_business_nobody_marked_cannot_move_to_it(self, shop, owner, stripe_double):
        from hubs.models import Plan

        Plan.objects.filter(slug="payment-test").update(stripe_price_id="price_payment-test_month")
        paid = pay(shop)

        with pytest.raises(InvalidPayload):
            start(owner, paid, plan="payment-test")
        assert stripe_double.calls == []


# --- Who pays is the payer, not the role ----------------------------------------------------------------


class TestThePayerPays:
    def test_a_new_owner_does_not_buy_with_the_previous_owners_payer(self, shop, owner, make_user, stripe_double):
        new_owner = transferred(shop, owner, make_user)

        error = refused("billing.payer_required", lambda: start(new_owner, shop, plan="starter"))

        assert error.status == 409
        assert stripe_double.calls == []

    def test_once_the_new_owner_says_who_pays_a_free_business_is_bought(self, shop, owner, make_user, stripe_double):
        from hubs.services import billing_profiles
        from hubs.schemas.payers import BillingProfileIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        new_owner = transferred(shop, owner, make_user)
        billing_profiles.billing_profile_update(
            hub_ctx(new_owner),
            BillingProfileIn(hub_id=shop.id, billing_name="Nuevo SL", billing_country="ES", billing_postal_code="28002"),
        )

        assert start(new_owner, Hub.objects.get(pk=shop.pk), plan="starter")["flow"] == "checkout"
        assert stripe_double.last("customers.create").params["name"] == "Nuevo SL"

    def test_a_subscription_still_paid_by_the_previous_owner_is_not_touched(self, shop, owner, make_user,
                                                                           inventory, stripe_double):
        from hubs.services import billing_profiles
        from hubs.schemas.payers import BillingProfileIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        paid = pay(shop)
        new_owner = transferred(paid, owner, make_user)
        billing_profiles.billing_profile_update(
            hub_ctx(new_owner),
            BillingProfileIn(hub_id=paid.id, billing_name="Nuevo SL", billing_country="ES", billing_postal_code="28002"),
        )

        refused("billing.payer_required", lambda: start(new_owner, paid, module="inventory"))
        refused("billing.payer_required", lambda: confirm(new_owner, paid, module="inventory", proration_date=NOW_TS))

        assert stripe_double.calls == []
