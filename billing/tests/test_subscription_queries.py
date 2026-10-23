"""Billing → Subscriptions and Billing → Payment details (lot L3-C; round 17 §2.7, mockups ``billing.html``).

Subscriptions: one row per business of the account that Stripe bills (a paid plan or paid modules), for its
owner and for its payer: the plan and its modules at their net price, the next invoice with VAT (priced by
the payer's place, as the checkout prices it; none while the plan is ending), its status and the row's
actions, computed here: «Change plan» (the fixed one), «Keep the plan» once cancelled, «View the invoice»
with one not collected; «Cancel plan» and «View invoices». Changing, cancelling and keeping need the owner
who pays (``billing.plan.*``); anyone else sees the row to consult it.

Payment details: the card of each payer of the account (one Stripe customer per business's payer), read from
Stripe (the subscription's card, else the customer's default) and kept 10 minutes; ``customer.updated``
forgets it. Stripe away is ``unavailable``, never an invented card. Ported in spirit from ERPlora/saas
``test_api.TestSubscriptionAPI`` (the list is the account's, another account's is not there); the old module
subscriptions and purchases are gone (one subscription per business, PLAN-SAAS §4).
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from billing import queries
from billing.models import Invoice, PaymentFailure
from billing.schemas import PaymentMethodIn, SubscriptionListIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import connection_error, event, signed
from hubs.models import BillingProfile, HubMember, Subscription
from hubs.tests.conftest import add_member, create_business

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _forget_cards():
    cache.clear()
    yield
    cache.clear()


def subscriptions(user, language="en") -> list[dict]:
    return queries.subscription_list(
        ctx_for(user, language), SubscriptionListIn()
    ).model_dump(mode="json")["rows"]


class TestTheApiOfSubscriptions:
    """BILLING-G02 (the old DRF list «filtered by status» and «the detail of one»): the same rows, filtered by
    business (one business's subscription) and by status, and open to an integration's key with ``billing.read``
    as the invoices are."""

    def test_one_business_s_subscription(self, owner, shop, plans):
        pay(shop)
        other = pay(create_business(owner, name="Café Central"), sub_id="sub_2", customer="cus_2")

        rows = queries.subscription_list(ctx_for(owner), SubscriptionListIn(hub_id=other.id)).model_dump(mode="json")

        assert [row["business"]["name"] for row in rows["rows"]] == ["Café Central"]
        assert rows["total"] == 1

    def test_by_status(self, owner, shop, plans):
        pay(shop)
        pay(create_business(owner, name="Café Central"), sub_id="sub_2", customer="cus_2", status="past_due")

        rows = queries.subscription_list(ctx_for(owner), SubscriptionListIn(status="past_due")).model_dump(mode="json")

        assert [row["business"]["name"] for row in rows["rows"]] == ["Café Central"]

    def test_another_account_s_business_is_never_there(self, shop, make_user):
        pay(shop)
        stranger = make_user("stranger@example.com")

        rows = queries.subscription_list(ctx_for(stranger), SubscriptionListIn(hub_id=shop.id)).model_dump(mode="json")

        assert rows["rows"] == []

    def test_an_unknown_status_is_refused_at_the_route(self, client, owner, shop):
        client.force_login(owner)

        response = client.get("/api/billing/subscriptions?status=nonsense", HTTP_HOST="localhost:8001")

        assert response.status_code == 422

    def key(self, user, *scopes):
        from accounts.models import ApiKey

        secret, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=user, name="gestoría", prefix=prefix, key_hash=key_hash, scopes=list(scopes))
        return secret

    def by_key(self, secret, **params):
        from django.test import Client

        return Client(enforce_csrf_checks=True).get(
            "/api/billing/subscriptions", params, HTTP_HOST="localhost:8001", HTTP_AUTHORIZATION=f"Bearer {secret}"
        )

    def test_an_integration_reads_it_with_its_key(self, owner, shop, plans, make_user):
        pay(shop)
        pay(create_business(make_user("stranger@example.com"), name="Ajeno"), sub_id="sub_2", customer="cus_2")

        response = self.by_key(self.key(owner, "billing.read"), hub_id=str(shop.id))

        assert response.status_code == 200
        assert [row["business"]["name"] for row in response.json()["rows"]] == [shop.name]

    def test_a_key_without_billing_read_reads_nothing(self, owner, shop):
        pay(shop)

        response = self.by_key(self.key(owner, "hubs.read"))

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_missing_scope")


class TestWhichRows:
    def test_a_visitor_sees_nothing(self):
        from django.test import Client

        response = Client().get("/api/billing/subscriptions", HTTP_HOST="localhost:8001")

        assert response.status_code == 401

    def test_only_the_businesses_stripe_bills(self, owner, shop, plans):
        pay(shop)
        create_business(owner, name="Gratis")

        assert [row["business"]["name"] for row in subscriptions(owner)] == [
            "Panadería López"
        ]

    def test_the_payer_who_no_longer_owns_it_still_sees_it(
        self, owner, shop, make_user
    ):
        pay(shop)
        new_owner = make_user("new@example.com")
        HubMember.objects.filter(hub=shop, user=owner).update(role=HubMember.Role.ADMIN)
        add_member(shop, new_owner, HubMember.Role.OWNER)

        assert len(subscriptions(owner)) == 1
        assert len(subscriptions(new_owner)) == 1

    def test_a_member_who_neither_owns_nor_pays_does_not(self, shop, make_user):
        pay(shop)
        admin = make_user("admin@example.com")
        add_member(shop, admin, HubMember.Role.ADMIN)

        assert subscriptions(admin) == []

    def test_an_ended_subscription_is_not_a_row(self, owner, shop):
        pay(shop)
        Subscription.objects.filter(hub=shop).update(
            stripe_subscription_id="", status="canceled"
        )

        assert subscriptions(owner) == []


class TestTheRow:
    def test_the_plan_its_modules_and_the_next_invoice_with_vat(
        self, owner, shop, inventory
    ):
        pay(shop, modules=["inventory"])

        [row] = subscriptions(owner)

        assert row["plan"] == {
            "slug": "starter",
            "name": "Starter",
            "interval": "month",
            "price_cents": 2999,
        }
        assert row["modules"] == [
            {
                "slug": "inventory",
                "interval": "month",
                "price_cents": 1000,
                "source": "purchase",
                "valid_until": None,
            }
        ]
        period_end = Subscription.objects.get(hub=shop).current_period_end
        # (29.99 + 10.00) + 21 % = 48.39
        assert row["next_invoice"]["total_cents"] == 4839
        assert row["next_invoice"]["date"].startswith(period_end.date().isoformat())
        assert (row["status"], row["cancelling"], row["unpaid_invoice_id"]) == (
            "active",
            False,
            None,
        )

    def test_a_cancelled_module_ends_and_is_not_billed_again(
        self, owner, shop, inventory
    ):
        pay(shop, modules=["inventory"])
        until = timezone.now() + timedelta(days=20)
        shop.subscription.items.filter(module_slug="inventory").update(
            valid_until=until
        )

        [row] = subscriptions(owner)

        assert row["modules"][0]["valid_until"] is not None
        assert row["next_invoice"]["total_cents"] == 3629

    def test_a_module_whose_cancellation_ended_is_not_listed(
        self, owner, shop, inventory
    ):
        # BILLING-G67: once its paid period is over the module is gone from the business, as in the
        # snapshot the Hub gets and in the store, which sells it again.
        pay(shop, modules=["inventory"])
        shop.subscription.items.filter(module_slug="inventory").update(
            valid_until=timezone.now() - timedelta(days=1)
        )

        [row] = subscriptions(owner)

        assert row["modules"] == []
        assert row["next_invoice"]["total_cents"] == 3629

    def test_an_annual_plan_is_priced_by_the_year(self, owner, shop):
        pay(shop, interval="year")

        [row] = subscriptions(owner)

        assert (row["plan"]["interval"], row["plan"]["price_cents"]) == ("year", 29990)

    def test_without_the_payers_place_the_next_total_is_unknown(self, owner, shop):
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            billing_country="", billing_postal_code=""
        )

        assert subscriptions(owner)[0]["next_invoice"]["total_cents"] is None

    def test_the_plan_name_speaks_the_accounts_language(self, owner, shop):
        pay(shop, plan="standard")

        [row] = subscriptions(owner, "es")

        assert row["plan"]["name"] == shop.subscription.plan.translated("name", "es")


class TestTheActions:
    def actions(self, owner):
        [row] = subscriptions(owner)
        return row["actions"], row["can"]

    def test_a_running_plan_is_changed_or_cancelled(self, owner, shop):
        pay(shop)

        actions, can = self.actions(owner)

        assert actions == ["change_plan", "cancel_plan", "view_invoices"]
        assert can == {
            "take_over": False,
            "change_plan": True,
            "cancel_plan": True,
            "keep_plan": False,
            "view_invoice": False,
            "view_invoices": True,
        }

    def test_a_cancelled_plan_is_kept_and_has_no_next_invoice(self, owner, shop):
        pay(shop, cancel_at_period_end=True)

        [row] = subscriptions(owner)

        assert row["actions"] == ["keep_plan", "change_plan", "view_invoices"]
        assert (row["cancelling"], row["next_invoice"]) == (True, None)
        assert row["ends_at"] is not None

    def test_with_an_invoice_not_collected_it_is_viewed_first(self, owner, shop):
        pay(shop, status="past_due")
        unpaid = Invoice.objects.create(
            stripe_invoice_id="in_open",
            hub=shop,
            payer_account=owner,
            payment_status="open",
            net_cents=2999,
            tax_cents=630,
            total_cents=3629,
        )

        [row] = subscriptions(owner)

        assert row["actions"][0] == "view_invoice"
        assert row["unpaid_invoice_id"] == str(unpaid.id)
        assert row["status_label"] == "Payment pending"

    def test_an_owner_who_does_not_pay_only_consults_or_keeps_it_with_their_card(self, owner, shop, make_user):
        """The plan on another account's card is neither changed nor cancelled by the owner: the owner keeps it
        with their own card first (HUBS-F28, ``billing.plan.take_over``)."""
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            owner=make_user("payer@example.com")
        )

        actions, can = self.actions(owner)

        assert actions == ["take_over", "view_invoices"]
        assert not (can["change_plan"] or can["cancel_plan"] or can["keep_plan"])


class TestThePaymentMethod:
    def methods(self, user, **data):
        return queries.payment_method_get(
            ctx_for(user), PaymentMethodIn(**data)
        ).model_dump(mode="json")["methods"]

    def card(self, stripe_double, last4="4242"):
        stripe_double.answer(
            "subscriptions.retrieve",
            {
                "id": "sub_1",
                "object": "subscription",
                "default_payment_method": {
                    "id": "pm_1",
                    "object": "payment_method",
                    "card": {
                        "brand": "visa",
                        "last4": last4,
                        "exp_month": 8,
                        "exp_year": 2028,
                    },
                },
            },
        )

    def test_the_card_that_pays_the_business(self, owner, shop, stripe_double):
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            stripe_customer_id="cus_1"
        )
        self.card(stripe_double)

        [method] = self.methods(owner)

        assert method["card"] == {
            "brand": "visa",
            "last4": "4242",
            "exp_month": 8,
            "exp_year": 2028,
        }
        assert method["businesses"] == [{"id": str(shop.id), "name": "Panadería López"}]
        assert (method["unavailable"], method["last_failure"]) == (False, None)

    def test_a_free_business_on_the_same_payer_is_not_said_to_be_paid_with_it(
        self, owner, shop, stripe_double
    ):
        """Audit 2 R-26: «Pays Bar La Plaza, Bar Norte, Café Central and Panadería López» named a Free business."""
        from hubs.models import Hub

        pay(shop)
        cafe = create_business(owner, name="Café Central")
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(stripe_customer_id="cus_1")
        Hub.objects.filter(pk=cafe.pk).update(billing_profile_id=shop.billing_profile_id)
        self.card(stripe_double)

        [method] = self.methods(owner)

        assert method["businesses"] == [{"id": str(shop.id), "name": "Panadería López"}]

    def test_it_is_kept_for_a_while_and_forgotten_when_the_customer_changes(
        self, owner, shop, stripe_double
    ):
        from django.test import Client

        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            stripe_customer_id="cus_1"
        )
        self.card(stripe_double)
        self.methods(owner)
        self.card(stripe_double, last4="5454")

        assert self.methods(owner)[0]["card"]["last4"] == "4242"
        assert len(stripe_double.calls_to("subscriptions.retrieve")) == 1

        body, header = signed(
            event(
                "customer.updated",
                {"id": "cus_1", "object": "customer", "invoice_settings": {}},
            )
        )
        Client().post(
            "/webhooks/stripe/",
            body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=header,
            HTTP_HOST="localhost:8001",
        )

        assert self.methods(owner)[0]["card"]["last4"] == "5454"

    def test_stripe_away_is_unavailable_never_invented(
        self, owner, shop, stripe_double
    ):
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            stripe_customer_id="cus_1"
        )
        stripe_double.answer("subscriptions.retrieve", connection_error())

        [method] = self.methods(owner)

        assert (method["card"], method["unavailable"]) == (None, True)

    def test_the_last_failure_names_its_business(self, owner, shop, stripe_double):
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            stripe_customer_id="cus_1"
        )
        self.card(stripe_double)
        failed_at = timezone.now() - timedelta(days=2)
        PaymentFailure.objects.create(
            hub=shop,
            stripe_invoice_id="in_1",
            reason="card_declined",
            invoice_created_at=failed_at,
            failed_at=failed_at,
        )

        [method] = self.methods(owner)

        assert method["last_failure"]["business"] == "Panadería López"

    def test_a_business_without_a_stripe_customer_has_no_card_yet(
        self, owner, shop, stripe_double
    ):
        assert self.methods(owner) == []
        assert stripe_double.calls == []

    def test_only_the_accounts_payers(self, shop, make_user, stripe_double):
        pay(shop)
        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
            stripe_customer_id="cus_1"
        )

        assert self.methods(make_user("other@example.com")) == []
