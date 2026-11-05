"""Choosing a provider's models (``assistant.model.select``, ASSISTANT-G24, G14; old SAAS_ASSISTANT-F22 step 3).

The staff tick, among the chat models the provider's API listed, the ones the provider keeps: the ticked are created
(or made available again), the rest of the provider's models are deleted, except the ones the policy uses, which
stay. Only staff who may add and delete models choose.
"""

import pytest
from live.errors import OperationError, PermissionDenied
from live.models import OutboxEvent

from assistant import services
from assistant.models import AIModel, AIRoutingPolicy
from assistant.schemas import ListedModel, ModelSelectIn
from assistant.tests.conftest import grant, staff_ctx

pytestmark = pytest.mark.django_db

LISTED = [
    ListedModel(model_id="gpt-4o", display_name="gpt-4o", context_window=128000),
    ListedModel(model_id="gpt-5.5", display_name="GPT-5.5", context_window=0),
]


def select(user, provider, selected, listed=LISTED):
    return services.model_select(staff_ctx(user), ModelSelectIn(provider=provider.pk, listed=listed, selected=selected))


def test_the_ticked_models_are_created_available(ai_admin, provider):
    out = select(ai_admin, provider, ["gpt-4o", "gpt-5.5"])

    assert (out.created, out.kept, out.deleted, out.protected) == (2, 0, 0, 0)
    created = {m.model_id: m for m in AIModel.objects.filter(provider=provider)}
    assert created["gpt-4o"].display_name == "gpt-4o" and created["gpt-4o"].context_window == 128000
    assert created["gpt-5.5"].display_name == "GPT-5.5" and created["gpt-5.5"].is_available
    [event] = OutboxEvent.objects.filter(name="assistant.model.selected")
    assert event.payload == {"provider": str(provider.pk), "created": 2, "kept": 0, "deleted": 0, "protected": 0}


def test_a_ticked_model_that_was_there_is_kept_and_made_available(ai_admin, provider):
    model = AIModel.objects.create(provider=provider, model_id="gpt-4o", display_name="My GPT-4o", is_available=False, context_window=0)

    out = select(ai_admin, provider, ["gpt-4o"])

    model.refresh_from_db()
    assert (out.created, out.kept) == (0, 1)
    assert model.is_available is True
    assert model.display_name == "My GPT-4o"
    assert model.context_window == 128000


def test_the_models_not_ticked_are_deleted_but_the_ones_the_policy_uses_stay(ai_admin, provider):
    used = AIModel.objects.create(provider=provider, model_id="gpt-4o", display_name="gpt-4o")
    reserve = AIModel.objects.create(provider=provider, model_id="old-reserve", display_name="Reserve")
    AIModel.objects.create(provider=provider, model_id="gpt-old", display_name="old")
    policy = AIRoutingPolicy.solo()
    policy.active_model, policy.fallback_model = used, reserve
    policy.save()

    out = select(ai_admin, provider, ["gpt-5.5"])

    assert (out.created, out.kept, out.deleted, out.protected) == (1, 0, 1, 2)
    assert set(AIModel.objects.filter(provider=provider).values_list("model_id", flat=True)) == {"gpt-4o", "old-reserve", "gpt-5.5"}


def test_a_ticked_model_the_api_did_not_list_is_ignored(ai_admin, provider):
    out = select(ai_admin, provider, ["not-listed"])

    assert out.created == 0
    assert not AIModel.objects.filter(model_id="not-listed").exists()


def test_the_models_of_another_provider_are_never_touched(ai_admin, provider):
    from assistant.models import AIProvider

    other = AIProvider.objects.create(slug="deepseek", name="DeepSeek", kind="deepseek")
    theirs = AIModel.objects.create(provider=other, model_id="deepseek-chat", display_name="DeepSeek")

    select(ai_admin, provider, [])

    assert AIModel.objects.filter(pk=theirs.pk).exists()


def test_an_unknown_provider_is_refused(ai_admin, provider):
    with pytest.raises(OperationError) as refused:
        services.model_select(staff_ctx(ai_admin), ModelSelectIn(provider="0190b3a0-0000-7000-8000-000000000000", listed=[], selected=[]))

    assert (refused.value.status, refused.value.code) == (404, "assistant.provider_unknown")


@pytest.mark.parametrize("held", [("add_aimodel",), ("delete_aimodel",), ()])
def test_choosing_needs_to_add_and_to_delete_models(make_user, provider, held):
    member = grant(make_user("member@erplora.com", is_staff=True), *held)

    with pytest.raises(PermissionDenied):
        select(member, provider, ["gpt-4o"])

    assert not AIModel.objects.exists()
