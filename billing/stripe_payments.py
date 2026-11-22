"""What Stripe collected for an invoice and what it gave back: the invoice a payment paid, the refunds of an invoice
or a charge, the card that pays and why a payment failed."""

from billing import stripe_service


def invoice_paid_by(payment_intent_id: str) -> str | None:
    """The Stripe invoice a PaymentIntent paid, or ``None`` (a charge of no invoice)."""
    payments = stripe_service._call(
        stripe_service.client().v1.invoice_payments.list,
        params={"payment": {"type": "payment_intent", "payment_intent": payment_intent_id}, "limit": 10},
    )["data"]
    for payment in payments:
        found = payment.get("invoice")
        if found:
            return found["id"] if isinstance(found, dict) else found
    return None


def refund_invoice(invoice_id: str, *, key: str, metadata: dict) -> int:
    """Give back in full what ``invoice_id`` collected (each paid PaymentIntent of it), as a refund ``charge.refunded``
    turns into a rectifying invoice; the cents refunded (0: nothing was charged). ``key`` makes each refund
    idempotent (``<key>-<payment intent>``); a charge Stripe says is already refunded counts as refunded."""
    payments = stripe_service._call(
        stripe_service.client().v1.invoice_payments.list, params={"invoice": invoice_id, "limit": 10}
    )["data"]
    refunded = 0
    for payment in payments:
        intent = (payment.get("payment") or {}).get("payment_intent")
        if payment.get("status") != "paid" or not intent or not payment.get("amount_paid"):
            continue
        if isinstance(intent, dict):
            intent = intent["id"]
        try:
            stripe_service._call(
                stripe_service.client().v1.refunds.create,
                params={"payment_intent": intent, "reason": "requested_by_customer", "metadata": metadata},
                idempotency_key=f"{key}-{intent}",
            )
        except stripe_service.StripeRefused as refused:
            if refused.code != "charge_already_refunded":
                raise
        refunded += int(payment["amount_paid"])
    return refunded


def charge_refunds(charge_id: str) -> list[dict]:
    """Every refund of a charge."""
    params: dict = {"charge": charge_id, "limit": 100}
    found: list[dict] = []
    while True:
        page = stripe_service._call(stripe_service.client().v1.refunds.list, params=params)
        found += page["data"]
        if not page.get("has_more") or not page["data"]:
            return found
        params = {**params, "starting_after": page["data"][-1]["id"]}


def credit_note_refund_ids(invoice_id: str) -> set[str]:
    """The refunds the credit notes of an invoice made (``refunds[].refund`` since the 2025 API, ``refund``
    before): those are the credit notes' to rectify, not a refund's."""
    notes = stripe_service._call(
        stripe_service.client().v1.credit_notes.list, params={"invoice": invoice_id, "limit": 100}
    )["data"]
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
        live = stripe_service._call(
            stripe_service.client().v1.subscriptions.retrieve,
            subscription_id,
            params={"expand": ["default_payment_method"]},
        )
        method = live.get("default_payment_method")
    if not isinstance(method, dict) and customer_id:
        customer = stripe_service._call(
            stripe_service.client().v1.customers.retrieve,
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
    payments = stripe_service._call(
        stripe_service.client().v1.invoice_payments.list, params={"invoice": invoice_id, "limit": 10}
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
    error = stripe_service._call(stripe_service.client().v1.payment_intents.retrieve, intent_id).get(
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
