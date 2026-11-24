from config.settings.accounts import SUPPORT_EMAIL
from config.settings.core import DEBUG, config

# The fiscal seal's two .p12 slots (erplora/prod/fiscal/seal-{current,next}), base64 and password,
# loaded at startup by `saas` and `saas-cron`; empty = an empty slot (they are born
# empty and filled by hand; `saas-migrate` gets none). `manage.py report_seal_expiry` publishes the
# days left of the one that expires first.
FISCAL_SEAL_CURRENT_P12_BASE64 = config("FISCAL_SEAL_CURRENT_P12_BASE64", default="")
FISCAL_SEAL_CURRENT_PASSWORD = config("FISCAL_SEAL_CURRENT_PASSWORD", default="")
FISCAL_SEAL_NEXT_P12_BASE64 = config("FISCAL_SEAL_NEXT_P12_BASE64", default="")
FISCAL_SEAL_NEXT_PASSWORD = config("FISCAL_SEAL_NEXT_PASSWORD", default="")
# The fiscal gateway (fiscal_gateway/): presentations to the AEAT under way at once in
# one process; one more answers 503 `gateway_busy` and the Hub retries. 8 until it is measured in pre.
VERIFACTU_GATEWAY_CONCURRENCY = config("VERIFACTU_GATEWAY_CONCURRENCY", default=8, cast=int)
# The platform's hub (ERPlora's own invoices), named by the Hub as `hub`: the only one that
# presents through the seal without an authorisation, and only for the seal's holder. Its name and the one it had,
# so that renaming it stops no record. No business of the SaaS bears either: reserved slugs (live.slugs), or
# `check` fails (fiscal_gateway.E001).
PLATFORM_HUB_SLUGS = ("erp", "erplora")

# The documentation a hub sends so ERPlora files its VeriFactu records (fiscal/): the
# signed Anexo I, a copy of the signer's identity document and the rest, encrypted at rest with this Fernet
# key (fiscal/crypto.py; `check` says if it is no Fernet key, fiscal.E001). Required in production, like
# INTERNAL_SHARED_SECRET: a document stored with a lost key is lost. Local development uses a fixed key.
FISCAL_DOCUMENTS_KEY = (
    config("FISCAL_DOCUMENTS_KEY", default="bG9jYWwtZmlzY2FsLWRvY3VtZW50cy1rZXktMzJieXQ=")
    if DEBUG
    else config("FISCAL_DOCUMENTS_KEY")
)
# The review desk's mailbox (fiscal/emails.py): it hears of every authorisation that waits for a review.
FISCAL_REVIEW_EMAIL = config("FISCAL_REVIEW_EMAIL", default=SUPPORT_EMAIL)
# DATA_UPLOAD_MAX_MEMORY_SIZE stays Django's 2.5 MB for every view: the four documents of an authorisation
# (up to about 27 MB) have their own ceiling, read by their view alone (fiscal.internal.MAX_BODY_BYTES).
