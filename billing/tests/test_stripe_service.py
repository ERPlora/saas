"""The one door to Stripe (``billing.stripe_service``): keys, errors, plain dicts and the tax-rate mirror.

Ported from ERPlora/saas ``hubs/subscriptions/services/stripe.py`` (``StripeService``) and
``fiscal/services/stripe_tax_rates.py`` (the Stripe half; origin/develop), with what
``hubs/main/tests/test_stripe_service.py`` and ``test_webhooks_sdk15_compat.py`` pinned about the SDK:
``StripeObject`` has no ``.get()`` and ``items`` collides with ``dict.items()``, so the gateway hands
billing plain dicts and nothing else reads an SDK object. Every call goes through ``client()``, which the
tests replace (``stripe_double``): no test reaches Stripe.

- Without a secret or restricted key nothing is called (``StripeNotConfigured``): an empty key is not
  «probably test».
- Stripe's errors become two: ``StripeUnavailable`` (network, rate limit, Stripe's own 5xx: try again,
  nothing happened) and ``StripeRefused`` (a declined card, a missing object, a misconfiguration).
- The tax rates are OURS (``billing.TaxRule``); Stripe only charges them as ``TaxRate`` objects. The mirror
  reuses an exact, exclusive one, creates it when missing, remembers it 24 h, and never creates blind: a
  failed listing fills the account with duplicate 21 % (saas#1968).
"""

from decimal import Decimal

import pytest
import stripe

from billing import stripe_service
from billing.stripe_service import (
    InvalidWebhook,
    StripeNotConfigured,
    StripeRefused,
    StripeUnavailable,
)
from billing.stripe_tax_rates import TaxRateSpec
from billing.tests.stripe_double import (
    WEBHOOK_SECRET,
    card_error,
    connection_error,
    event,
    invalid_request,
    invoice,
    invoice_payment,
    listing,
    payment_intent,
    signed,
    subscription,
)

SPAIN = TaxRateSpec(country="ES", region="", percentage=Decimal("21"))


# --- The key -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["", "pk_test_publishable", "whsec_x", "sk_prod_x"])
def test_without_a_secret_key_nothing_is_called(settings, key):
    settings.STRIPE_SECRET_KEY = key

    with pytest.raises(StripeNotConfigured):
        stripe_service.client()


def test_a_live_secret_key_is_not_used(settings):
    """PLAN-SAAS §4: live money only through a RESTRICTED key (``rk_live_``), never the account's secret."""
    from billing.stripe_keys import StripeKeyMode

    settings.STRIPE_SECRET_KEY = "sk_live_51abc"

    with pytest.raises(StripeNotConfigured):
        stripe_service.client()
    assert stripe_service.key_mode() is StripeKeyMode.UNKNOWN


def test_outside_prod_a_live_key_is_not_usable(settings):
    """pre (plan 2026-10-14-entorno-pre) charges test money only: even a restricted live key is refused
    like no key at all, so a payment answers 503 instead of charging a real card."""
    from billing.stripe_keys import StripeKeyMode

    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.STRIPE_SECRET_KEY = "rk_live_51abc"

    assert stripe_service.key_mode() is StripeKeyMode.UNKNOWN
    with pytest.raises(StripeNotConfigured):
        stripe_service.client()

    settings.STRIPE_SECRET_KEY = "rk_test_51abc"
    assert stripe_service.key_mode() is StripeKeyMode.TEST


@pytest.mark.parametrize("key", ["sk_test_51abc", "rk_test_51abc"])
def test_in_production_a_test_key_is_not_usable(settings, key):
    """BILLING-F30: production (DEBUG off) charges real money only. A test key there would let anybody pay a
    plan with a test card: it is refused like no key at all (503), and development keeps its test keys."""
    from billing.stripe_keys import StripeKeyMode

    settings.STRIPE_TEST_KEYS_ALLOWED = False
    settings.STRIPE_SECRET_KEY = key

    assert stripe_service.key_mode() is StripeKeyMode.UNKNOWN
    with pytest.raises(StripeNotConfigured):
        stripe_service.client()

    settings.STRIPE_TEST_KEYS_ALLOWED = True
    assert stripe_service.key_mode() is StripeKeyMode.TEST


