"""Ninja routes of billing: each route calls exactly one operation and holds no logic.

Under ``/api/billing/`` with the API's session auth (an anonymous visitor gets the 401 envelope); a POST
needs the CSRF token. No path parameters: the input is the query string (GET) or the body (POST). What a
business pays (lot L2-B) is its owner's: each operation checks the role. Stripe's webhook is not here: it is
``billing.webhooks`` (Stripe signs it; no session).

The Billing section (lot L3-C): ERPlora's invoices (list, detail, the PDF of the platform hub, the CSV of the
filtered list and «Pay»), the subscriptions and the payment details. The PDF and the CSV are answered as the
file itself (``Content-Disposition: attachment``); the operation returns its name, type and bytes.
"""

from django.http import HttpResponse
from live.ninja import bind, run_operation
from ninja import Query, Router

from billing import queries, services
from billing.schemas import (
    CheckoutConfirmIn,
    CheckoutStartIn,
    HubIn,
    InvoiceByIdIn,
    InvoiceFilterIn,
    InvoiceListIn,
    InvoicePayIn,
    PaymentMethodIn,
    SubscriptionListIn,
    ModuleIn,
    PlanChangeIn,
    PortalOpenIn,
    PromoCheckIn,
    StoreCatalogIn,
    TaxPreviewIn,
    VatCheckIn,
)

router = Router(tags=["billing"])


@bind(router, "billing.vat_check.run", "/billing/vat-check")
async def vat_check_run(request, data: VatCheckIn):
    return await run_operation(request, services.vat_check_run, data)


@bind(router, "billing.tax.preview", "/billing/tax-preview")
async def tax_preview(request, params: Query[TaxPreviewIn]):
    return await run_operation(request, queries.tax_preview, params)


@bind(router, "billing.promo.check", "/billing/promo-check")
async def promo_check(request, params: Query[PromoCheckIn]):
    return await run_operation(request, queries.promo_check, params)


@bind(router, "billing.checkout.start", "/billing/checkout/start")
async def checkout_start(request, data: CheckoutStartIn):
    return await run_operation(request, services.checkout_start, data)


@bind(router, "billing.checkout.confirm", "/billing/checkout/confirm")
async def checkout_confirm(request, data: CheckoutConfirmIn):
    return await run_operation(request, services.checkout_confirm, data)


@bind(router, "billing.plan.change", "/billing/plan/change")
async def plan_change(request, data: PlanChangeIn):
    return await run_operation(request, services.plan_change, data)


@bind(router, "billing.plan.cancel", "/billing/plan/cancel")
async def plan_cancel(request, data: HubIn):
    return await run_operation(request, services.plan_cancel, data)


@bind(router, "billing.plan.keep", "/billing/plan/keep")
async def plan_keep(request, data: HubIn):
    return await run_operation(request, services.plan_keep, data)


@bind(router, "billing.module.cancel", "/billing/module/cancel")
async def module_cancel(request, data: ModuleIn):
    return await run_operation(request, services.module_cancel, data)


@bind(router, "billing.module.keep", "/billing/module/keep")
async def module_keep(request, data: ModuleIn):
    return await run_operation(request, services.module_keep, data)


@bind(router, "billing.portal.open", "/billing/portal")
async def portal_open(request, data: PortalOpenIn):
    return await run_operation(request, services.portal_open, data)


@bind(router, "billing.store.catalog", "/billing/store")
async def store_catalog(request, params: Query[StoreCatalogIn]):
    return await run_operation(request, queries.store_catalog, params)


# --- The Billing section (lot L3-C) --------------------------------------------------------------------


def _file(document) -> HttpResponse:
    """A document the operation returned, answered as the file itself."""
    response = HttpResponse(document.content, content_type=document.content_type)
    response["Content-Disposition"] = f'attachment; filename="{document.filename}"'
    return response


def _binary(content_type: str) -> dict:
    """The file in the route's 200: keyed by the int ``200``, as ninja keys its own, so the two merge into one
    response (the text ``"200"`` wrote the key twice in /api/openapi.json)."""
    return {"responses": {200: {"content": {content_type: {"schema": {"type": "string", "format": "binary"}}}}}}


@bind(router, "billing.invoice.list", "/billing/invoices")
async def invoice_list(request, params: Query[InvoiceListIn]):
    return await run_operation(request, queries.invoice_list, params)


@bind(router, "billing.invoice.get", "/billing/invoices/detail")
async def invoice_get(request, params: Query[InvoiceByIdIn]):
    return await run_operation(request, queries.invoice_get, params)


@bind(router, "billing.invoice.pdf", "/billing/invoices/pdf", openapi_extra=_binary("application/pdf"))
async def invoice_pdf(request, params: Query[InvoiceByIdIn]):
    return _file(await run_operation(request, queries.invoice_pdf, params))


@bind(router, "billing.invoice.csv", "/billing/invoices/csv", openapi_extra=_binary("text/csv"))
async def invoice_csv(request, params: Query[InvoiceFilterIn]):
    return _file(await run_operation(request, queries.invoice_csv, params))


@bind(router, "billing.invoice.pay", "/billing/invoices/pay")
async def invoice_pay(request, data: InvoicePayIn):
    return await run_operation(request, services.invoice_pay, data)


@bind(router, "billing.subscription.list", "/billing/subscriptions")
async def subscription_list(request, params: Query[SubscriptionListIn]):
    return await run_operation(request, queries.subscription_list, params)


@bind(router, "billing.payment_method.get", "/billing/payment-method")
async def payment_method_get(request, params: Query[PaymentMethodIn]):
    return await run_operation(request, queries.payment_method_get, params)

