"""Django admin of billing, one module per concern: VAT (``tax``), the promo codes (``promo_codes``), the payment
records (``payment_records``), ERPlora's invoices with the billing report (``invoices``) and the paying customers
(``paying_customers``)."""

# Importing a module registers its admins, in this order.
from billing.admin import tax
from billing.admin import promo_codes
from billing.admin import payment_records
from billing.admin import invoices
from billing.admin import paying_customers
