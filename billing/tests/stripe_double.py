"""Stripe at the boundary, for the tests: what ``billing.stripe_service.client()`` returns in them.

No test reaches Stripe. The double answers like ``stripe.StripeClient`` (``client.v1.<service>.<method>(…,
params=…, options=…)``): it records every call and returns SDK objects (``StripeObject.construct_from``)
built in the shapes of the API version the SDK pins (2026-09-30: the period on the subscription items, the
invoice's subscription under ``parent.subscription_details``), so the gateway's conversion to plain dicts is
exercised too. An exception given as an answer is raised, as the SDK raises it.

Boring calls have a default answer (the account's tax rates, a new customer, a checkout session, a portal
session); everything that decides money (a subscription, an invoice, a preview) must be answered by the
test, or the call fails loudly. ``signed_event`` signs a webhook payload exactly as Stripe does, so the
webhook's signature check is the real one.
"""

import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any

import stripe

DAY = 86_400
NOW = int(time.time())
#: The current period of the subscriptions the double answers: begun 10 days ago, renewing in 20.
MONTH_START = NOW - 10 * DAY
MONTH_END = MONTH_START + 30 * DAY
WEBHOOK_SECRET = "whsec_test_double"


@dataclass
class Call:
    path: str
    args: tuple
    params: dict
    options: dict = field(default_factory=dict)