def test_the_items_of_a_long_subscription_are_all_read(stripe_double):
    """Stripe embeds 10 items in a subscription; the rest are read page by page (review of L2-B)."""
    from billing.tests.stripe_double import item

    first = [item(f"si_{n}", f"price_{n}") for n in range(10)]
    rest = [item(f"si_{n}", f"price_{n}") for n in range(10, 13)]
    live = subscription("sub_9", items=first)
    live["items"]["has_more"] = True
    stripe_double.answer("subscriptions.retrieve", live)
    stripe_double.answer("subscription_items.list", listing(first + rest))

    read = stripe_service.retrieve_subscription("sub_9")

    assert [line["id"] for line in read["items"]["data"]] == [f"si_{n}" for n in range(13)]
    assert stripe_double.last("subscription_items.list").params == {"subscription": "sub_9", "limit": 100}


@pytest.mark.parametrize("key", ["sk_test_51abc", "rk_test_51abc", "rk_live_51abc"])
def test_a_secret_or_restricted_key_builds_the_client(settings, key):
    settings.STRIPE_SECRET_KEY = key

    assert isinstance(stripe_service.client(), stripe.StripeClient)


def test_the_key_mode_is_the_configured_keys(settings):
    from billing.stripe_keys import StripeKeyMode

    settings.STRIPE_SECRET_KEY = "rk_live_51abc"
    assert stripe_service.key_mode() is StripeKeyMode.LIVE
    settings.STRIPE_SECRET_KEY = ""
    assert stripe_service.key_mode() is StripeKeyMode.UNKNOWN


# --- Plain dicts and errors --------------------------------------------------------------------------


def test_billing_gets_plain_dicts_never_sdk_objects(stripe_double):
    stripe_double.answer("subscriptions.retrieve", subscription("sub_9"))

    live = stripe_service.retrieve_subscription("sub_9")

    assert type(live) is dict
    assert type(live["items"]["data"][0]["price"]) is dict
    assert live["items"]["data"][0]["price"]["id"] == "price_starter_month"
    assert stripe_double.last("subscriptions.retrieve").args == ("sub_9",)


@pytest.mark.parametrize(
    "error",
    [
        connection_error(),
        stripe.RateLimitError("Too many requests", http_status=429),
        stripe.APIError("Stripe had a problem", http_status=500),
    ],
)
def test_what_may_work_on_a_retry_is_unavailable(stripe_double, error):
    stripe_double.answer("subscriptions.retrieve", error)

    with pytest.raises(StripeUnavailable):
        stripe_service.retrieve_subscription("sub_1")


def test_a_declined_card_is_refused_with_its_codes(stripe_double):
    stripe_double.answer(
        "subscriptions.update", card_error("card_declined", "insufficient_funds")
    )

    with pytest.raises(StripeRefused) as refused:
        stripe_service.update_subscription("sub_1", {"cancel_at_period_end": False})

    assert refused.value.card is True
    assert (refused.value.code, refused.value.decline_code) == (
        "card_declined",
        "insufficient_funds",
    )


def test_a_missing_object_is_refused_with_its_code(stripe_double):
    stripe_double.answer("subscriptions.cancel", invalid_request("resource_missing"))

    with pytest.raises(StripeRefused) as refused:
        stripe_service.cancel_subscription("sub_gone")

    assert (refused.value.card, refused.value.code, refused.value.status) == (
        False,
        "resource_missing",
        404,
    )


def test_a_bad_key_is_refused_not_retried(stripe_double):
    stripe_double.answer(
        "subscriptions.retrieve",
        stripe.AuthenticationError("Invalid API Key", http_status=401),
    )

    with pytest.raises(StripeRefused):
        stripe_service.retrieve_subscription("sub_1")


def test_the_idempotency_key_travels_as_an_option(stripe_double):
    stripe_service.create_checkout_session(
        {"mode": "subscription"}, idempotency_key="checkout-1"
    )

    assert stripe_double.last("checkout.sessions.create").options == {
        "idempotency_key": "checkout-1"
    }


def test_without_an_idempotency_key_no_option_is_sent(stripe_double):
    stripe_double.answer("subscriptions.retrieve", subscription())

    stripe_service.retrieve_subscription("sub_1")

    assert stripe_double.last("subscriptions.retrieve").options == {}


