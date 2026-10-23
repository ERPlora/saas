"""Fixtures of the assistant tests: the key of the credentials, the staff who configure the AI and the rows the
admin leaves.

No test reaches a real provider: each client speaks to ``fake_provider`` (``assistant.tests.fake_provider``), a
local HTTP server on ``127.0.0.1`` that answers in the provider's own wire format, so our client runs its real
network code. No real key is ever written: the keys here are made up.
"""

import pytest
from django.contrib.auth.models import Permission
from live.context import OperationContext, Scope

from assistant.tests.fake_provider import FakeProvider
from hubs.tests.conftest import make_user  # noqa: F401 - shared fixture

FERNET_KEY = "mbAv33BqhZbROx9FgnZVR3XPEUopApIq3G-xQR4E58w="
OTHER_FERNET_KEY = "SWDVBWsq5tg7Eo92t5sGAbJr_rvRBe0wPKwAaX5pvI8="
#: A made-up key in the shape of OpenAI's: what a test types in the admin.
API_KEY = "sk-test-0000000000000000000000000000wxyz"


@pytest.fixture(autouse=True)
def fernet_key(settings):
    """The key of the credentials, as the environment gives it outside the tests."""
    settings.FERNET_KEY = FERNET_KEY
    settings.FERNET_KEY_PREVIOUS = ""
    return FERNET_KEY


def staff_ctx(user, language: str = "en") -> OperationContext:
    """The context the admin builds for a member of the staff (``assistant.admin.staff_context``)."""
    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=frozenset({"assistant.manage"}),
        language=language,
    )


def grant(user, *codenames: str):
    """Give ``user`` the assistant's model permissions ``codenames``."""
    user.user_permissions.add(
        *Permission.objects.filter(content_type__app_label="assistant", codename__in=codenames)
    )
    # The permission cache of the instance was filled before.
    for cache in ("_perm_cache", "_user_perm_cache"):
        user.__dict__.pop(cache, None)
    return user


#: Every permission the staff who configure the AI hold.
AI_ADMIN_PERMISSIONS = (
    "view_aiprovider",
    "add_aiprovider",
    "change_aiprovider",
    "delete_aiprovider",
    "view_aiprovidercredential",
    "add_aiprovidercredential",
    "change_aiprovidercredential",
    "delete_aiprovidercredential",
    "view_aimodel",
    "add_aimodel",
    "change_aimodel",
    "delete_aimodel",
    "view_airoutingpolicy",
    "change_airoutingpolicy",
)


@pytest.fixture
def ai_admin(make_user):
    """A member of ERPlora's staff who configures the AI: every permission of the assistant's models."""
    return grant(make_user("ai-admin@erplora.com", first_name="Iris", is_staff=True), *AI_ADMIN_PERMISSIONS)


@pytest.fixture
def plain_staff(make_user):
    """A member of the staff without any permission of the assistant."""
    return make_user("staff@erplora.com", first_name="Sam", is_staff=True)


@pytest.fixture
def fake_provider():
    """A provider's API on ``127.0.0.1``; the test scripts its answers (``FakeProvider``)."""
    server = FakeProvider()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def provider(db):
    """OpenAI, enabled, without a key."""
    from assistant.models import AIProvider

    return AIProvider.objects.create(slug="openai", name="OpenAI", kind=AIProvider.Kind.OPENAI)
