"""``POST /webhooks/stripe/``: Stripe's single webhook (PLAN-SAAS §4; lot L2-B).

Ported from ERPlora/saas ``hubs/main/webhooks.py`` (``stripe_webhook``, origin/develop), whose four routes
(hub plans, modules, Connect, assistant) are one now. A plain Django view, as the ``/internal`` doors
(``hubs/internal.py``): Stripe signs the body (``Stripe-Signature``), so no session, no CSRF and no ninja.

1. The signature is Stripe's (``billing.stripe_service.construct_event``): anything else is 400; without
   ``STRIPE_WEBHOOK_SECRET``, 503 (Stripe retries for three days).
2. The event is claimed (``billing.services.claim_event``): processed already → 200 ``duplicate``; another
   delivery processing it → 409 (Stripe retries; if that one fails, the retry processes it).
3. ``billing.services.process_stripe_event`` reads the LIVE subscription and writes it through
   ``hubs.subscription.apply``. A failure is 500 and stays claimable: Stripe's retry processes it again.

Answers ``{"status": <outcome>, "event_id"}``. Events to subscribe in Stripe: ``checkout.session.completed``,
``checkout.session.async_payment_succeeded``, ``checkout.session.async_payment_failed``,
``checkout.session.expired``, ``invoice.paid``, ``invoice.payment_failed``, ``customer.subscription.created``,
``customer.subscription.updated``, ``customer.subscription.deleted`` and ``customer.updated``; and, for
ERPlora's invoices (lot L3-C), ``invoice.voided``, ``invoice.marked_uncollectible``, ``credit_note.created`` and
``charge.refunded``. A paid invoice, a credit note or a refund that cannot be invoiced yet (its business or
the invoice it rectifies unknown, VIES down with no proof on file, lines that do not add up) is a 500: Stripe
retries it, nothing is forgotten.
"""

import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from billing import services, stripe_service

logger = logging.getLogger("billing.webhooks")


@csrf_exempt
@never_cache
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        response = JsonResponse({"status": "method_not_allowed"}, status=405)
        response["Allow"] = "POST"
        return response
    try:
        event = stripe_service.construct_event(
            request.body, request.headers.get("Stripe-Signature")
        )
    except stripe_service.StripeNotConfigured:
        logger.error(
            "[STRIPE WEBHOOK] STRIPE_WEBHOOK_SECRET is empty: the event waits for Stripe's retry"
        )
        return JsonResponse({"status": "unavailable"}, status=503)
    except stripe_service.InvalidWebhook as invalid:
        logger.warning("[STRIPE WEBHOOK] Refused: %s", invalid)
        return JsonResponse({"status": "invalid_signature"}, status=400)
    event_id, event_type = event["id"], event["type"]
    claim = services.claim_event(event_id, event_type)
    if claim == services.DUPLICATE:
        return JsonResponse({"status": "duplicate", "event_id": event_id})
    if claim == services.IN_PROGRESS:
        return JsonResponse({"status": "in_progress", "event_id": event_id}, status=409)
    try:
        outcome = services.process_stripe_event(event)
    except Exception as failure:  # noqa: BLE001 - recorded, answered 500: Stripe's retry processes it again
        logger.exception("[STRIPE WEBHOOK] %s (%s) failed", event_type, event_id)
        services.finish_event(
            event_id, success=False, outcome="error", error=str(failure)
        )
        return JsonResponse({"status": "error", "event_id": event_id}, status=500)
    services.finish_event(event_id, success=True, outcome=outcome)
    logger.info("[STRIPE WEBHOOK] %s (%s): %s", event_type, event_id, outcome)
    return JsonResponse({"status": outcome, "event_id": event_id})
