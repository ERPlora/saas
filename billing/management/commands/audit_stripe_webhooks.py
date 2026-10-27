"""``python manage.py audit_stripe_webhooks [--base-url URL]``: does Stripe send our webhook every event it handles?
(BILLING-F39)

Ported from ERPlora/saas ``apps/core/stripe_webhooks.py`` and its command (origin/develop, saas#2402): the route a
Stripe endpoint delivers to lives in Stripe and the events it sends are ticked there by hand (PLAN-SAAS §4, «A mano
en el panel de Stripe»), so nothing else notices an endpoint pointed at the wrong route, disabled after its 404s, or
one event short. Only an ENABLED endpoint counts (a disabled one delivers nothing). Problems: an endpoint on our host
to a route we do not serve, one to another environment, more than one to our route (one ``whsec_`` fits
``STRIPE_WEBHOOK_SECRET``), none to it, and ours sending other events than ``billing.services.STRIPE_WEBHOOK_EVENTS``
(what is missing and what is extra, by name; ``*`` is every event). The daily scheduled task's door and the human's:
it exits non-zero with the problems, so the ``task_failed`` alarm tells the team. Without a usable Stripe key there
is nothing to audit: it says so and exits 0. The restricted live key needs read access to webhook endpoints.
"""

from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from billing import services, stripe_service


def _target(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return (parts.hostname or "").lower(), parts.path or "/"


def endpoint_problems(endpoints: list[dict], url: str, events: tuple[str, ...]) -> list[str]:
    """What is wrong between the account's ``endpoints`` and our webhook at ``url`` that handles ``events``."""
    host, _ = _target(url)
    problems: list[str] = []
    ours: list[dict] = []
    for endpoint in endpoints:
        if endpoint.get("status") != "enabled":
            continue
        target = _target(endpoint.get("url") or "")
        if target == _target(url):
            ours.append(endpoint)
        elif target[0] == host:
            problems.append(
                f"Stripe endpoint {endpoint['id']} delivers to {endpoint['url']}, a route this SaaS does not serve: "
                f"every delivery gets a 404 and Stripe disables it. Point it at {url}."
            )
        else:
            problems.append(
                f"Stripe endpoint {endpoint['id']} delivers to {endpoint['url']}, another environment than {host}: "
                "it rejects the events this account signs. Delete it from this Stripe account."
            )
    if not ours:
        problems.append(
            f"No enabled Stripe endpoint delivers to {url}: its events are lost. Create it in Stripe (or enable it) "
            "with the events of billing.services.STRIPE_WEBHOOK_EVENTS and put its whsec_ in STRIPE_WEBHOOK_SECRET."
        )
    elif len(ours) > 1:
        problems.append(
            f"{len(ours)} enabled Stripe endpoints deliver to {url} ({', '.join(e['id'] for e in ours)}): keep one, "
            "only its whsec_ fits STRIPE_WEBHOOK_SECRET and the others' deliveries are refused."
        )
    wanted = set(events)
    for endpoint in ours:
        enabled = set(endpoint.get("enabled_events") or [])
        if "*" in enabled:
            problems.append(
                f"Stripe endpoint {endpoint['id']} subscribes to every event (*): subscribe it exactly to the "
                f"{len(events)} of billing.services.STRIPE_WEBHOOK_EVENTS."
            )
            continue
        missing, extra = sorted(wanted - enabled), sorted(enabled - wanted)
        if missing or extra:
            found = ([f"missing: {', '.join(missing)}"] if missing else []) + (
                [f"extra: {', '.join(extra)}"] if extra else []
            )
            problems.append(
                f"Stripe endpoint {endpoint['id']} does not send the events the webhook handles ({'; '.join(found)})."
            )
    return problems


class Command(BaseCommand):
    help = "Check that Stripe sends our webhook exactly the events it handles (exits non-zero when it does not)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url", default=None, help="Environment to audit (default: https://<PUBLIC_HOST>)."
        )

    def handle(self, *args, **options):
        base_url = (options["base_url"] or f"https://{settings.PUBLIC_HOST}").rstrip("/")
        url = f"{base_url}{reverse('stripe_webhook')}"
        try:
            endpoints = stripe_service.webhook_endpoints()
        except stripe_service.StripeNotConfigured:
            self.stdout.write(
                self.style.WARNING("Stripe is not configured here (no usable STRIPE_SECRET_KEY): nothing to audit.")
            )
            return
        except (stripe_service.StripeUnavailable, stripe_service.StripeRefused) as error:
            raise CommandError(f"The Stripe webhook endpoints could not be read: {error}") from error

        for endpoint in endpoints:
            self.stdout.write(f"{endpoint['id']}  {endpoint.get('status', ''):<8}  {endpoint.get('url', '')}")

        problems = endpoint_problems(endpoints, url, services.STRIPE_WEBHOOK_EVENTS)
        if problems:
            raise CommandError("\n".join(problems))

        self.stdout.write(
            self.style.SUCCESS(
                f"OK — {url} receives exactly the {len(services.STRIPE_WEBHOOK_EVENTS)} events the webhook handles."
            )
        )
