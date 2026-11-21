"""Who changed the configuration of the AI: the providers (with the variable of the environment each reads its key
from), their models and the model that answers stay in the audit trail of erplora.com (django-auditlog), with who did
it, from where and what changed. A key is never written there: it lives in the environment, not in a row.

There is one trail: each app registers its models with ``accounts.auditlog.audit``.
"""

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog

from assistant.models import AIModel, AIProvider, AIRoutingPolicy
from assistant.tests.conftest import API_KEY

pytestmark = pytest.mark.django_db

def written(entries) -> str:
    """All a log entry keeps about its object, as one string to search for a secret."""
    return " ".join(
        f"{entry.object_repr} {entry.changes} {entry.changes_text} {entry.serialized_data} {entry.additional_data}"
        for entry in entries
    )


def test_the_configuration_of_the_ai_is_audited():
    registered = set(auditlog.get_models())

    assert {AIProvider, AIModel, AIRoutingPolicy} <= registered


def test_the_variable_a_provider_reads_stays_in_the_trail_never_its_key(provider, settings):
    settings.OPENAI_API_KEY = API_KEY
    provider.key_variable = "DASHSCOPE_API_KEY"
    provider.save()

    entries = LogEntry.objects.get_for_object(provider).order_by("timestamp")
    assert entries.last().changes_dict["key_variable"] == ["OPENAI_API_KEY", "DASHSCOPE_API_KEY"]
    assert API_KEY not in written(entries)


def test_a_change_of_a_provider_or_a_model_says_what_changed(provider):
    created = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")
    # As the admin does: the row read back (an instance just created keeps its defaults unrounded).
    model = AIModel.objects.get(pk=created.pk)
    provider.is_enabled = False
    provider.save()
    model.price_input_per_1m = "5"
    model.save()

    [provider_change] = LogEntry.objects.get_for_object(provider).filter(action=LogEntry.Action.UPDATE)
    [model_change] = LogEntry.objects.get_for_object(model).filter(action=LogEntry.Action.UPDATE)
    assert provider_change.changes_dict == {"is_enabled": ["True", "False"]}
    assert set(model_change.changes_dict) == {"price_input_per_1m"}


def test_the_model_that_answers_changed_in_the_admin_names_who_and_from_where(client, ai_admin, provider):
    model = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")
    client.force_login(ai_admin)

    client.post("/admin/assistant/airoutingpolicy/policy/", {"active_model": str(model.pk)}, REMOTE_ADDR="203.0.113.7")

    [change] = LogEntry.objects.get_for_object(AIRoutingPolicy.solo()).filter(action=LogEntry.Action.UPDATE)
    assert (change.actor_id, change.remote_addr) == (ai_admin.pk, "203.0.113.7")
    assert change.changes_dict["active_model"][1] == str(model.pk)
    assert "updated_at" not in change.changes_dict
