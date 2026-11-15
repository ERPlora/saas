from config.settings.core import config

# EU VAT (billing/): VIES, the European Commission's register of VAT numbers, asked through its REST
# endpoint as an identified requester (ERPlora's own VAT number, billing.CompanyConfig), the only way
# its answer carries the consultation number that proves it (billing/vies.py). Short timeout: a person
# waits for it (the forms, the checkout); a slow VIES is `unavailable`, and the sale pays VAT.
VIES_ENDPOINT = config(
    "VIES_ENDPOINT",
    default="https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number",
)
VIES_CONNECT_TIMEOUT_SECONDS = config("VIES_CONNECT_TIMEOUT_SECONDS", default=3.0, cast=float)
VIES_TIMEOUT_SECONDS = config("VIES_TIMEOUT_SECONDS", default=5.0, cast=float)
# One budget per person for every door that spends a VIES query (the panel's check, the admin's
# «Check now in VIES»), and one for everybody: each one is a request to the Commission under
# ERPlora's requester number. Only a query really sent spends.
VAT_CHECK_RATE = config("VAT_CHECK_RATE", default="20/m")
VAT_CHECK_GLOBAL_RATE = config("VAT_CHECK_GLOBAL_RATE", default="60/m")

# Stripe (billing/). Production holds a RESTRICTED live key (`rk_live_…`), local
# development test keys only; never a key in code. Without a secret key no payment starts (503
# `billing.payments_unavailable`) and the webhook answers 503. STRIPE_WEBHOOK_SECRET is the `whsec_…` of
# the one endpoint, `/webhooks/stripe/`; the publishable key travels to the SPA with each checkout. A
# call to Stripe waits STRIPE_TIMEOUT_SECONDS at most and is retried once (a command holds its
# transaction open meanwhile; Aurora ends one idle for 30 s). Prices: the Stripe ids on each Plan (admin)
# and apps.Module.
STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_TIMEOUT_SECONDS = config("STRIPE_TIMEOUT_SECONDS", default=10.0, cast=float)
# The Customer Portal's configuration (`bpc_…`): cards and receipts only; plan changes go through the panel,
# which puts our TaxRates. Empty = the portal does not open (503 `billing.portal_unavailable`).
STRIPE_PORTAL_CONFIGURATION = config("STRIPE_PORTAL_CONFIGURATION", default="")
# ERPlora's invoices are issued by its platform hub (billing): a live key charges nothing until this
# says the route is wired AND the Hub answers `GET /internal/platform/invoices/health`.
PLATFORM_INVOICING_ENABLED = config("PLATFORM_INVOICING_ENABLED", default=False, cast=bool)
# Promo codes grant trial days: a person may ask whether one is valid this often, so the codes
# cannot be guessed by brute force.
PROMO_CHECK_RATE = config("PROMO_CHECK_RATE", default="20/m")
