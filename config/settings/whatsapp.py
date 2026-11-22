from config.settings.core import DEBUG, config
from config.settings.public import PUBLIC_HOST

# WhatsApp, erplora.com's side (whatsapp/): Meta's app («ERPlora Inbox»), its
# Embedded Signup configuration and its webhook. Empty = WhatsApp is off, visibly: the webhook answers 503 and the
# Hub's doors whatsapp.not_configured (`check --deploy` warns, whatsapp.W001). The secrets come from the
# environment (Secrets Manager in AWS), never from code.
WHATSAPP_APP_ID = config("WHATSAPP_APP_ID", default="")
WHATSAPP_APP_SECRET = config("WHATSAPP_APP_SECRET", default="")
WHATSAPP_VERIFY_TOKEN = config("WHATSAPP_VERIFY_TOKEN", default="")
WHATSAPP_CONFIG_ID = config("WHATSAPP_CONFIG_ID", default="")
# The version of Meta's Graph API every call names.
WHATSAPP_GRAPH_VERSION = config("WHATSAPP_GRAPH_VERSION", default="v25.0")
# The key of the credentials kept at rest (Meta's, whatsapp/crypto.py; rotated by assistant/crypto.py; Fernet);
# during a rotation the previous one still opens what it closed. Local development uses a fixed key; elsewhere it comes from the environment, and
# without it no number can be connected.
FERNET_KEY = config("FERNET_KEY", default="yh5h4Yur2lIgWp9ZxkyLt1BrQfFVrwLH4WhIHCRwXXA=" if DEBUG else "")
FERNET_KEY_PREVIOUS = config("FERNET_KEY_PREVIOUS", default="")
# Where the people of a business open a customer's attachment (`/whatsapp/media/<id>`): erplora.com's own origin,
# the only one the Hub accepts for it (its SAAS_URL).
# The largest notice of Meta's webhook read (a chunk of the 180 days of history included); a larger one is 413.
WHATSAPP_WEBHOOK_MAX_BYTES = config("WHATSAPP_WEBHOOK_MAX_BYTES", default=10 * 1024 * 1024, cast=int)
WHATSAPP_MEDIA_BASE_URL = config(
    "WHATSAPP_MEDIA_BASE_URL", default="http://localhost:8001" if DEBUG else f"https://{PUBLIC_HOST}"
).rstrip("/")
# Where Meta's window (Embedded Signup) brings its one-time code back (`/whatsapp/return`, whatsapp/signup_return.py):
# erplora.com's own page, from the origin the Hub accepts it (its SAAS_URL), and one of the «Valid OAuth Redirect URIs»
# of Meta's app. Door 10 hands it to the Hub, which opens the window with it, and door 11 exchanges the code with this
# very value (Meta refuses another: error 100/36008). Not https outside development = WhatsApp off (whatsapp.I001).
WHATSAPP_REDIRECT_URI = config("WHATSAPP_REDIRECT_URI", default=f"{WHATSAPP_MEDIA_BASE_URL}/whatsapp/return")
