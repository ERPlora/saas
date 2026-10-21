"""The one door to Stripe (lot L2-B; PLAN-SAAS §4): the only module of the SaaS that imports ``stripe``.

Ported from ERPlora/saas ``hubs/subscriptions/services/stripe.py`` (``StripeService``) and the Stripe half of
``fiscal/services/stripe_tax_rates.py`` (origin/develop), as plain functions over one ``StripeClient``:

- ``client()`` builds it from ``STRIPE_SECRET_KEY`` (a restricted ``rk_live_`` key in production, test keys
  locally; never a key in code), with a short timeout and one retry: a command waits for Stripe inside its
  transaction. Without a secret or restricted key nothing is called (``StripeNotConfigured``). The tests
  replace ``client`` with ``billing/tests/stripe_double.py``.
- Every answer is a plain dict (``StripeObject.to_dict()``): on stripe>=15 a ``StripeObject`` has no
  ``.get()`` and ``items`` collides with ``dict.items()``, so nothing else reads an SDK object.
- Stripe's errors become two: ``StripeUnavailable`` (network, rate limit, Stripe's own 5xx: nothing
  happened, try again) and ``StripeRefused`` (a declined card, a missing object, a misconfiguration).
- The tax rates are OURS (``billing.TaxRule``, ``billing.stripe_tax_rates``); Stripe charges them as
  ``TaxRate`` objects, mirrored here (``tax_rate_ids``).

No database here: the callers (``billing.services``) decide and record.
"""

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import stripe
from django.conf import settings
from django.core.cache import cache

from billing.stripe_keys import StripeKeyMode, stripe_key_mode
from billing.stripe_tax_rates import TaxRateSpec, matches

logger = logging.getLogger("billing.stripe")

#: How long a mirrored ``TaxRate`` id is trusted: a rate never changes its value; only somebody archiving
#: it in the dashboard can make it stale.
TAX_RATE_CACHE_SECONDS = 24 * 60 * 60
#: How many times the SDK retries a call that failed on the network (with Stripe's idempotency keys).
MAX_NETWORK_RETRIES = 1
#: How old a signed webhook may be (Stripe's default tolerance): an older one is a replay.
WEBHOOK_TOLERANCE_SECONDS = 300


class StripeNotConfigured(Exception):
    """No usable secret key (or webhook secret): nothing is sent to Stripe."""


class StripeUnavailable(Exception):
    """Stripe could not be reached or failed on its side: nothing happened; try again."""


class StripeRefused(Exception):
    """Stripe answered no: a declined card (``card``), a missing object (``resource_missing``)…"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        decline_code: str = "",
        status: int | None = None,
        card: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code or ""
        self.decline_code = decline_code or ""
        self.status = status
        self.card = card


class InvalidWebhook(Exception):
    """A webhook whose body or signature is not Stripe's (or is too old)."""


def client() -> stripe.StripeClient:
    """The Stripe client of this process's key; ``StripeNotConfigured`` without a usable one (``key_mode``)."""
    key = settings.STRIPE_SECRET_KEY
    if key_mode() is StripeKeyMode.UNKNOWN:
        raise StripeNotConfigured(
            "STRIPE_SECRET_KEY is not a test key (sk_test_, rk_test_) nor a restricted live key (rk_live_)"
        )
    return stripe.StripeClient(
        key,
        max_network_retries=MAX_NETWORK_RETRIES,
        http_client=stripe.RequestsClient(timeout=settings.STRIPE_TIMEOUT_SECONDS),
    )