# --- The tax-rate mirror -----------------------------------------------------------------------------


def test_a_missing_rate_is_created_on_top_of_the_net_price(stripe_double):
    ids = stripe_service.tax_rate_ids([SPAIN])

    created = stripe_double.last("tax_rates.create").params
    assert ids == [stripe_double.tax_rates[0]["id"]]
    assert created == {
        "display_name": "IVA",
        "description": "ERPlora — ES 21%",
        "percentage": 21.0,
        "inclusive": False,
        "country": "ES",
        "tax_type": "vat",
    }
    assert stripe_double.last("tax_rates.list").params == {"active": True, "limit": 100}


def test_an_exact_exclusive_rate_is_reused(stripe_double):
    stripe_double.tax_rates.append(
        {
            "id": "txr_es_21",
            "percentage": 21.0,
            "inclusive": False,
            "country": "ES",
            "active": True,
        }
    )

    assert stripe_service.tax_rate_ids([SPAIN]) == ["txr_es_21"]
    assert stripe_double.calls_to("tax_rates.create") == []


def test_an_inclusive_rate_of_the_same_percentage_is_not_ours(stripe_double):
    stripe_double.tax_rates.append(
        {
            "id": "txr_inclusive",
            "percentage": 21.0,
            "inclusive": True,
            "country": "ES",
            "active": True,
        }
    )

    ids = stripe_service.tax_rate_ids([SPAIN])

    assert ids != ["txr_inclusive"]
    assert len(stripe_double.calls_to("tax_rates.create")) == 1


def test_the_mirror_follows_the_pages_of_the_listing(stripe_double):
    first = listing(
        [{"id": "txr_de", "percentage": 19.0, "inclusive": False, "country": "DE"}],
        has_more=True,
    )
    second = listing(
        [{"id": "txr_es_21", "percentage": 21.0, "inclusive": False, "country": "ES"}]
    )
    stripe_double.answer("tax_rates.list", first, second)

    assert stripe_service.tax_rate_ids([SPAIN]) == ["txr_es_21"]
    assert (
        stripe_double.calls_to("tax_rates.list")[1].params["starting_after"] == "txr_de"
    )


def test_the_rate_is_remembered(stripe_double):
    stripe_service.tax_rate_ids([SPAIN])
    calls = len(stripe_double.calls)

    stripe_service.tax_rate_ids([SPAIN])

    assert len(stripe_double.calls) == calls


def test_a_failed_listing_never_creates_blind(stripe_double):
    stripe_double.answer("tax_rates.list", connection_error())

    with pytest.raises(StripeUnavailable):
        stripe_service.tax_rate_ids([SPAIN])

    assert stripe_double.calls_to("tax_rates.create") == []


def test_nothing_to_add_asks_nothing(stripe_double):
    assert stripe_service.tax_rate_ids([]) == []
    assert stripe_double.calls == []


# --- Reads the webhook and the sweep need ------------------------------------------------------------


def test_the_open_invoices_of_a_subscription(stripe_double):
    stripe_double.answer("invoices.list", listing([invoice("in_7")]))

    found = stripe_service.open_invoices("sub_1")

    assert [one["id"] for one in found] == ["in_7"]
    assert stripe_double.last("invoices.list").params == {
        "subscription": "sub_1",
        "status": "open",
        "limit": 100,
    }


def test_a_customer_is_deleted_by_its_id(stripe_double):
    """A departed payer (ACCOUNTS-F27): Stripe removes the customer and its payment methods; its invoices stay."""
    stripe_double.answer("customers.delete", {"id": "cus_1", "object": "customer", "deleted": True})

    assert stripe_service.delete_customer("cus_1")["deleted"] is True
    assert stripe_double.last("customers.delete").args == ("cus_1",)


def test_an_unpaid_invoice_is_voided_by_its_id(stripe_double):
    stripe_double.answer("invoices.void_invoice", invoice("in_7", status="void"))

    assert stripe_service.void_invoice("in_7")["status"] == "void"
    assert stripe_double.last("invoices.void_invoice").args == ("in_7",)


