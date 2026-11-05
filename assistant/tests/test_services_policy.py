"""Choosing which model answers (``assistant.policy.update`` and ``assistant.policy.show``; ASSISTANT-G27, G17, G10,
G60; old SAAS_ASSISTANT-F23).

One row for the whole platform: the model that answers and the fallback one. Only an available model of an enabled
provider can be chosen, the fallback is another model, and who changed it is kept. Only staff with the policy's
permissions see it or change it.
"""

import pytest
from live.errors import OperationError, PermissionDenied
from live.models import OutboxEvent

from assistant import queries, services
from assistant.models import AIModel, AIProvider, AIRoutingPolicy
from assistant.schemas import NoInput, PolicyIn
from assistant.tests.conftest import grant, staff_ctx

pytestmark = pytest.mark.django_db


@pytest.fixture
def models(provider):
    anthropic = AIProvider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic")
    return {
        "large": AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5"),
        "small": AIModel.objects.create(provider=provider, model_id="gpt-5.4-mini", display_name="GPT-5.4 mini"),
        "sonnet": AIModel.objects.create(provider=anthropic, model_id="claude-sonnet-4-6", display_name="Sonnet"),
        "off": AIModel.objects.create(provider=provider, model_id="gpt-off", display_name="Off", is_available=False),
    }


def update(user, **fields):
    return services.policy_update(staff_ctx(user), PolicyIn(**fields))


def test_choosing_the_model_and_its_fallback_saves_who_did_it(ai_admin, models):
    out = update(ai_admin, active_model=models["large"].pk, fallback_model=models["sonnet"].pk)

    policy = AIRoutingPolicy.solo()
    assert (policy.active_model, policy.fallback_model, policy.updated_by) == (models["large"], models["sonnet"], ai_admin)
    assert (out.active_model, out.fallback_model) == (models["large"].pk, models["sonnet"].pk)
    [event] = OutboxEvent.objects.filter(name="assistant.policy.updated")
    assert event.payload == {"active_model": str(models["large"].pk), "fallback_model": str(models["sonnet"].pk)}


def test_the_fallback_can_be_left_empty_and_changing_again_keeps_one_row(ai_admin, models):
    update(ai_admin, active_model=models["large"].pk, fallback_model=models["sonnet"].pk)
    update(ai_admin, active_model=models["small"].pk)

    policy = AIRoutingPolicy.solo()
    assert (policy.active_model, policy.fallback_model) == (models["small"], None)
    assert AIRoutingPolicy.objects.count() == 1


def test_a_model_that_is_off_cannot_answer(ai_admin, models):
    with pytest.raises(OperationError) as refused:
        update(ai_admin, active_model=models["off"].pk)

    assert (refused.value.status, refused.value.code) == (422, "assistant.model_unavailable")
    assert "active_model" in refused.value.fields
    assert AIRoutingPolicy.solo().active_model is None


def test_a_model_of_a_provider_that_is_off_cannot_answer(ai_admin, models, provider):
    provider.is_enabled = False
    provider.save()

    with pytest.raises(OperationError) as refused:
        update(ai_admin, active_model=models["sonnet"].pk, fallback_model=models["large"].pk)

    assert refused.value.code == "assistant.model_unavailable"
    assert "fallback_model" in refused.value.fields


def test_the_fallback_must_be_another_model(ai_admin, models):
    with pytest.raises(OperationError) as refused:
        update(ai_admin, active_model=models["large"].pk, fallback_model=models["large"].pk)

    assert (refused.value.status, refused.value.code) == (422, "assistant.fallback_is_active")


def test_a_fallback_without_a_model_that_answers_is_refused(ai_admin, models):
    with pytest.raises(OperationError) as refused:
        update(ai_admin, fallback_model=models["large"].pk)

    assert refused.value.code == "assistant.fallback_without_model"


def test_an_unknown_model_is_refused(ai_admin, models):
    with pytest.raises(OperationError) as refused:
        update(ai_admin, active_model="0190b3a0-0000-7000-8000-000000000000")

    assert refused.value.code == "assistant.model_unavailable"


def test_changing_needs_the_change_permission(make_user, models):
    viewer = grant(make_user("viewer@erplora.com", is_staff=True), "view_airoutingpolicy")

    with pytest.raises(PermissionDenied):
        update(viewer, active_model=models["large"].pk)

    assert AIRoutingPolicy.solo().active_model is None


def test_the_policy_shows_its_choice_and_the_models_that_can_answer(ai_admin, models, provider):
    update(ai_admin, active_model=models["large"].pk)

    out = queries.policy_show(staff_ctx(ai_admin), NoInput())

    assert out.active_model == models["large"].pk and out.fallback_model is None
    assert out.updated_by == "ai-admin@erplora.com"
    labels = [choice.label for choice in out.choices]
    assert labels == ["Anthropic · Sonnet (claude-sonnet-4-6)", "OpenAI · GPT-5.4 mini (gpt-5.4-mini)", "OpenAI · GPT-5.5 (gpt-5.5)"]


def test_seeing_the_policy_needs_its_view_permission(make_user, models):
    member = grant(make_user("member@erplora.com", is_staff=True), "view_aimodel")

    with pytest.raises(PermissionDenied):
        queries.policy_show(staff_ctx(member), NoInput())
