"""Input and output schemas of billing's operations (OpenAPI, the 422's ``fields``).

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from billing.schemas.invoices import InvoiceListIn``).
"""

# The ``as`` tells ruff the import is kept on purpose: importing the package loads every schema.
from billing.schemas import common as common
from billing.schemas import tax as tax
from billing.schemas import discounts as discounts
from billing.schemas import promo_codes as promo_codes
from billing.schemas import checkout as checkout
from billing.schemas import subscription_changes as subscription_changes
from billing.schemas import stripe_pages as stripe_pages
from billing.schemas import store as store
from billing.schemas import invoices as invoices
from billing.schemas import invoice_records as invoice_records
from billing.schemas import subscriptions as subscriptions
from billing.schemas import payment_methods as payment_methods