def test_why_an_invoice_was_not_paid(stripe_double):
    stripe_double.answer(
        "invoice_payments.list", listing([invoice_payment("pi_9", invoice_id="in_1")])
    )
    stripe_double.answer(
        "payment_intents.retrieve",
        payment_intent(
            "pi_9",
            code="card_declined",
            decline_code="stolen_card",
            payment_method="pm_1",
        ),
    )

    assert stripe_service.payment_failure_of("in_1") == {
        "code": "card_declined",
        "decline_code": "stolen_card",
        "payment_method": "pm_1",
    }
    assert stripe_double.last("invoice_payments.list").params["invoice"] == "in_1"


def test_an_invoice_without_a_payment_attempt_has_no_reason(stripe_double):
    stripe_double.answer("invoice_payments.list", listing([]))

    assert stripe_service.payment_failure_of("in_1") is None


def paid(pi_id, cents, *, status="paid"):
    return {**invoice_payment(pi_id, invoice_id="in_1"), "status": status, "amount_paid": cents}


def test_what_an_invoice_collected_is_refunded_once_per_payment(stripe_double):
    """Each paid PaymentIntent of the invoice, in full; a payment that never collected is not refunded."""
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629), paid("pi_2", 0, status="canceled")]))
    stripe_double.answer("refunds.create", {"id": "re_1", "object": "refund", "status": "succeeded"})

    assert stripe_service.refund_invoice("in_1", key="refund-cs_1", metadata={"hub_id": "h"}) == 3629

    (call,) = stripe_double.calls_to("refunds.create")
    assert call.params == {"payment_intent": "pi_1", "reason": "requested_by_customer", "metadata": {"hub_id": "h"}}
    assert call.options == {"idempotency_key": "refund-cs_1-pi_1"}


def test_a_charge_stripe_already_refunded_counts_as_refunded(stripe_double):
    """A redelivery after Stripe forgot the idempotency key (24 hours): the second refund is refused, not lost."""
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629)]))
    stripe_double.answer(
        "refunds.create", invalid_request(code="charge_already_refunded", message="Charge has already been refunded.")
    )

    assert stripe_service.refund_invoice("in_1", key="refund-cs_1", metadata={}) == 3629


def test_any_other_refusal_of_a_refund_is_raised(stripe_double):
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629)]))
    stripe_double.answer("refunds.create", invalid_request(code="resource_missing", message="No such payment_intent"))

    with pytest.raises(StripeRefused):
        stripe_service.refund_invoice("in_1", key="refund-cs_1", metadata={})


# --- The webhook's signature -------------------------------------------------------------------------


def test_a_signed_event_is_read(stripe_keys):
    body, header = signed(event("invoice.paid", invoice("in_1"), event_id="evt_1"))

    read = stripe_service.construct_event(body, header)

    assert (read["id"], read["type"], read["data"]["object"]["id"]) == (
        "evt_1",
        "invoice.paid",
        "in_1",
    )
    assert type(read["data"]["object"]) is dict


def test_a_tampered_event_is_refused(stripe_keys):
    body, header = signed(event("invoice.paid", invoice("in_1")))

    with pytest.raises(InvalidWebhook):
        stripe_service.construct_event(body.replace(b"in_1", b"in_2"), header)


def test_an_event_signed_with_another_secret_is_refused(stripe_keys):
    body, header = signed(event("invoice.paid", invoice()), secret="whsec_someone_else")

    with pytest.raises(InvalidWebhook):
        stripe_service.construct_event(body, header)


def test_a_replayed_old_event_is_refused(stripe_keys):
    import time

    body, header = signed(
        event("invoice.paid", invoice()), timestamp=int(time.time()) - 3600
    )

    with pytest.raises(InvalidWebhook):
        stripe_service.construct_event(body, header)


def test_garbage_is_refused(stripe_keys):
    with pytest.raises(InvalidWebhook):
        stripe_service.construct_event(b"not json", "t=1,v1=abc")
    with pytest.raises(InvalidWebhook):
        stripe_service.construct_event(b"{}", None)


def test_without_the_webhook_secret_nothing_is_read(settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    body, header = signed(event("invoice.paid", invoice()), secret=WEBHOOK_SECRET)

    with pytest.raises(StripeNotConfigured):
        stripe_service.construct_event(body, header)