def key_mode() -> StripeKeyMode:
    """Whether the configured key charges real money (``LIVE``), test money, or is not usable (``UNKNOWN``).

    Live money only through a RESTRICTED key (``rk_live_``, PLAN-SAAS §4): the account's live secret key
    (``sk_live_``) can do everything a stolen key could, so it is refused like no key at all. And only in
    prod: outside it (``ERPLORA_ENVIRONMENT=pre``) any live key is refused the same way (``billing.E002``
    stops the deploy first). Production itself (DEBUG off) refuses a test key (``billing.E003``,
    ``settings.STRIPE_TEST_KEYS_ALLOWED``): development runs as prod with DEBUG on and keeps its test keys."""
    key = settings.STRIPE_SECRET_KEY or ""
    mode = stripe_key_mode(key)
    if mode is StripeKeyMode.LIVE and not key.startswith("rk_"):
        logger.error("[STRIPE] STRIPE_SECRET_KEY is a live SECRET key: use a restricted rk_live_ key")
        return StripeKeyMode.UNKNOWN
    if mode is StripeKeyMode.LIVE and settings.ERPLORA_ENVIRONMENT != "prod":
        logger.error(
            "[STRIPE] STRIPE_SECRET_KEY is a live key outside prod (%s): use a test key", settings.ERPLORA_ENVIRONMENT
        )
        return StripeKeyMode.UNKNOWN
    if mode is StripeKeyMode.TEST and not settings.STRIPE_TEST_KEYS_ALLOWED:
        # Production (DEBUG off) with a test key would let anybody pay a plan with a test card (billing.E003).
        logger.error("[STRIPE] STRIPE_SECRET_KEY is a test key in production: use the restricted rk_live_ key")
        return StripeKeyMode.UNKNOWN
    return mode


def _plain(value: Any) -> Any:
    return value.to_dict() if hasattr(value, "to_dict") else value


def _call(
    method: Callable,
    *args: Any,
    params: dict | None = None,
    idempotency_key: str | None = None,
) -> Any:
    options = {"idempotency_key": idempotency_key} if idempotency_key else {}
    try:
        return _plain(method(*args, params=params or {}, options=options))
    except stripe.CardError as error:
        raise StripeRefused(
            error.user_message or str(error),
            code=error.code or "card_declined",
            decline_code=getattr(error.error, "decline_code", "") or "",
            status=error.http_status,
            card=True,
        ) from error
    except (stripe.APIConnectionError, stripe.RateLimitError, stripe.APIError) as error:
        logger.warning("[STRIPE] Unavailable: %s", error)
        raise StripeUnavailable(str(error)) from error
    except stripe.StripeError as error:
        logger.error(
            "[STRIPE] Refused (%s, HTTP %s): %s", error.code, error.http_status, error
        )
        raise StripeRefused(
            str(error), code=error.code or "", status=error.http_status
        ) from error


# --- Customers ---------------------------------------------------------------------------------------


def create_customer(params: dict, *, idempotency_key: str) -> dict:
    return _call(
        client().v1.customers.create, params=params, idempotency_key=idempotency_key
    )


def find_customer(billing_profile_id: str) -> dict | None:
    """The customer created for a payer (``metadata.billing_profile_id``), if Stripe has one: a checkout
    that failed after creating it rolled its id back, and the next one must not create another."""
    found = _call(
        client().v1.customers.search,
        params={"query": f"metadata['billing_profile_id']:'{billing_profile_id}'"},
    )["data"]
    return found[0] if found else None


def retrieve_price(price_id: str) -> dict:
    return _call(client().v1.prices.retrieve, price_id)


def retrieve_customer(customer_id: str) -> dict:
    return _call(client().v1.customers.retrieve, customer_id)


def update_customer(customer_id: str, params: dict) -> dict:
    return _call(client().v1.customers.update, customer_id, params=params)


def delete_customer(customer_id: str) -> dict:
    """Delete the customer of a payer whose account is gone: Stripe drops its payment methods; its invoices stay."""
    return _call(client().v1.customers.delete, customer_id)


def customer_tax_ids(customer_id: str) -> list[dict]:
    return _call(
        client().v1.customers.tax_ids.list, customer_id, params={"limit": 100}
    )["data"]


