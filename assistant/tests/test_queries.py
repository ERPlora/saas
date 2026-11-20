"""The reads of the AI gateway (``assistant.queries``).

This file starts with the connection of a provider (``assistant.provider.connection``): its API, its
address and its key, read from the variable of the environment it names, for the listing of its models. The key
travels as a secret: the output's ``repr`` and dump never show it.
"""

import pytest
from live.errors import OperationError, PermissionDenied

from assistant import queries
from assistant.models import AIModel
from assistant.schemas import ProviderRef
from assistant.tests.conftest import API_KEY, grant, staff_ctx

pytestmark = pytest.mark.django_db

NEWER_KEY = "sk-test-2222222222222222222222222222newr"


def connection(user, provider):
    return queries.provider_connection(staff_ctx(user), ProviderRef(id=provider.pk))


def test_the_connection_has_the_api_the_address_and_the_key_of_the_environment(ai_admin, provider, openai_key):
    AIModel.objects.create(provider=provider, model_id="gpt-4o", display_name="gpt-4o")

    out = connection(ai_admin, provider)

    assert (out.kind, out.base_url, out.name) == ("openai", "https://api.openai.com/v1", "OpenAI")
    assert out.api_key.get_secret_value() == API_KEY
    assert out.existing == ["gpt-4o"]
    assert API_KEY not in repr(out) and API_KEY not in out.model_dump_json()


def test_a_provider_without_its_key_in_the_environment_says_so(ai_admin, provider):
    with pytest.raises(OperationError) as refused:
        connection(ai_admin, provider)

    assert (refused.value.status, refused.value.code) == (409, "assistant.no_key")


def test_reading_a_connection_needs_to_see_providers(make_user, provider):
    member = grant(make_user("member@erplora.com", is_staff=True), "view_aimodel")

    with pytest.raises(PermissionDenied):
        connection(member, provider)


# --- The route of a turn ---------------------------------------------------------------------------------

from assistant.models import AIProvider, AIRoutingPolicy  # noqa: E402
from assistant.schemas import RouteIn  # noqa: E402
from assistant.services.platform_actor import platform_context  # noqa: E402


@pytest.fixture
def routed(provider, settings):
    """OpenAI answers with GPT-5.5 and Anthropic is the fallback with Sonnet, both with their key in the environment."""
    anthropic = AIProvider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY")
    settings.OPENAI_API_KEY = API_KEY
    settings.ANTHROPIC_API_KEY = NEWER_KEY
    large = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5", price_input_per_1m="5", price_output_per_1m="30")
    sonnet = AIModel.objects.create(provider=anthropic, model_id="claude-sonnet-4-6", display_name="Sonnet")
    policy = AIRoutingPolicy.solo()
    policy.active_model, policy.fallback_model = large, sonnet
    policy.save()
    return {"openai": provider, "anthropic": anthropic, "large": large, "sonnet": sonnet}


def route(model=None):
    return queries.route_resolve(platform_context(), RouteIn(model=model))


def test_a_turn_goes_to_the_model_that_answers_then_to_its_fallback(routed):
    out = route()

    first, second = out.candidates
    assert (first.model, first.model_id, first.kind, first.base_url) == (routed["large"].pk, "gpt-5.5", "openai", "https://api.openai.com/v1")
    assert first.api_key.get_secret_value() == API_KEY
    assert (str(first.price_input_per_1m), str(first.price_output_per_1m)) == ("5.0000", "30.0000")
    assert (second.model_id, second.kind, second.api_key.get_secret_value()) == ("claude-sonnet-4-6", "anthropic", NEWER_KEY)
    assert API_KEY not in repr(out) and NEWER_KEY not in out.model_dump_json()


def test_a_model_whose_provider_cannot_be_used_is_skipped_for_the_fallback(routed):
    routed["openai"].is_enabled = False
    routed["openai"].save()

    assert [c.model_id for c in route().candidates] == ["claude-sonnet-4-6"]


def test_a_model_turned_off_is_skipped_too(routed):
    routed["large"].is_available = False
    routed["large"].save()

    assert [c.model_id for c in route().candidates] == ["claude-sonnet-4-6"]


def test_without_a_model_that_answers_no_turn_can_be_answered(db):
    with pytest.raises(OperationError) as refused:
        route()

    assert (refused.value.status, refused.value.code) == (409, "assistant.no_model")


def test_a_model_whose_provider_has_no_key_is_skipped_for_the_fallback(routed, settings):
    settings.OPENAI_API_KEY = ""

    assert [c.model_id for c in route().candidates] == ["claude-sonnet-4-6"]


def test_without_any_key_no_turn_can_be_answered(routed, settings):
    settings.OPENAI_API_KEY = ""
    settings.ANTHROPIC_API_KEY = ""

    with pytest.raises(OperationError) as refused:
        route()

    assert (refused.value.status, refused.value.code) == (409, "assistant.provider_not_configured")


def test_a_changed_key_or_choice_applies_to_the_next_turn(routed, ai_admin, settings):
    from assistant import services
    from assistant.schemas import PolicyIn

    route()
    settings.OPENAI_API_KEY = "sk-test-rotated-9999"
    assert route().candidates[0].api_key.get_secret_value() == "sk-test-rotated-9999"

    services.model_choice.policy_update(staff_ctx(ai_admin), PolicyIn(active_model=routed["sonnet"].pk))
    assert [c.model_id for c in route().candidates] == ["claude-sonnet-4-6"]


def test_a_chosen_model_is_routed_alone(routed):
    assert [c.model_id for c in route(routed["sonnet"].pk).candidates] == ["claude-sonnet-4-6"]


def test_a_chosen_model_that_cannot_answer_says_why(routed, settings):
    routed["sonnet"].is_available = False
    routed["sonnet"].save()
    with pytest.raises(OperationError) as off:
        route(routed["sonnet"].pk)
    assert (off.value.status, off.value.code) == (422, "assistant.model_unavailable")

    settings.OPENAI_API_KEY = ""
    with pytest.raises(OperationError) as keyless:
        route(routed["large"].pk)
    assert (keyless.value.status, keyless.value.code) == (409, "assistant.provider_not_configured")


def test_the_staff_route_a_model_only_with_the_policy_permission(routed, make_user, ai_admin):
    member = grant(make_user("member@erplora.com", is_staff=True), "view_airoutingpolicy")

    with pytest.raises(PermissionDenied):
        queries.route_resolve(staff_ctx(member), RouteIn(model=routed["large"].pk))
    assert queries.route_resolve(staff_ctx(ai_admin), RouteIn(model=routed["large"].pk)).candidates
