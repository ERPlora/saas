"""The body of ``POST /internal/platform/invoices`` (``services.platform_payload``) against the Hub's own schema of it.

The platform hub validates the body with its ``PlatformInvoiceIn`` (``apps/invoice/schemas/platform.py``, in the
Hub's code) and answers 422 ``internal.payload_invalid`` to one out of contract: the invoice is numbered here and stays
«issuing», never reaching VeriFactu. ``HubPlatformInvoiceIn`` below is that schema field for field (same names, types,
bounds and whitespace stripping, a key it does not know ignored); every invoice erplora.com records has to pass it.
A change of the Hub's schema is a change of this copy.

The period of a line travels as days: the Hub reads ``dt.date`` and refuses a moment of Stripe
(«2026-11-16T22:26:22+00:00») with 422, whatever the invoice.
"""

import datetime as dt
import json
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import pytest
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from billing import services
from billing.models import Invoice, InvoiceCounter
from billing.tests.stripe_double import credit_note, event, invoice, subscription
from billing.tests.test_invoice_discounts import captured_paid, deliver
from billing.tests.test_invoice_recording import running  # noqa: F401 - a ready business paying Starter monthly
from hubs.models import BillingProfile

pytestmark = pytest.mark.django_db

PLATFORM = r"^/internal/platform/invoices$"

# --- The Hub's schema (hub apps/invoice/schemas: MAX_AMOUNT, _text, Platform*In) -------------------------------

MAX_AMOUNT = 10**12


def _text(max_length: int, *, min_length: int = 0) -> Any:
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


class _HubPart(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HubRectificationIn(_HubPart):
    type: Literal["R1", "R2", "R3", "R4"]
    reason: _text(255) = ""


class HubBusinessIn(_HubPart):
    id: UUID | None = None
    name: _text(255) = ""


class HubRecipientIn(_HubPart):
    name: _text(255) = ""
    tax_id: _text(50) = ""
    tax_id_type: _text(20) = ""
    tax_id_verified: bool = False
    vat_consultation_number: _text(64) = ""
    address: _text(500) = ""
    city: _text(100) = ""
    postal_code: _text(20) = ""
    country: _text(2) = ""
    email: _text(254) = ""


class HubLineIn(_HubPart):
    position: int = Field(ge=1)
    description: _text(255) = ""
    item_kind: _text(20) = ""
    item_slug: _text(80) = ""
    quantity: int = Field(1, ge=1)
    proration: bool = False
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    tax_category: _text(80) | None = None
    tax_treatment: _text(20) = ""
    tax_rate: Decimal
    net_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    tax_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    total_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    discount_cents: int = Field(0, ge=0, le=MAX_AMOUNT)


class HubRectifiedIn(_HubPart):
    id: UUID
    number: _text(60) = ""
    issued_on: dt.date | None = None


class HubPlatformInvoiceIn(_HubPart):
    id: UUID
    kind: Literal["invoice", "credit_note"]
    series: Literal["ERP", "ERPR"]
    number: _text(60, min_length=1)
    issued_on: dt.date
    stripe_invoice_id: _text(255) = ""
    stripe_source_id: _text(255) = ""
    rectification: HubRectificationIn | None = None
    currency: _text(3, min_length=3) = "EUR"
    language: _text(8) = "es"
    net_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    tax_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    total_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT)
    tax_treatment: _text(20, min_length=1)
    tax_country: _text(2) = ""
    tax_rate: Decimal
    vat_included_reconciled: bool = False
    vat_included_because_unverified: bool = False
    business: HubBusinessIn
    recipient: HubRecipientIn
    lines: list[HubLineIn] = Field(min_length=1, max_length=200)
    rectifies: HubRectifiedIn | None = None

    @model_validator(mode="after")
    def _credit_note_names_its_invoice(self):
        if self.kind == "credit_note" and (self.rectifies is None or self.rectification is None):
            raise ValueError("A credit note carries its rectification and the invoice it rectifies.")
        return self


