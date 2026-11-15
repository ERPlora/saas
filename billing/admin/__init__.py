"""Django admin of billing, one module per concern: VAT (``tax``), the payment records (``payment_records``) and
ERPlora's invoices with the billing report (``invoices``)."""

# Importing a module registers its admins, in this order.
from billing.admin import tax
from billing.admin import payment_records
from billing.admin import invoices
