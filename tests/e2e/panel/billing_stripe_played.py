"""BILLING-F11 and BILLING-F14 · The Stripe of ``billing-downgrade.spec.ts``: the panel's real routes and Stripe's real
webhook, with only Stripe doubled (``billing/tests/stripe_double.py``).

The panel's server has no Stripe in the e2e, so the spec hands the routes that call it to this process
(``page.route``). What the double answers comes from the database, so a downgrade that waits is held as the server
wrote it; the Plan rows get a Stripe price only while a call lasts, as the e2e's database has none.

From saas-next/, against the database of the run (development only, refused without ``DEBUG``), with the Hub the spec
plays at ``<hub_url>``: ``uv run python tests/e2e/panel/billing_stripe_played.py serve <hub_url>``. One process for the
whole spec (saas#328): Django starts once, says ``{"ready": true}``, and then answers each JSON line it reads on its
stdin with one JSON line, in order, until its stdin ends:

- ``{"command": "api", "email", "path", "body"}``: the route, as ``<email>`` signed in calls it → ``{"status", "body"}``;
- ``{"command": "arrive", "hub_id"}``: the paid period ended and Stripe's schedule started the phase of the plan that
  waits: its signed ``customer.subscription.updated`` → ``{"status", "body"}``;
- a call that fails → ``{"error": <its traceback>}``, and the next one is answered as usual.

Its stdout carries only those lines; whatever a call prints goes to its stderr.
"""

import json
import os
import sys
import traceback
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, redirect_stdout
from datetime import timedelta
from pathlib import Path
from typing import TextIO

SAAS_DIR = Path(__file__).resolve().parents[3]
HOST = "localhost:8001"
DAYS_OF_PERIOD = {"month": 30, "year": 365}


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _lines(held, plan_slug: str, interval: str, period: tuple[int, int]) -> list[dict]:
    """The items Stripe bills: the plan's, and the modules the business bought (those of its plan bill nothing)."""
    from apps.models import Module
    from billing.tests.stripe_double import item
    from hubs.models import SubscriptionItem

    bought = SubscriptionItem.objects.filter(subscription=held, source=SubscriptionItem.Source.PURCHASE)
    lines = [item("si_plan", f"price_{plan_slug}_{interval}", interval=interval, period=period)]
    for row in bought:
        module = Module.objects.get(slug=row.module_slug)
        price = module.stripe_price_id_monthly if interval == "month" else module.stripe_price_id_annual
        lines.append(item(row.stripe_item_id, price, interval=interval, period=period))
    return lines


def _live(subscription_id: str) -> dict:
    """The live subscription, as the database holds it."""
    from billing.models import PlanChangeSchedule
    from billing.tests.stripe_double import subscription
    from hubs.models import Subscription

    held = Subscription.objects.select_related("plan").get(stripe_subscription_id=subscription_id)
    pending = PlanChangeSchedule.objects.filter(hub_id=held.hub_id).first()
    period = (int(held.current_period_start.timestamp()), int(held.current_period_end.timestamp()))
    live = subscription(
        subscription_id,
        customer=held.stripe_customer_id,
        items=_lines(held, held.plan.slug, held.billing_interval, period),
        cancel_at_period_end=held.cancel_at_period_end,
    )
    return {**live, "schedule": pending.stripe_schedule_id if pending else None}


@contextmanager
def _stripe_played(hub_url: str) -> Iterator:
    """Stripe doubled, its test keys and the plans' prices in place, and everything back as it was afterwards."""
    from django.test import override_settings

    from billing import stripe_service
    from billing.tests.stripe_double import WEBHOOK_SECRET, StripeDouble, schedule
    from hubs.models import Plan

    double = StripeDouble()
    double.answer("subscriptions.retrieve", lambda call: _live(call.args[0]))
    double.answer(
        "subscription_schedules.create",
        lambda call: schedule(f"sub_sched_{call.params['from_subscription']}", subscription_id=call.params["from_subscription"]),
    )
    double.answer("subscription_schedules.update", schedule())
    double.answer("subscription_schedules.release", schedule(status="released"))
    prices = list(Plan.objects.values_list("pk", "stripe_price_id", "stripe_price_id_annual"))
    real_client = stripe_service.client
    stripe_service.client = lambda: double
    try:
        for plan in Plan.objects.filter(price_monthly__gt=0):
            Plan.objects.filter(pk=plan.pk).update(
                stripe_price_id=f"price_{plan.slug}_month", stripe_price_id_annual=f"price_{plan.slug}_year"
            )
        with override_settings(
            STRIPE_SECRET_KEY="rk_test_double", STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET, HUB_INTERNAL_URL=hub_url
        ):
            yield double
    finally:
        stripe_service.client = real_client
        for pk, month, year in prices:
            Plan.objects.filter(pk=pk).update(stripe_price_id=month, stripe_price_id_annual=year)


