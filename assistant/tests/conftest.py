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
from base.tests.conftest import ca_gone_after_one_read, unreadable_ca  # noqa: F401 - the server's trusted certificates
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

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


# --- The Hub's turn (part 2): the doors, a business and a model that answers ------------------------------------


@pytest.fixture
def internal(settings):
    """The secret the Hub signs its calls with (``accounts.signing``), as the environment gives it."""
    from assistant.tests.doors import SECRET

    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    return SECRET


@pytest.fixture
def business(owner, plans):
    """A working business (active) on the Free plan of the catalogue: 30 assistant messages a month."""
    from hubs.models import Hub
    from hubs.tests.conftest import create_business

    hub = create_business(owner)
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ACTIVE)
    hub.refresh_from_db()
    return hub


@pytest.fixture
def owner(make_user):
    return make_user("owner@example.com", first_name="Olga", language="es")


def on_plan(hub, slug: str, **changes):
    """``hub`` on the catalogue's plan ``slug`` (with ``changes`` to the plan, e.g. its monthly messages)."""
    from hubs.models import Plan, Subscription

    plan = Plan.objects.get(slug=slug)
    if changes:
        Plan.objects.filter(pk=plan.pk).update(**changes)
    Subscription.objects.filter(hub=hub).update(plan=plan, trial_plan=None, trial_end=None)
    return plan


@pytest.fixture
def answering(fake_provider, provider):
    """OpenAI on the fake provider with a key and one model that answers (``gpt-test``, 2 $ in / 8 $ out per 1M)."""
    from decimal import Decimal

    from assistant.models import AIModel, AIProviderCredential, AIRoutingPolicy

    provider.base_url = f"{fake_provider.url}/v1"
    provider.save(update_fields=["base_url"])
    credential = AIProviderCredential(provider=provider, label="default")
    credential.api_key = API_KEY
    credential.key_hint = API_KEY[-4:]
    credential.save()
    model = AIModel.objects.create(
        provider=provider,
        model_id="gpt-test",
        display_name="GPT Test",
        price_input_per_1m=Decimal("2"),
        price_output_per_1m=Decimal("8"),
        supports_vision=True,
    )
    policy = AIRoutingPolicy.solo()
    policy.active_model = model
    policy.save()
    return model


def openai_answer(*pieces: str, tokens=(100, 20), finish: str = "stop") -> list:
    """The SSE of an OpenAI answer in ``pieces`` with its usage, for ``fake_provider.reply(..., sse=…)``."""
    from assistant.tests.fake_provider import openai_chunk

    chunks = [openai_chunk(piece) for piece in pieces[:-1]]
    chunks.append(openai_chunk(pieces[-1] if pieces else "", finish=finish))
    chunks.append(openai_chunk(usage={"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}))
    return [*chunks, "[DONE]"]


def openai_tool_call(name: str, arguments: str, *, call_id: str = "call_1", tokens=(100, 10)) -> list:
    """The SSE of an OpenAI answer that asks for the tool ``name``."""
    from assistant.tests.fake_provider import openai_chunk

    call = [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}]
    return [
        openai_chunk(tool_calls=call),
        openai_chunk(finish="tool_calls"),
        openai_chunk(usage={"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}),
        "[DONE]",
    ]