def add_customer_tax_id(customer_id: str, *, tax_type: str, value: str) -> dict:
    return _call(
        client().v1.customers.tax_ids.create,
        customer_id,
        params={"type": tax_type, "value": value},
    )


# --- Tax rates ---------------------------------------------------------------------------------------


def tax_rate_ids(specs: list[TaxRateSpec]) -> list[str]:
    """The Stripe ``TaxRate`` id of each spec: remembered, else an exact exclusive one of the account, else a
    new one. A failed listing is NOT swallowed (``StripeUnavailable``): creating blind would fill the account
    with duplicate rates."""
    found = []
    for spec in specs:
        cached = cache.get(spec.cache_key)
        if cached:
            found.append(cached)
            continue
        rate_id = _existing_rate(spec) or _create_rate(spec)
        cache.set(spec.cache_key, rate_id, TAX_RATE_CACHE_SECONDS)
        found.append(rate_id)
    return found


def _existing_rate(spec: TaxRateSpec) -> str | None:
    params: dict = {"active": True, "limit": 100}
    while True:
        page = _call(client().v1.tax_rates.list, params=params)
        for rate in page["data"]:
            if matches(SimpleNamespace(**rate), spec):
                return rate["id"]
        if not page.get("has_more") or not page["data"]:
            return None
        params = {**params, "starting_after": page["data"][-1]["id"]}


def _create_rate(spec: TaxRateSpec) -> str:
    rate = _call(
        client().v1.tax_rates.create,
        params={
            "display_name": spec.display_name,
            "description": spec.description,
            "percentage": float(spec.percentage),
            "inclusive": False,
            "country": spec.country,
            "tax_type": spec.tax_type,
        },
    )
    logger.info("[STRIPE] TaxRate %s created for %s", rate["id"], spec.description)
    return rate["id"]


# --- Checkout, subscriptions and invoices ------------------------------------------------------------


def create_checkout_session(params: dict, *, idempotency_key: str) -> dict:
    return _call(
        client().v1.checkout.sessions.create,
        params=params,
        idempotency_key=idempotency_key,
    )


def retrieve_subscription(subscription_id: str) -> dict:
    """The live subscription with ALL its items: Stripe embeds the first 10, the rest are listed."""
    live = _call(client().v1.subscriptions.retrieve, subscription_id)
    items = live.get("items") or {}
    if items.get("has_more"):
        live["items"] = {**items, "data": subscription_items(subscription_id), "has_more": False}
    return live


def subscription_items(subscription_id: str) -> list[dict]:
    """Every item of a subscription (Stripe allows 20; a page holds 100)."""
    params: dict = {"subscription": subscription_id, "limit": 100}
    found: list[dict] = []
    while True:
        page = _call(client().v1.subscription_items.list, params=params)
        found += page["data"]
        if not page.get("has_more") or not page["data"]:
            return found
        params = {**params, "starting_after": page["data"][-1]["id"]}


def update_subscription(
    subscription_id: str, params: dict, *, idempotency_key: str | None = None
) -> dict:
    return _call(
        client().v1.subscriptions.update,
        subscription_id,
        params=params,
        idempotency_key=idempotency_key,
    )


def cancel_subscription(subscription_id: str, *, credit_unused: bool = False) -> dict:
    """End the subscription NOW. ``credit_unused``: the time paid and not used becomes the customer's credit
    (a final invoice with the proration), for a subscription that should never have existed."""
    params = {"prorate": True, "invoice_now": True} if credit_unused else {}
    return _call(client().v1.subscriptions.cancel, subscription_id, params=params)


def expire_checkout_session(session_id: str) -> dict:
    """Close an open Checkout Session so it can no longer be paid."""
    return _call(client().v1.checkout.sessions.expire, session_id)


def create_subscription_item(params: dict, *, idempotency_key: str) -> dict:
    return _call(
        client().v1.subscription_items.create,
        params=params,
        idempotency_key=idempotency_key,
    )


