"""Fixtures of the whatsapp tests: a business with its owner, Meta's settings and the Hub double.

Meta is a third party with no test environment here: its Graph API is replaced at the HTTP border only
(``respx``), with bodies from Meta's documentation and the old product's tests. The Hub is ours: its
``/internal`` is the real-HTTP double of hubs (``hubs.tests.hub_double``), which verifies the signature.
"""

import pytest

from hubs.tests.conftest import (  # noqa: F401 - fixtures shared with hubs
    add_member,
    business,
    create_business,
    hub_double,
    make_user,
    offline_hub,
    owner,
    plans,
    team,
)

APP_ID = "1234567890"
APP_SECRET = "test-meta-app-secret"
VERIFY_TOKEN = "test-verify-token"
CONFIG_ID = "987654321"
FERNET_KEY = "mbAv33BqhZbROx9FgnZVR3XPEUopApIq3G-xQR4E58w="
OTHER_FERNET_KEY = "SWDVBWsq5tg7Eo92t5sGAbJr_rvRBe0wPKwAaX5pvI8="
GRAPH = "https://graph.facebook.com/v25.0"
#: erplora.com's page Meta's window brings its code back to (door 10 gives it; door 11 exchanges the code with it).
REDIRECT_URI = "https://erplora.com/whatsapp/return"


@pytest.fixture
def whatsapp_on(settings):
    """WhatsApp configured as outside the tests: Meta's app, its webhook secret and the key of the tokens."""
    settings.WHATSAPP_APP_ID = APP_ID
    settings.WHATSAPP_APP_SECRET = APP_SECRET
    settings.WHATSAPP_VERIFY_TOKEN = VERIFY_TOKEN
    settings.WHATSAPP_CONFIG_ID = CONFIG_ID
    settings.WHATSAPP_GRAPH_VERSION = "v25.0"
    settings.WHATSAPP_REDIRECT_URI = REDIRECT_URI
    settings.FERNET_KEY = FERNET_KEY
    settings.FERNET_KEY_PREVIOUS = ""
    return settings


@pytest.fixture
def other_business(make_user, plans):
    """A second business, of another account (an account owns one free business)."""
    return create_business(make_user("pepe@example.com", language="es"), name="Bar Pepe")
