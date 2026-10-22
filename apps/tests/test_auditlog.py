"""ACCOUNTS-F36 · The audit trail of what ERPlora sells of a paid app (django-auditlog; PLAN-SAAS §1.1: «en los
modelos de cuenta, cobro y fiscal»).

A ``Module`` row is a price the staff keep in the admin (its tier, its monthly and annual price, its Stripe prices):
who changed it and from what is logged, with only the logged fields serialized (#957) and without ``updated_at``. The
catalog of apps the Hub writes (``App``, ``AppDoc``, schema ``shared``) is not money and the Hub's worker rewrites it
on every start: not audited.
"""

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog

from apps.models import App, AppDoc, Module

pytestmark = pytest.mark.django_db


def test_the_price_of_a_paid_app_is_audited_and_the_catalog_the_hub_writes_is_not():
    assert auditlog.contains(Module)
    assert auditlog.get_serialize_options(Module)["serialize_auditlog_fields_only"] is True
    assert not auditlog.contains(App) and not auditlog.contains(AppDoc)


def test_a_price_the_staff_change_is_logged_with_what_it_was():
    module = Module.objects.create(slug="whatsapp_inbox", price_monthly_cents=900)

    module.price_monthly_cents = 1200
    module.save()

    entry = LogEntry.objects.get_for_object(module).get(action=LogEntry.Action.UPDATE)
    assert entry.changes_dict["price_monthly_cents"] == ["900", "1200"]
    assert "updated_at" not in set(entry.changes_dict) | set(entry.serialized_data["fields"])
