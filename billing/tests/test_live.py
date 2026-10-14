"""billing's live queries (``billing/live.py``): the Billing section re-runs after the COMMIT of what changes it.

The scope is the account (PLAN-SAAS §6): the webhook records an invoice in its payer's channel (or its
business owner's), so their Invoices list re-runs; Subscriptions re-runs with every change of a plan
(``hubs.subscription.changed``, recorded by ``hubs.subscription.apply``) and with an invoice not collected
(its «View the invoice»). The payment method is not live: it asks Stripe.
"""

from live.live_registry import live_registry

from billing import events
from hubs import events as hub_events


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_invoices_rerun_with_every_invoice_event():
    for name in events.INVOICES:
        assert "billing.invoice.list" in live_registry.affected([name]), name


def test_the_subscriptions_rerun_when_a_plan_or_an_unpaid_invoice_changes():
    for name in [hub_events.SUBSCRIPTION_CHANGED, events.PLAN_CANCELLED, events.PLAN_KEPT, events.INVOICE_RECORDED,
                 events.INVOICE_VOIDED]:
        assert "billing.subscription.list" in live_registry.affected([name]), name


def test_the_payment_method_is_not_live():
    assert not live_registry.is_subscribable("billing.payment_method.get")