def create_schedule(subscription_id: str) -> dict:
    """A subscription schedule made from the subscription: its first phase is the period being paid."""
    return _call(client().v1.subscription_schedules.create, params={"from_subscription": subscription_id})


def retrieve_schedule(schedule_id: str) -> dict:
    """A subscription schedule with its phases (each item's price as an id, its rates as objects)."""
    return _call(client().v1.subscription_schedules.retrieve, schedule_id)


def update_schedule(schedule_id: str, params: dict) -> dict:
    return _call(client().v1.subscription_schedules.update, schedule_id, params=params)


def release_schedule(schedule_id: str) -> dict:
    """Detach the schedule: the subscription keeps its current items and nothing changes later."""
    return _call(client().v1.subscription_schedules.release, schedule_id)


def preview_invoice(params: dict) -> dict:
    return _call(client().v1.invoices.create_preview, params=params)


def void_invoice(invoice_id: str) -> dict:
    """Cancel an unpaid invoice for good: it can no longer be paid (Stripe sends ``invoice.voided``)."""
    return _call(client().v1.invoices.void_invoice, invoice_id)


def open_invoices(subscription_id: str) -> list[dict]:
    return _call(
        client().v1.invoices.list,
        params={"subscription": subscription_id, "status": "open", "limit": 100},
    )["data"]


def invoice_lines(invoice: dict) -> list[dict]:
    """Every line of an invoice: the event embeds the first ones (``lines.has_more``), the rest are listed."""
    embedded = invoice.get("lines") or {}
    if not embedded.get("has_more"):
        return list(embedded.get("data") or [])
    return _every(client().v1.invoices.line_items.list, invoice["id"])


def credit_note_lines(credit_note: dict) -> list[dict]:
    """Every line of a credit note, as ``invoice_lines``."""
    embedded = credit_note.get("lines") or {}
    if not embedded.get("has_more"):
        return list(embedded.get("data") or [])
    return _every(client().v1.credit_notes.line_items.list, credit_note["id"])


def _every(method: Callable, parent_id: str) -> list[dict]:
    params: dict = {"limit": 100}
    found: list[dict] = []
    while True:
        page = _call(method, parent_id, params=params)
        found += page["data"]
        if not page.get("has_more") or not page["data"]:
            return found
        params = {**params, "starting_after": page["data"][-1]["id"]}


def invoice_paid_by(payment_intent_id: str) -> str | None:
    """The Stripe invoice a PaymentIntent paid, or ``None`` (a charge of no invoice)."""
    payments = _call(
        client().v1.invoice_payments.list,
        params={"payment": {"type": "payment_intent", "payment_intent": payment_intent_id}, "limit": 10},
    )["data"]
    for payment in payments:
        found = payment.get("invoice")
        if found:
            return found["id"] if isinstance(found, dict) else found
    return None


def charge_refunds(charge_id: str) -> list[dict]:
    """Every refund of a charge."""
    params: dict = {"charge": charge_id, "limit": 100}
    found: list[dict] = []
    while True:
        page = _call(client().v1.refunds.list, params=params)
        found += page["data"]
        if not page.get("has_more") or not page["data"]:
            return found
        params = {**params, "starting_after": page["data"][-1]["id"]}


def credit_note_refund_ids(invoice_id: str) -> set[str]:
    """The refunds the credit notes of an invoice made (``refunds[].refund`` since the 2025 API, ``refund``
    before): those are the credit notes' to rectify, not a refund's."""
    notes = _call(client().v1.credit_notes.list, params={"invoice": invoice_id, "limit": 100})["data"]
    ids: set[str] = set()
    for note in notes:
        refunds = [entry.get("refund") for entry in note.get("refunds") or []] + [note.get("refund")]
        ids |= {(refund["id"] if isinstance(refund, dict) else refund) for refund in refunds if refund}
    return ids