# --- Every invoice erplora.com records --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    # A credit note is read LIVE before it becomes a rectifying invoice.
    stripe_double.answer("credit_notes.retrieve", lambda call: {"id": call.args[0], "object": "credit_note", "status": "issued"})
    return stripe_double


def body_of(stripe_invoice_id: str, kind: str = Invoice.Kind.INVOICE) -> dict:
    """What the platform hub receives, as JSON travels."""
    recorded = Invoice.objects.get(kind=kind, stripe_invoice_id=stripe_invoice_id)
    return json.loads(json.dumps(services.platform_payload(recorded)))


@pytest.mark.usefixtures("running")
@pytest.mark.parametrize("tax_id", ["", "B12345678"], ids=["without a tax ID", "with a tax ID"])
class TestTheHubTakesIt:
    def payer(self, running, tax_id):
        BillingProfile.objects.filter(pk=running.billing_profile_id).update(tax_id=tax_id)

    def test_a_month_free_of_a_promo_code(self, running, tax_id):
        self.payer(running, tax_id)
        deliver(captured_paid(1))

        body = HubPlatformInvoiceIn.model_validate(body_of(captured_paid(1)["data"]["object"]["id"]))

        assert (body.total_cents, body.lines[0].discount_cents, body.recipient.tax_id) == (0, 2999, tax_id)
        assert (body.lines[0].period_start, body.lines[0].period_end) == (dt.date(2026, 11, 16), dt.date(2026, 12, 16))

    def test_an_invoice_paid_as_any_other(self, running, tax_id):
        self.payer(running, tax_id)
        deliver(event("invoice.paid", invoice("in_1", status="paid")))

        body = HubPlatformInvoiceIn.model_validate(body_of("in_1"))

        assert (body.total_cents, body.lines[0].discount_cents) == (3629, 0)
        assert body.lines[0].period_start is not None

    def test_its_credit_note(self, running, tax_id):
        self.payer(running, tax_id)
        deliver(event("invoice.paid", invoice("in_1", status="paid")))
        deliver(event("credit_note.created", credit_note()))

        body = HubPlatformInvoiceIn.model_validate(body_of("in_1", kind=Invoice.Kind.CREDIT_NOTE))

        assert (body.kind, body.series, body.total_cents) == ("credit_note", "ERPR", -3629)
        assert body.lines[0].discount_cents == 0


def test_a_moment_of_stripe_is_the_day_it_falls_on_in_spain():
    """23:30 UTC of 31 December is already 1 January in Madrid."""
    late = timezone.make_aware(dt.datetime(2026, 12, 31, 23, 30), dt.UTC)

    assert [services._day(value) for value in (late, dt.date(2026, 10, 1), None)] == ["2027-01-01", "2026-10-01", None]


# --- One the platform hub refused goes again, with its number ----------------------------------------------------


@pytest.mark.usefixtures("running")
def test_an_invoice_the_hub_refused_goes_again_with_the_same_number(hub_double, django_capture_on_commit_callbacks):
    from django.core.management import call_command

    hub_double.answer("POST", PLATFORM, 422, {"error": {"code": "internal.payload_invalid", "message": "The body is out of contract."}})
    with django_capture_on_commit_callbacks(execute=True):
        deliver(captured_paid(1))
    owed = Invoice.objects.get()
    assert owed.fiscal_status == "issuing"

    hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": "https://example.com/qr"})
    Invoice.objects.filter(pk=owed.pk).update(next_post_at=timezone.now() - dt.timedelta(minutes=1))
    call_command("reconcile_platform_invoices", stdout=None)

    again = Invoice.objects.get()
    assert (again.pk, again.number, again.fiscal_status) == (owed.pk, owed.number, "accepted")
    assert InvoiceCounter.objects.get().last_number == 1
    posted = [call.body for call in hub_double.calls_to("POST") if call.path == "/internal/platform/invoices"]
    assert [body["number"] for body in posted] == [owed.number, owed.number]
