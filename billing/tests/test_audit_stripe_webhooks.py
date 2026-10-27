"""``python manage.py audit_stripe_webhooks``: does Stripe send our webhook every event it handles? (BILLING-F39)

Ported from ERPlora/saas ``apps/core/stripe_webhooks.py`` and its command (origin/develop, saas#2402: PRE's module
endpoint pointed at a route that never existed, every delivery got a 404 and Stripe disabled it). The rules kept: only
an ENABLED endpoint counts, one on our host to a route we do not serve and one to another environment are problems,
and so is our route without an enabled endpoint. Added (PLAN-SAAS §1.1): the events of our endpoint are compared with
``billing.services.STRIPE_WEBHOOK_EVENTS``, the one list the webhook handles; what is missing and what is extra are
named. Without a usable Stripe key there is nothing to audit: it says so and exits 0. Stripe is the double: no network.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from billing import services
from billing.tests.stripe_double import connection_error, listing

pytestmark = pytest.mark.django_db

OURS = "https://erplora.com/webhooks/stripe/"


@pytest.fixture(autouse=True)
def _host(settings):
    settings.PUBLIC_HOST = "erplora.com"


def endpoint(url=OURS, *, endpoint_id="we_1", status="enabled", events=None):
    return {
        "id": endpoint_id,
        "object": "webhook_endpoint",
        "url": url,
        "status": status,
        "enabled_events": list(services.STRIPE_WEBHOOK_EVENTS if events is None else events),
    }


def audit(*args):
    from io import StringIO

    out = StringIO()
    call_command("audit_stripe_webhooks", *args, stdout=out)
    return out.getvalue()


def refused(*args) -> str:
    with pytest.raises(CommandError) as raised:
        audit(*args)
    return str(raised.value)


class TestTheOneList:
    HANDLERS = (
        "checkout_completed", "checkout_closed", "invoice_paid", "invoice_payment_failed", "invoice_voided",
        "credit_note_created", "charge_refunded", "subscription_updated", "subscription_deleted", "customer_updated",
    )

    def test_every_event_of_the_list_reaches_a_handler(self, monkeypatch):
        for name in self.HANDLERS:
            monkeypatch.setattr(services, name, lambda *args, **kwargs: "handled")

        for event_type in services.STRIPE_WEBHOOK_EVENTS:
            assert services.process_stripe_event({"type": event_type, "data": {"object": {}}}) == "handled", event_type
        assert services.process_stripe_event({"type": "payment_intent.created", "data": {"object": {}}}) == "ignored"

    def test_it_names_each_event_once(self):
        assert len(services.STRIPE_WEBHOOK_EVENTS) == len(set(services.STRIPE_WEBHOOK_EVENTS))


class TestOurEndpoint:
    def test_exactly_the_list_is_ok(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint()]))

        out = audit()

        assert "we_1" in out and OURS in out
        assert out.rstrip().endswith(f"OK — {OURS} receives exactly the {len(services.STRIPE_WEBHOOK_EVENTS)} events the webhook handles.")

    def test_a_missing_and_an_extra_event_are_named(self, stripe_double):
        events = [e for e in services.STRIPE_WEBHOOK_EVENTS if e != "charge.refunded"] + ["payment_intent.succeeded"]
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(events=events)]))

        problem = refused()

        assert "missing: charge.refunded" in problem
        assert "extra: payment_intent.succeeded" in problem

    def test_every_event_at_once_is_a_problem(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(events=["*"])]))

        assert "every event (*)" in refused()

    def test_no_enabled_endpoint_to_our_route_loses_its_events(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(status="disabled")]))

        assert f"No enabled Stripe endpoint delivers to {OURS}" in refused()

    def test_with_no_endpoint_at_all_too(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([]))

        assert f"No enabled Stripe endpoint delivers to {OURS}" in refused()


class TestTheOtherEndpoints:
    def test_two_enabled_to_our_route_are_one_too_many(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(), endpoint(endpoint_id="we_9")]))

        assert f"2 enabled Stripe endpoints deliver to {OURS} (we_1, we_9): keep one" in refused()

    def test_one_on_our_host_to_a_route_we_do_not_serve(self, stripe_double):
        wrong = "https://erplora.com/modules/webhooks/stripe/"
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(), endpoint(wrong, endpoint_id="we_2")]))

        problem = refused()

        assert f"we_2 delivers to {wrong}, a route this SaaS does not serve" in problem

    def test_one_to_another_environment(self, stripe_double):
        other = "https://pre.erplora.com/webhooks/stripe/"
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(), endpoint(other, endpoint_id="we_3")]))

        assert f"we_3 delivers to {other}, another environment" in refused()

    def test_a_disabled_one_delivers_nothing_and_does_not_count(self, stripe_double):
        other = "https://pre.erplora.com/webhooks/stripe/"
        stripe_double.answer(
            "webhook_endpoints.list", listing([endpoint(), endpoint(other, endpoint_id="we_3", status="disabled")])
        )

        assert audit().rstrip().endswith("events the webhook handles.")


class TestReadingStripe:
    def test_another_environment_is_audited_with_its_base_url(self, stripe_double):
        pre = "https://pre.erplora.com/webhooks/stripe/"
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(pre)]))

        assert f"OK — {pre} receives" in audit("--base-url", "https://pre.erplora.com/")

    def test_every_page_is_read(self, stripe_double):
        stale = endpoint("https://old.example.com/hook/", endpoint_id="we_0", status="disabled")
        stripe_double.answer(
            "webhook_endpoints.list", listing([stale], has_more=True), listing([endpoint()])
        )

        assert "OK —" in audit()
        first, second = stripe_double.calls_to("webhook_endpoints.list")
        assert first.params == {"limit": 100}
        assert second.params == {"limit": 100, "starting_after": "we_0"}

    def test_stripe_away_is_an_error_not_an_ok(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", connection_error())

        assert "The Stripe webhook endpoints could not be read" in refused()

    def test_without_a_stripe_key_there_is_nothing_to_audit(self, settings):
        settings.STRIPE_SECRET_KEY = ""

        assert "Stripe is not configured here" in audit()
