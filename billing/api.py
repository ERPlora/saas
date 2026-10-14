"""Ninja routes of billing: each route calls exactly one operation and holds no logic.

Under ``/api/billing/`` with the API's session auth (an anonymous visitor gets the 401 envelope); a POST
needs the CSRF token. No path parameters: the input is the query string (GET) or the body (POST).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from billing import queries, services
from billing.schemas import TaxPreviewIn, VatCheckIn

router = Router(tags=["billing"])


@bind(router, "billing.vat_check.run", "/billing/vat-check")
async def vat_check_run(request, data: VatCheckIn):
    return await run_operation(request, services.vat_check_run, data)


@bind(router, "billing.tax.preview", "/billing/tax-preview")
async def tax_preview(request, params: Query[TaxPreviewIn]):
    return await run_operation(request, queries.tax_preview, params)
