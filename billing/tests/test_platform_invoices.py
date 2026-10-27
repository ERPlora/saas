"""The legal invoice is issued by ERPlora's platform hub, not by the SaaS (PLAN-SAAS §4, ADR-0478; lot L3-C).

Once the webhook's transaction commits, the SaaS posts the invoice to hub-next's
``POST /internal/platform/invoices`` (signed like every ``/internal`` call, ``hubs.hub_client``), keyed by
the invoice's id (idempotent: posting it again answers what the Hub has). The platform hub chains it in
VeriFactu and answers its status and the QR; the SaaS stores them (``fiscal_status`` mirrors the Hub) and
never simulates them (working rules §2: VeriFactu is never simulated): with the Hub away the invoice stays
«issuing» and ``reconcile_platform_invoices`` posts it again; an issued one is asked
(``GET /internal/platform/invoices/{id}``) until the AEAT answers.

These tests drive the SaaS half against the Hub double (``hubs/tests/hub_double.py``), which verifies the
signature as the Hub will; its answers for the platform routes are given per test.
"""

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from billing import services
from billing.models import Invoice
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    credit_note,
    event,
    invoice,
    signed,
    subscription,
)
from hubs.models import Hub

pytestmark = pytest.mark.django_db

PLATFORM = r"^/internal/platform/invoices$"
QR = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B27593136&numserie=ERP-2026-00001"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    # A credit note is read LIVE before it becomes a rectifying invoice (a voided one never does, BILLING-F26).
    stripe_double.answer("credit_notes.retrieve", lambda call: {"id": call.args[0], "object": "credit_note", "status": "issued"})
    return stripe_double


@pytest.fixture
def running(shop):
    paid = pay(shop)
    Hub.objects.filter(pk=paid.pk).update(
        status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call=""
    )
    return Hub.objects.get(pk=paid.pk)


def deliver(payload, capture):
    body, header = signed(payload)
    with capture(execute=True):
        response = Client().post(
            "/webhooks/stripe/",
            body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=header,
            HTTP_HOST="localhost:8001",
        )
    assert response.status_code == 200, response.content
    return response.json()["status"]


def paid(invoice_id="in_1"):
    return event("invoice.paid", invoice(invoice_id, status="paid"))


def posts(hub_double):
    return [
        call
        for call in hub_double.calls_to("POST")
        if call.path == "/internal/platform/invoices"
    ]


