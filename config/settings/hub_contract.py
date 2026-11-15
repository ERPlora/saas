from urllib.parse import urlsplit

from config.settings.core import DEBUG, config

# Jump to a hub with a one-time code.

# The Hub signs POST /internal/auth/redeem with this secret (HMAC-SHA256 + timestamp).
INTERNAL_SHARED_SECRET = (
    config("INTERNAL_SHARED_SECRET", default="local-internal-shared-secret")
    if DEBUG
    else config("INTERNAL_SHARED_SECRET")
)
# The secret before a rotation (accounts/signing.py): still accepted, never used to sign. Empty
# outside a rotation.
INTERNAL_SHARED_SECRET_PREVIOUS = config("INTERNAL_SHARED_SECRET_PREVIOUS", default="")
HUB_CALLBACK_TEMPLATE = config(
    "HUB_CALLBACK_TEMPLATE",
    default="http://{slug}.localhost:8000/auth/callback"
    if DEBUG
    else "https://{slug}.erplora.com/auth/callback",
)
# CSP source of every hub's origin (`http://*.localhost:8000`): the auto-submitted form posts there.
_hub_callback = urlsplit(HUB_CALLBACK_TEMPLATE.format(slug="*"))
HUB_ORIGIN_PATTERN = f"{_hub_callback.scheme}://{_hub_callback.netloc}"
# The staff's jump from this admin to the Hub's (audience `hub-admin`): the
# callback of the platform host `hubs.erplora.com`, which only the Hub serves.
HUB_ADMIN_CALLBACK_URL = config(
    "HUB_ADMIN_CALLBACK_URL",
    default="http://hubs.localhost:8000/auth/callback"
    if DEBUG
    else "https://hubs.erplora.com/auth/callback",
)
_hub_admin_callback = urlsplit(HUB_ADMIN_CALLBACK_URL)
HUB_ADMIN_ORIGIN = f"{_hub_admin_callback.scheme}://{_hub_admin_callback.netloc}"
EXCHANGE_CODE_TTL_SECONDS = 60
# How long a pass the Hub signs for the way back to erplora.com opens (accounts/hub_pass.py).
HUB_PASS_MAX_AGE_SECONDS = 60
# Jumps one account may start in a while (accounts/handoff.py):
# past it, the error page asks to wait and no code is minted. django-ratelimit, over the default cache.
HUB_LOGIN_RATELIMIT = config("HUB_LOGIN_RATELIMIT", default="20/5m")
INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 300
# Where the SaaS calls the Hub's /internal/* (hubs.hub_client), signed with the same secret: the ALB
# answers 404 to it, so production uses the private name ERPlora/aws gives the Hub (Cloud Map).
HUB_INTERNAL_URL = config(
    "HUB_INTERNAL_URL",
    default="http://localhost:8000" if DEBUG else "http://hub.erplora.internal:8000",
)
