"""Recording a try of a model (``assistant.model.try``, ASSISTANT-G61): who tried which model, how long the message
was and how many tools it offered, never the message (the old product's tester kept a summary of it)."""

import pytest
from auditlog.models import LogEntry
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent

from assistant import services
from assistant.models import AIModel
from assistant.schemas import ModelTryIn
from assistant.tests.conftest import grant, staff_ctx

pytestmark = pytest.mark.django_db


@pytest.fixture
def model(provider):
    return AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")


def test_a_try_is_recorded_with_who_and_how_much_was_sent(ai_admin, model):
    out = services.model_try(staff_ctx(ai_admin), ModelTryIn(model=model.pk, prompt_chars=12, tools=0))

    assert out.recorded is True
    [entry] = LogEntry.objects.filter(action=LogEntry.Action.ACCESS)
    assert (entry.object_pk, entry.actor_id, entry.additional_data) == (str(model.pk), ai_admin.pk, {"tried": True, "prompt_chars": 12, "tools": 0})
    [event] = OutboxEvent.objects.filter(name="assistant.model.tried")
    assert event.payload == {"model": str(model.pk), "prompt_chars": 12, "tools": 0}


def test_only_the_staff_who_may_change_the_model_that_answers_try_one(make_user, model):
    member = grant(make_user("member@erplora.com", is_staff=True), "view_airoutingpolicy")

    with pytest.raises(PermissionDenied):
        services.model_try(staff_ctx(member), ModelTryIn(model=model.pk, prompt_chars=12, tools=0))
    assert not LogEntry.objects.filter(action=LogEntry.Action.ACCESS).exists()


def test_an_unknown_model_cannot_be_tried(ai_admin, model):
    model_id = model.pk
    model.delete()

    with pytest.raises(NotFound) as unknown:
        services.model_try(staff_ctx(ai_admin), ModelTryIn(model=model_id, prompt_chars=12, tools=0))

    assert unknown.value.code == "assistant.model_unknown"