class TestTheInvoiceReachesThePlatformHub:
    def test_it_is_posted_after_the_commit_signed(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})

        deliver(paid(), django_capture_on_commit_callbacks)

        [call] = posts(hub_double)
        assert call.signed_v2
        recorded = Invoice.objects.get()
        assert call.body["id"] == str(recorded.id)
        assert call.body["number"] == recorded.number

    def test_the_payload_is_the_whole_invoice(
        self, running, owner, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})

        deliver(paid(), django_capture_on_commit_callbacks)

        recorded = Invoice.objects.get()
        body = posts(hub_double)[0].body
        assert {
            key: body[key]
            for key in (
                "kind",
                "series",
                "number",
                "issued_on",
                "stripe_invoice_id",
                "currency",
                "language",
                "net_cents",
                "tax_cents",
                "total_cents",
                "tax_treatment",
                "tax_country",
                "tax_rate",
                "vat_included_reconciled",
                "vat_included_because_unverified",
                "rectifies",
            )
        } == {
            "kind": "invoice",
            "series": "ERP",
            "number": recorded.number,
            "issued_on": recorded.issued_on.isoformat(),
            "stripe_invoice_id": "in_1",
            "currency": "EUR",
            "language": "es",
            "net_cents": 2999,
            "tax_cents": 630,
            "total_cents": 3629,
            "tax_treatment": "domestic",
            "tax_country": "ES",
            "tax_rate": "21.00",
            "vat_included_reconciled": False,
            "vat_included_because_unverified": False,
            "rectifies": None,
        }
        assert body["business"] == {"id": str(running.id), "name": "Panadería López"}
        assert body["recipient"] == {
            "name": "Panadería López SL",
            "tax_id": "",
            "tax_id_type": "",
            "tax_id_verified": False,
            "vat_consultation_number": "",
            "address": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28001",
            "country": "ES",
            "email": owner.email,
        }
        [line] = body["lines"]
        assert {
            key: line[key]
            for key in (
                "position",
                "item_kind",
                "item_slug",
                "quantity",
                "proration",
                "tax_category",
                "tax_treatment",
                "tax_rate",
                "net_cents",
                "tax_cents",
                "total_cents",
            )
        } == {
            "position": 1,
            "item_kind": "plan",
            "item_slug": "starter",
            "quantity": 1,
            "proration": False,
            "tax_category": "service.saas_subscription",
            "tax_treatment": "domestic",
            "tax_rate": "21.00",
            "net_cents": 2999,
            "tax_cents": 630,
            "total_cents": 3629,
        }
        assert line["description"] and line["period_start"] and line["period_end"]

    def test_what_the_hub_answers_is_stored(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})

        deliver(paid(), django_capture_on_commit_callbacks)

        recorded = Invoice.objects.get()
        assert (recorded.fiscal_status, recorded.qr) == ("issued", QR)
        assert (
            recorded.post_attempts,
            recorded.next_post_at,
            recorded.last_post_error,
        ) == (1, None, "")
        assert recorded.fiscal_status_at is not None

    def test_a_credit_note_names_the_invoice_it_rectifies(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})
        deliver(paid(), django_capture_on_commit_callbacks)

        deliver(
            event("credit_note.created", credit_note()),
            django_capture_on_commit_callbacks,
        )

        original = Invoice.objects.get(kind="invoice")
        body = posts(hub_double)[-1].body
        assert (body["kind"], body["series"], body["total_cents"]) == (
            "credit_note",
            "ERPR",
            -3629,
        )
        assert body["rectifies"] == {
            "id": str(original.id),
            "number": original.number,
            "issued_on": original.issued_on.isoformat(),
        }