def payment_card(*, subscription_id: str = "", customer_id: str = "") -> dict | None:
    """The card that pays: the subscription's own (Checkout puts it there), else the customer's default for
    invoices. ``{brand, last4, exp_month, exp_year}``, or ``None`` when Stripe has none."""
    method = None
    if subscription_id:
        live = _call(
            client().v1.subscriptions.retrieve, subscription_id, params={"expand": ["default_payment_method"]}
        )
        method = live.get("default_payment_method")
    if not isinstance(method, dict) and customer_id:
        customer = _call(
            client().v1.customers.retrieve,
            customer_id,
            params={"expand": ["invoice_settings.default_payment_method"]},
        )
        method = (customer.get("invoice_settings") or {}).get("default_payment_method")
    card = method.get("card") if isinstance(method, dict) else None
    if not card:
        return None
    return {
        "brand": card.get("brand") or "",
        "last4": card.get("last4") or "",
        "exp_month": int(card.get("exp_month") or 0),
        "exp_year": int(card.get("exp_year") or 0),
    }


def payment_failure_of(invoice_id: str) -> dict | None:
    """Why the last payment of an invoice failed: ``{code, decline_code, payment_method}``, or ``None``
    when nothing says (no attempt, no error on it)."""
    payments = _call(
        client().v1.invoice_payments.list, params={"invoice": invoice_id, "limit": 10}
    )["data"]
    attempts = sorted(
        (
            payment
            for payment in payments
            if (payment.get("payment") or {}).get("payment_intent")
        ),
        key=lambda payment: payment.get("created") or 0,
    )
    if not attempts:
        return None
    intent_id = attempts[-1]["payment"]["payment_intent"]
    if isinstance(intent_id, dict):
        intent_id = intent_id["id"]
    error = _call(client().v1.payment_intents.retrieve, intent_id).get(
        "last_payment_error"
    )
    if not error:
        return None
    method = error.get("payment_method")
    return {
        "code": error.get("code") or "",
        "decline_code": error.get("decline_code") or "",
        "payment_method": (method.get("id") if isinstance(method, dict) else method)
        or "",
    }


def create_portal_session(customer_id: str, *, return_url: str, configuration: str) -> dict:
    """A Customer Portal session with OUR configuration (cards and receipts; no plan changes, which must carry
    our tax rates)."""
    return _call(
        client().v1.billing_portal.sessions.create,
        params={"customer": customer_id, "return_url": return_url, "configuration": configuration},
    )


def checkout_ui_mode_annotation() -> object | None:
    """The raw ``ui_mode`` annotation of the SDK's Checkout Session create params (``billing.stripe_checkout``
    reads the accepted values out of it), or ``None`` when the SDK no longer exposes it there."""
    try:
        from stripe.params.checkout import SessionCreateParams
    except ImportError:  # pragma: no cover - depends on the installed SDK layout
        return None
    return SessionCreateParams.__annotations__.get("ui_mode")


# --- Test clocks (test mode only; billing.stripe_test_clocks refuses a live key first) ---------------


def create_test_clock(params: dict) -> dict:
    return _call(client().v1.test_helpers.test_clocks.create, params=params)


def advance_test_clock(clock_id: str, params: dict) -> dict:
    return _call(client().v1.test_helpers.test_clocks.advance, clock_id, params=params)


def retrieve_test_clock(clock_id: str) -> dict:
    return _call(client().v1.test_helpers.test_clocks.retrieve, clock_id)


# --- Webhooks ----------------------------------------------------------------------------------------


def construct_event(payload: bytes, signature: str | None) -> dict:
    """The event Stripe signed, as a plain dict; ``InvalidWebhook`` for anything else (a bad body, a bad
    or missing signature, one older than ``WEBHOOK_TOLERANCE_SECONDS``)."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET is empty")
    try:
        received = stripe.Webhook.construct_event(
            payload, signature, secret, tolerance=WEBHOOK_TOLERANCE_SECONDS
        )
    except (ValueError, stripe.SignatureVerificationError) as error:
        raise InvalidWebhook(str(error)) from error
    return _plain(received)