class StripeDouble:
    """A fake ``StripeClient``: ``double.answer("subscriptions.retrieve", subscription(...))``."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._answers: dict[str, list] = {}
        self._ids = itertools.count(1)
        #: What each idempotency key answered (Stripe replays it, errors included).
        self._idempotent: dict[str, tuple] = {}
        #: The account's tax rates (``tax_rates.list``); ``tax_rates.create`` adds to it.
        self.tax_rates: list[dict] = []
        #: Each customer's tax ids (``customers.tax_ids.list``/``create``).
        self.customer_tax_ids: dict[str, list[dict]] = {}
        self.v1 = _Node(self, "")

    # --- Arranging -----------------------------------------------------------------------------

    def answer(self, path: str, *values: Any) -> "StripeDouble":
        """Each call to ``path`` takes the next value; the last one keeps answering."""
        self._answers[path] = list(values)
        return self

    # --- Asserting -----------------------------------------------------------------------------

    def calls_to(self, path: str) -> list[Call]:
        return [call for call in self.calls if call.path == path]

    def last(self, path: str) -> Call:
        found = self.calls_to(path)
        assert found, (
            f"Stripe {path} was never called; calls: {[c.path for c in self.calls]}"
        )
        return found[-1]

    def paths(self) -> list[str]:
        return [call.path for call in self.calls]

    # --- Answering -----------------------------------------------------------------------------

    def _handle(self, path: str, args: tuple, kwargs: dict) -> Any:
        params = dict(kwargs.get("params") or {})
        call = Call(path, args, params, dict(kwargs.get("options") or {}))
        self.calls.append(call)
        key = call.options.get("idempotency_key")
        if key is not None and key in self._idempotent:
            # Stripe keeps the answer of an idempotency key (24 h), errors included; the same key with other
            # parameters is refused.
            seen_params, value = self._idempotent[key]
            if seen_params != (path, args, params):
                raise stripe.IdempotencyError("Keys for idempotent requests can only be used with the same parameters")
        else:
            value = self._answer(call)
            if key is not None:
                self._idempotent[key] = ((path, args, params), value)
        if isinstance(value, BaseException):
            raise value
        return _sdk(value)

    def _answer(self, call: Call) -> Any:
        path = call.path
        if path in self._answers:
            queue = self._answers[path]
            value = queue.pop(0) if len(queue) > 1 else queue[0]
            if callable(value) and not isinstance(value, dict):
                value = value(call)
        else:
            value = self._default(call)
        return value

    def _default(self, call: Call) -> Any:
        number = next(self._ids)
        params = call.params
        match call.path:
            case "tax_rates.list":
                return listing(self.tax_rates)
            case "tax_rates.create":
                rate = {
                    "id": f"txr_{number}",
                    "object": "tax_rate",
                    "active": True,
                    **params,
                }
                self.tax_rates.append(rate)
                return rate
            case "customers.search":
                return {"object": "search_result", "data": [], "has_more": False}
            case "customers.create":
                return {"id": "cus_new", "object": "customer", **params}
            case "customers.update":
                return {"id": call.args[0], "object": "customer", **params}
            case "customers.tax_ids.list":
                return listing(self.customer_tax_ids.get(call.args[0], []))
            case "customers.tax_ids.create":
                tax_id = {"id": f"txi_{number}", "object": "tax_id", **params}
                self.customer_tax_ids.setdefault(call.args[0], []).append(tax_id)
                return tax_id
            case "checkout.sessions.create":
                return {
                    "id": f"cs_test_{number}",
                    "object": "checkout.session",
                    "client_secret": f"cs_test_{number}_secret_abc",
                    "status": "open",
                    **{
                        key: params[key]
                        for key in ("mode", "metadata", "customer")
                        if key in params
                    },
                }
            case "checkout.sessions.expire":
                return {"id": call.args[0], "object": "checkout.session", "status": "expired"}
            case "billing_portal.sessions.create":
                return {
                    "id": f"bps_{number}",
                    "object": "billing_portal.session",
                    "url": f"https://billing.stripe.com/p/session/test_{number}",
                    **params,
                }
        raise AssertionError(
            f"Stripe {call.path} was called without an answer (params {params})"
        )


class _Node:
    def __init__(self, double: StripeDouble, path: str) -> None:
        self._double = double
        self._path = path

    def __getattr__(self, name: str) -> "_Node":
        if name.startswith("_"):
            raise AttributeError(name)
        return _Node(self._double, f"{self._path}.{name}" if self._path else name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._double._handle(self._path, args, kwargs)


def _sdk(value: Any) -> Any:
    """An answer as the SDK returns it: a StripeObject for a dict (lists too), the rest as it is."""
    if isinstance(value, dict):
        return stripe.StripeObject.construct_from(value, "sk_test_double")
    return value


# --- Objects in the shapes of the pinned API version ----------------------------------------------


def listing(data: list[dict], *, has_more: bool = False) -> dict:
    return {"object": "list", "data": list(data), "has_more": has_more, "url": "/v1/x"}


def price(price_id: str, *, interval: str = "month") -> dict:
    return {"id": price_id, "object": "price", "recurring": {"interval": interval}}


def item(
    item_id: str,
    price_id: str,
    *,
    interval: str = "month",
    period: tuple[int, int] = (MONTH_START, MONTH_END),
    tax_rates: list | None = None,
) -> dict:
    return {
        "id": item_id,
        "object": "subscription_item",
        "price": price(price_id, interval=interval),
        "quantity": 1,
        "current_period_start": period[0],
        "current_period_end": period[1],
        "tax_rates": tax_rates or [],
    }


def subscription(
    sub_id: str = "sub_1",
    *,
    status: str = "active",
    customer: str = "cus_1",
    items: list[dict] | None = None,
    cancel_at_period_end: bool = False,
    trial: tuple[int | None, int | None] = (None, None),
    metadata: dict | None = None,
    default_payment_method: str | None = None,
) -> dict:
    return {
        "id": sub_id,
        "object": "subscription",
        "status": status,
        "customer": customer,
        "cancel_at_period_end": cancel_at_period_end,
        "cancel_at": None,
        "trial_start": trial[0],
        "trial_end": trial[1],
        "metadata": metadata or {},
        "default_payment_method": default_payment_method,
        "items": listing(
            items if items is not None else [item("si_plan", "price_starter_month")]
        ),
    }


def invoice_line(
    line_id: str = "il_plan",
    *,
    price_id: str = "price_starter_month",
    amount: int = 2999,
    tax: int = 630,
    description: str = "1 × Starter (at €29.99 / month)",
    proration: bool = False,
    quantity: int = 1,
    period: tuple[int, int] = (MONTH_START, MONTH_END),
    subscription_item: str = "si_plan",
) -> dict:
    """A line of an invoice as the pinned API version shapes it: the price under ``pricing.price_details``,
    the proration under ``parent.subscription_item_details`` and its tax under ``taxes``."""
    return {
        "id": line_id,
        "object": "line_item",
        "amount": amount,
        "currency": "eur",
        "description": description,
        "quantity": quantity,
        "period": {"start": period[0], "end": period[1]},
        "parent": {
            "type": "subscription_item_details",
            "subscription_item_details": {
                "subscription_item": subscription_item,
                "proration": proration,
                "subscription": "sub_1",
            },
        },
        "pricing": {"type": "price_details", "price_details": {"price": price_id, "product": "prod_1"}},
        "taxes": (
            [
                {
                    "amount": tax,
                    "tax_behavior": "exclusive",
                    "tax_rate_details": {"tax_rate": "txr_1"},
                    "taxable_amount": amount,
                    "type": "tax_rate_details",
                }
            ]
            if tax
            else []
        ),
    }


def invoice(
    invoice_id: str = "in_1",
    *,
    subscription_id: str = "sub_1",
    customer: str = "cus_1",
    created: int | None = None,
    status: str = "open",
    amount_due: int = 3629,
    amount_paid: int = 0,
    tax: int = 630,
    billing_reason: str = "subscription_cycle",
    hosted_invoice_url: str = "https://invoice.stripe.com/i/test_1",
    customer_address: dict | None = None,
    lines: list[dict] | None = None,
) -> dict:
    """A Stripe invoice. Without ``lines``, one line of the plan that adds up to ``amount_due``; with them,
    the totals are theirs (``amount_due`` and ``tax`` are ignored)."""
    if lines is None:
        lines = [invoice_line(amount=amount_due - tax, tax=tax)]
    else:
        tax = sum(sum(t["amount"] for t in line["taxes"]) for line in lines)
        amount_due = sum(line["amount"] for line in lines) + tax
    created = created if created is not None else int(time.time())
    return {
        "id": invoice_id,
        "object": "invoice",
        "status": status,
        "customer": customer,
        "number": f"ABCD{invoice_id[-4:].upper()}-0001",
        "livemode": False,
        "created": created,
        "amount_due": amount_due,
        "amount_paid": amount_paid,
        "subtotal": amount_due - tax,
        "total": amount_due,
        "total_taxes": [{"amount": tax, "type": "tax_rate_details"}] if tax else [],
        "currency": "eur",
        "billing_reason": billing_reason,
        "hosted_invoice_url": hosted_invoice_url,
        "customer_address": customer_address,
        "status_transitions": {"paid_at": created if status == "paid" else None, "finalized_at": created},
        "lines": listing(lines),
        "parent": {
            "type": "subscription_details",
            "subscription_details": {"subscription": subscription_id, "metadata": {}},
        },
    }


def credit_note(
    credit_note_id: str = "cn_1",
    *,
    invoice_id: str = "in_1",
    lines: list[dict] | None = None,
    reason: str = "requested_by_customer",
) -> dict:
    """A credit note of a paid invoice (its amounts positive, as Stripe gives them). Without ``lines``, the
    whole default plan line (29.99 + 6.30)."""
    if lines is None:
        lines = [credit_note_line()]
    tax = sum(sum(t["amount"] for t in line["taxes"]) for line in lines)
    subtotal = sum(line["amount"] for line in lines)
    return {
        "id": credit_note_id,
        "object": "credit_note",
        "invoice": invoice_id,
        "number": f"ABCD-0001-CN-{credit_note_id[-2:]}",
        "status": "issued",
        "type": "post_payment",
        "reason": reason,
        "created": int(time.time()),
        "currency": "eur",
        "subtotal": subtotal,
        "total": subtotal + tax,
        "total_taxes": [{"amount": tax, "type": "tax_rate_details"}] if tax else [],
        "lines": listing(lines),
    }


def credit_note_line(
    line_id: str = "cnli_1", *, amount: int = 2999, tax: int = 630, invoice_line_item: str = "il_plan",
    description: str = "Starter",
) -> dict:
    return {
        "id": line_id,
        "object": "credit_note_line_item",
        "type": "invoice_line_item",
        "invoice_line_item": invoice_line_item,
        "amount": amount,
        "quantity": 1,
        "description": description,
        "taxes": (
            [{"amount": tax, "tax_behavior": "exclusive", "tax_rate_details": {"tax_rate": "txr_1"},
              "taxable_amount": amount, "type": "tax_rate_details"}]
            if tax
            else []
        ),
    }


def schedule(schedule_id: str = "sub_sched_1", *, subscription_id: str = "sub_1", status: str = "active") -> dict:
    """A subscription schedule made from a subscription: its first phase is the paid period."""
    return {
        "id": schedule_id,
        "object": "subscription_schedule",
        "status": status,
        "subscription": subscription_id,
        "end_behavior": "release",
        "phases": [{"start_date": MONTH_START, "end_date": MONTH_END, "items": []}],
    }


def checkout_session(
    session_id: str = "cs_test_1",
    *,
    metadata: dict | None = None,
    subscription_id: str | None = "sub_1",
    customer: str = "cus_1",
    payment_status: str = "paid",
    status: str = "complete",
) -> dict:
    return {
        "id": session_id,
        "object": "checkout.session",
        "mode": "subscription",
        "status": status,
        "payment_status": payment_status,
        "subscription": subscription_id,
        "customer": customer,
        "metadata": metadata or {},
    }


def payment_intent(
    pi_id: str = "pi_1",
    *,
    code: str = "card_declined",
    decline_code: str = "insufficient_funds",
    payment_method: str = "pm_old",
) -> dict:
    return {
        "id": pi_id,
        "object": "payment_intent",
        "status": "requires_payment_method",
        "last_payment_error": {
            "type": "card_error",
            "code": code,
            "decline_code": decline_code,
            "payment_method": {"id": payment_method, "object": "payment_method"},
        },
    }


def invoice_payment(pi_id: str = "pi_1", *, invoice_id: str = "in_1") -> dict:
    return {
        "id": f"inpay_{pi_id}",
        "object": "invoice_payment",
        "invoice": invoice_id,
        "status": "open",
        "created": int(time.time()),
        "payment": {"type": "payment_intent", "payment_intent": pi_id},
    }


def preview(*, amount_due: int = 1210, tax: int = 210) -> dict:
    return {
        "object": "invoice",
        "amount_due": amount_due,
        "subtotal": amount_due - tax,
        "total": amount_due,
        "total_taxes": [{"amount": tax, "type": "tax_rate_details"}] if tax else [],
        "currency": "eur",
        "lines": listing([]),
    }


# --- Webhook events --------------------------------------------------------------------------------

_events = itertools.count(1)


def event(event_type: str, obj: dict, *, event_id: str | None = None) -> dict:
    return {
        "id": event_id or f"evt_test_{next(_events)}",
        "object": "event",
        "api_version": "2026-09-30.endive",
        "type": event_type,
        "created": int(time.time()),
        "livemode": False,
        "data": {"object": obj},
    }


def signed(
    payload: dict, *, secret: str = WEBHOOK_SECRET, timestamp: int | None = None
) -> tuple[bytes, str]:
    """``payload`` as Stripe sends it, with its ``Stripe-Signature`` header (``t=…,v1=…``)."""
    body = json.dumps(payload)
    stamp = int(time.time()) if timestamp is None else timestamp
    signature = stripe.WebhookSignature._compute_signature(f"{stamp}.{body}", secret)
    return body.encode(), f"t={stamp},v1={signature}"


def card_error(
    code: str = "card_declined", decline_code: str = "insufficient_funds"
) -> stripe.CardError:
    return stripe.CardError(
        "Your card was declined.",
        param="",
        code=code,
        http_status=402,
        json_body={"error": {"code": code, "decline_code": decline_code}},
    )


def connection_error() -> stripe.APIConnectionError:
    return stripe.APIConnectionError("Could not connect to Stripe.")


def invalid_request(
    code: str = "resource_missing", message: str = "No such subscription"
) -> stripe.InvalidRequestError:
    return stripe.InvalidRequestError(message, param="id", code=code, http_status=404)