class TestTheHubAwayIsNeverSimulated:
    def test_the_hub_down_leaves_it_issuing_for_the_next_run(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer(
            "POST",
            PLATFORM,
            503,
            {"error": {"code": "unavailable", "message": "Down."}},
        )

        deliver(paid(), django_capture_on_commit_callbacks)

        recorded = Invoice.objects.get()
        assert (recorded.fiscal_status, recorded.qr, recorded.post_attempts) == (
            "issuing",
            "",
            1,
        )
        assert recorded.next_post_at > timezone.now()
        assert recorded.last_post_error

    def test_no_hub_at_all_leaves_it_issuing(
        self, running, offline_hub, django_capture_on_commit_callbacks
    ):
        deliver(paid(), django_capture_on_commit_callbacks)

        assert Invoice.objects.get().fiscal_status == "issuing"

    def test_a_refusal_is_kept_with_its_code(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer(
            "POST",
            PLATFORM,
            422,
            {
                "error": {
                    "code": "invalid_recipient",
                    "message": "The tax ID is malformed.",
                }
            },
        )

        deliver(paid(), django_capture_on_commit_callbacks)

        recorded = Invoice.objects.get()
        assert (recorded.fiscal_status, recorded.fiscal_error_code) == (
            "issuing",
            "invalid_recipient",
        )

    def test_posting_again_is_harmless(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        """The Hub keys it by the invoice's id: a second post answers what it has (Stripe-style idempotency)."""
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})
        deliver(paid(), django_capture_on_commit_callbacks)
        recorded = Invoice.objects.get()
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        assert services.post_platform_invoice(recorded.id) == services.POSTED

        bodies = [call.body for call in posts(hub_double)]
        assert bodies[0]["id"] == bodies[1]["id"]
        assert Invoice.objects.get().fiscal_status == "accepted"

    def test_an_unpaid_invoice_is_never_posted(self, running, hub_double):
        unpaid = Invoice.objects.create(
            stripe_invoice_id="in_open",
            hub=running,
            payment_status="open",
            net_cents=2999,
            tax_cents=630,
            total_cents=3629,
        )

        assert services.post_platform_invoice(unpaid.id) == services.NOTHING_TO_POST
        assert posts(hub_double) == []


class TestTheAnswerIsAskedUntilTheAeatSpeaks:
    def issued(self, running, hub_double, capture):
        hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})
        deliver(paid(), capture)
        return Invoice.objects.get()

    def test_an_issued_invoice_is_asked_for_its_status(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        recorded = self.issued(running, hub_double, django_capture_on_commit_callbacks)
        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{recorded.id}$",
            200,
            {"status": "accepted", "qr": QR},
        )

        assert services.refresh_platform_invoice(recorded.id) == "accepted"

        assert Invoice.objects.get().fiscal_status == "accepted"

    def test_a_rejection_keeps_its_reason(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        recorded = self.issued(running, hub_double, django_capture_on_commit_callbacks)
        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{recorded.id}$",
            200,
            {
                "status": "rejected",
                "qr": QR,
                "error": {"code": "1100", "message": "Valor del campo NIF incorrecto."},
            },
        )

        services.refresh_platform_invoice(recorded.id)

        recorded.refresh_from_db()
        assert (
            recorded.fiscal_status,
            recorded.fiscal_error_code,
            recorded.fiscal_error,
        ) == ("rejected", "1100", "Valor del campo NIF incorrecto.")

    def test_an_answer_the_saas_does_not_know_changes_nothing(
        self, running, hub_double, django_capture_on_commit_callbacks
    ):
        recorded = self.issued(running, hub_double, django_capture_on_commit_callbacks)
        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{recorded.id}$",
            200,
            {"status": "lost"},
        )

        services.refresh_platform_invoice(recorded.id)

        assert Invoice.objects.get().fiscal_status == "issued"


def test_the_backoff_doubles_and_has_a_ceiling():
    assert services.platform_backoff(1) == timedelta(minutes=15)
    assert services.platform_backoff(2) == timedelta(minutes=30)
    assert services.platform_backoff(20) == timedelta(hours=6)


def test_the_hub_client_signs_the_pdf_request(hub_double):
    from hubs import hub_client

    hub_double.answer("GET", r"/pdf$", 200, {"not": "a pdf"})

    hub_client.get_platform_invoice_pdf("0193a1b2-0000-7000-8000-000000000000")

    [call] = hub_double.calls_to("GET", "/pdf")
    assert call.signed_v2
    assert (
        call.path
        == "/internal/platform/invoices/0193a1b2-0000-7000-8000-000000000000/pdf"
    )


def test_the_body_travels_as_json(
    running, hub_double, django_capture_on_commit_callbacks
):
    hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})

    deliver(paid(), django_capture_on_commit_callbacks)

    assert json.loads(posts(hub_double)[0].raw)["number"].startswith("ERP-")


def test_the_payer_is_told_once_the_platform_hub_issues_it(running, hub_double, django_capture_on_commit_callbacks):
    from django.core import mail

    hub_double.answer("POST", PLATFORM, 201, {"status": "issued", "qr": QR})
    deliver(paid(), django_capture_on_commit_callbacks)
    recorded = Invoice.objects.get()
    hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})
    with django_capture_on_commit_callbacks(execute=True):
        services.post_platform_invoice(recorded.id)

    assert [message.subject for message in mail.outbox] == [f"Factura {recorded.number} de ERPlora"]
    assert Invoice.objects.get().emailed_at is not None


def test_nobody_is_told_while_it_is_not_issued(running, hub_double, django_capture_on_commit_callbacks):
    from django.core import mail

    hub_double.answer("POST", PLATFORM, 503, {})

    deliver(paid(), django_capture_on_commit_callbacks)

    assert mail.outbox == []