def _answer(response) -> dict:
    return {"status": response.status_code, "body": response.json()}


def api(email: str, path: str, body: dict, hub_url: str) -> dict:
    """``POST <path>`` of the panel as the account ``email``, answered as the route answers."""
    from django.contrib.auth import get_user_model
    from django.test import Client

    client = Client()
    client.force_login(get_user_model().objects.get(email=email))
    with _stripe_played(hub_url):
        response = client.post(path, json.dumps(body), content_type="application/json", HTTP_HOST=HOST)
    client.logout()
    return _answer(response)


def arrive(hub_id: str, hub_url: str) -> dict:
    """The paid period ended: the plan that waits starts, as Stripe says it, over the signed webhook."""
    from django.test import Client

    from billing.models import PlanChangeSchedule, WebhookEvent
    from billing.tests.stripe_double import event, signed, subscription
    from hubs.models import Subscription

    pending = PlanChangeSchedule.objects.get(hub_id=hub_id)
    held = Subscription.objects.get(hub_id=hub_id)
    start = held.current_period_end
    period = (int(start.timestamp()), int((start + timedelta(days=DAYS_OF_PERIOD[pending.interval])).timestamp()))
    live = {
        **subscription(
            held.stripe_subscription_id,
            customer=held.stripe_customer_id,
            items=_lines(held, pending.plan_slug, pending.interval, period),
        ),
        "schedule": pending.stripe_schedule_id,
    }
    # The ids are unique and the row goes: the webhook skips an event it has seen, and the e2e's database stays.
    event_id = f"evt_e2e_{uuid.uuid4().hex}"
    payload, signature = signed(event("customer.subscription.updated", live, event_id=event_id))
    with _stripe_played(hub_url) as double:
        double.answer("subscriptions.retrieve", live)
        response = Client().post(
            "/webhooks/stripe/", payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=signature, HTTP_HOST=HOST
        )
    WebhookEvent.objects.filter(event_id=event_id).delete()
    return _answer(response)


def _played(request: dict, hub_url: str) -> dict:
    match request:
        case {"command": "api", "email": email, "path": path, "body": body}:
            return api(email, path, body, hub_url)
        case {"command": "arrive", "hub_id": hub_id}:
            return arrive(hub_id, hub_url)
        case _:
            raise ValueError(f"no such call: {request!r}")


def _say(answers: TextIO, answer: dict) -> None:
    answers.write(json.dumps(answer) + "\n")
    answers.flush()


def serve(hub_url: str, requests: Iterable[str], answers: TextIO) -> None:
    """``{"ready": true}``, then one answer line per request line of ``requests``, in order, until they end."""
    _say(answers, {"ready": True})
    for line in requests:
        try:
            answer = _played(json.loads(line), hub_url)
        except Exception:
            # The spec waits for this line: it rejects that call with the traceback, and the next call still runs.
            answer = {"error": traceback.format_exc()}
        _say(answers, answer)


def main(argv: list[str]) -> None:
    setup_django()
    from django.conf import settings

    if not settings.DEBUG:
        sys.exit("billing_stripe_played.py only runs with DEBUG=True")
    match argv:
        case ["serve", hub_url]:
            answers = sys.stdout
            with redirect_stdout(sys.stderr):
                serve(hub_url, sys.stdin, answers)
        case _:
            sys.exit("usage: billing_stripe_played.py serve <hub_url>")


if __name__ == "__main__":
    main(sys.argv[1:])
