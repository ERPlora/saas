"""``python manage.py audit_stripe_webhooks``: does Stripe send our webhook every event it handles?

An endpoint pointed at a route that does not exist gets a 404 on every delivery until Stripe disables it. Only an
ENABLED endpoint counts, one on our host to a route we do not serve and one to another environment are problems, and
so is our route without an enabled endpoint. The events of our endpoint are compared with
``billing.services.webhook_dispatch.STRIPE_WEBHOOK_EVENTS``, the one list the webhook handles; what is missing and what is extra are
named. Without a usable Stripe key there is nothing to audit: it says so and exits 0. Stripe is the double: no network.
"""

from typing import get_args

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from stripe.params import WebhookEndpointCreateParams

from billing.services import webhook_dispatch
from billing.tests.stripe_double import connection_error, listing
from billing.tests.test_webhook_dispatch import HANDLERS

pytestmark = pytest.mark.django_db

OURS = "https://erplora.com/webhooks/stripe/"
#: Every event an endpoint can be sent, as Stripe's SDK lists them.
STRIPE_EVENTS = get_args(get_args(WebhookEndpointCreateParams.__annotations__["enabled_events"])[0])


@pytest.fixture(autouse=True)
def _host(settings):
    settings.PUBLIC_HOST = "erplora.com"


def endpoint(url=OURS, *, endpoint_id="we_1", status="enabled", events=None):
    return {
        "id": endpoint_id,
        "object": "webhook_endpoint",
        "url": url,
        "status": status,
        "enabled_events": list(webhook_dispatch.STRIPE_WEBHOOK_EVENTS if events is None else events),
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
    @pytest.fixture(autouse=True)
    def _handlers(self, monkeypatch):
        for module, names in HANDLERS:
            for name in names:
                monkeypatch.setattr(module, name, lambda *args, **kwargs: "handled")

    def test_every_event_of_the_list_reaches_a_handler(self):
        for event_type in webhook_dispatch.STRIPE_WEBHOOK_EVENTS:
            assert webhook_dispatch.process_stripe_event({"type": event_type, "data": {"object": {}}}) == "handled", event_type
        assert webhook_dispatch.process_stripe_event({"type": "payment_intent.created", "data": {"object": {}}}) == "ignored"

    def test_it_names_every_event_the_webhook_handles(self):
        """The other direction: an event handled but off the list passes the audit with the endpoint not sending it.
        ``invoice.payment_succeeded`` is the one handled on purpose without being subscribed (see the list)."""
        handled = {
            event_type
            for event_type in STRIPE_EVENTS
            if webhook_dispatch.process_stripe_event({"type": event_type, "data": {"object": {}}}) == "handled"
        }

        assert handled - {"invoice.payment_succeeded"} == set(webhook_dispatch.STRIPE_WEBHOOK_EVENTS)

    def test_it_names_each_event_once(self):
        assert len(webhook_dispatch.STRIPE_WEBHOOK_EVENTS) == len(set(webhook_dispatch.STRIPE_WEBHOOK_EVENTS))


class TestOurEndpoint:
    def test_exactly_the_list_is_ok(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint()]))

        out = audit()

        assert "we_1" in out and OURS in out
        assert out.rstrip().endswith(f"OK — {OURS} receives exactly the {len(webhook_dispatch.STRIPE_WEBHOOK_EVENTS)} events the webhook handles.")

    def test_a_missing_and_an_extra_event_are_named(self, stripe_double):
        events = [e for e in webhook_dispatch.STRIPE_WEBHOOK_EVENTS if e != "charge.refunded"] + ["payment_intent.succeeded"]
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


class TestWhatItSays:
    """Each problem names its endpoint and what to do, in one order: the endpoints that are not ours as Stripe lists
    them, how many deliver to our route, and the events of each of ours."""

    PRE = "https://pre.erplora.com/webhooks/stripe/"
    WRONG = "https://erplora.com/modules/webhooks/stripe/"
    OLD = "https://old.example.com/hook/"

    def test_the_problems_come_in_one_order(self, stripe_double):
        events = [e for e in webhook_dispatch.STRIPE_WEBHOOK_EVENTS if not e.startswith("invoice.")]
        short = sorted(set(webhook_dispatch.STRIPE_WEBHOOK_EVENTS) - set(events))
        assert len(short) > 1
        stripe_double.answer(
            "webhook_endpoints.list",
            listing(
                [
                    endpoint(self.PRE, endpoint_id="we_pre", events=["payout.paid"]),
                    endpoint(endpoint_id="we_short", events=["payout.paid", "account.updated", *events]),
                    endpoint(self.WRONG, endpoint_id="we_wrong", events=[]),
                    endpoint(endpoint_id="we_all", events=["*"]),
                    endpoint(self.OLD, endpoint_id="we_old"),
                ]
            ),
        )

        pre, wrong, old, several, short_of, every = refused().split("\n")

        assert pre.startswith(f"Stripe endpoint we_pre delivers to {self.PRE}, another environment than erplora.com:")
        assert wrong.startswith(f"Stripe endpoint we_wrong delivers to {self.WRONG}, a route this SaaS does not serve:")
        assert wrong.endswith(f"Point it at {OURS}.")
        assert old.startswith(f"Stripe endpoint we_old delivers to {self.OLD}, another environment than erplora.com:")
        assert several.startswith(f"2 enabled Stripe endpoints deliver to {OURS} (we_short, we_all):")
        assert short_of.startswith("Stripe endpoint we_short does not send the events the webhook handles")
        assert short_of.endswith(f"(missing: {', '.join(short)}; extra: account.updated, payout.paid).")
        assert every.startswith("Stripe endpoint we_all subscribes to every event (*):")
        assert f"exactly to the {len(webhook_dispatch.STRIPE_WEBHOOK_EVENTS)} of" in every

    def test_none_to_our_route_is_said_after_the_others(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(self.PRE, endpoint_id="we_pre")]))

        other, none = refused().split("\n")

        assert other.startswith("Stripe endpoint we_pre")
        assert none.startswith(f"No enabled Stripe endpoint delivers to {OURS}:")

    def test_only_missing_events_are_said(self, stripe_double):
        events = [e for e in webhook_dispatch.STRIPE_WEBHOOK_EVENTS if e != "charge.refunded"]
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(events=events)]))

        assert refused().endswith("(missing: charge.refunded).")

    def test_only_extra_events_are_said(self, stripe_double):
        events = [*webhook_dispatch.STRIPE_WEBHOOK_EVENTS, "payout.paid"]
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(events=events)]))

        assert refused().endswith("(extra: payout.paid).")

    def test_every_event_and_one_more_is_every_event(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([endpoint(events=["*", "charge.refunded"])]))

        assert "every event (*)" in refused()

    def test_an_endpoint_without_events_is_missing_them_all(self, stripe_double):
        stripe_double.answer("webhook_endpoints.list", listing([{**endpoint(), "enabled_events": None}]))

        assert refused().endswith(f"(missing: {', '.join(sorted(webhook_dispatch.STRIPE_WEBHOOK_EVENTS))}).")

    def test_an_endpoint_that_does_not_say_it_is_enabled_does_not_count(self, stripe_double):
        unsaid = {key: value for key, value in endpoint().items() if key != "status"}
        stripe_double.answer("webhook_endpoints.list", listing([unsaid]))

        assert refused().startswith(f"No enabled Stripe endpoint delivers to {OURS}")


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
