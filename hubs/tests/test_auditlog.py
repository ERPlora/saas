"""ACCOUNTS-F36 · The audit trail of what a business pays and who pays it (django-auditlog; PLAN-SAAS §1.1: «en los
modelos de cuenta, cobro y fiscal»).

Ported from ERPlora/saas ``apps/dashboard/billing/auditlog.py`` (#970, its ``Subscription``): the subscription of a
business (plan, status, the Stripe that renews it, an unpaid renewal), the paid apps it carries, its payer's details
and the plans' prices the staff keep, with only the logged fields serialized (#957). Never written: the link that opens
an unpaid Stripe invoice to whoever holds it, and ``updated_at``. The rest of ``hubs`` (the business, its people, its
usage) is not money: the access a person has travels in ``accounts.HubMembership``, already audited.
"""

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.utils import timezone

from hubs.models import BillingProfile, Plan, Subscription, SubscriptionItem

pytestmark = pytest.mark.django_db

MONEY = {Plan, BillingProfile, Subscription, SubscriptionItem}
STRIPE_LINK = "https://invoice.stripe.com/i/acct_never_logged"


def _entries_for(instance):
    return LogEntry.objects.get_for_object(instance)


def _fields_written(entry) -> set[str]:
    return set(entry.changes_dict) | set(entry.serialized_data["fields"])


def test_the_money_models_are_audited_with_only_their_logged_fields():
    assert all(auditlog.contains(model) for model in MONEY)
    assert all(auditlog.get_serialize_options(model)["serialize_auditlog_fields_only"] for model in MONEY)


def test_an_unpaid_renewal_is_logged_without_the_link_to_its_stripe_invoice(business):
    subscription = business.subscription

    subscription.status, subscription.unpaid_since = Subscription.Status.PAST_DUE, timezone.now()
    subscription.unpaid_invoice_url = STRIPE_LINK
    subscription.save()

    entry = _entries_for(subscription).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
    assert entry.changes_dict["status"][1] == "past_due"
    assert not {"unpaid_invoice_url", "updated_at"} & _fields_written(entry)
    assert STRIPE_LINK not in " ".join(f"{e.changes} {e.serialized_data}" for e in _entries_for(subscription))


def test_a_paid_app_of_the_subscription_is_logged(business):
    item = SubscriptionItem.objects.create(subscription=business.subscription, module_slug="inventory", stripe_item_id="si_1")

    pk = item.pk  # delete() empties it
    item.delete()

    entries = LogEntry.objects.get_for_model(SubscriptionItem).filter(object_pk=str(pk))
    assert list(entries.values_list("action", flat=True)) == [LogEntry.Action.DELETE, LogEntry.Action.CREATE]
    assert "updated_at" not in _fields_written(entries.get(action=LogEntry.Action.CREATE))


def test_the_payers_details_are_logged(business):
    profile = BillingProfile.objects.get(pk=business.billing_profile_id)

    profile.tax_id = "B12345678"
    profile.save()

    entry = _entries_for(profile).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
    assert entry.changes_dict["tax_id"][1] == "B12345678"
    assert "updated_at" not in _fields_written(entry)


def test_a_price_the_staff_change_is_logged(plans):
    plan = Plan.objects.get(slug="starter")
    before = str(plan.price_monthly)

    plan.price_monthly += 1
    plan.save()

    entry = _entries_for(plan).get(action=LogEntry.Action.UPDATE)
    assert entry.changes_dict["price_monthly"][0] == before
    assert "updated_at" not in _fields_written(entry)
