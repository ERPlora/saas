"""Who changed the configuration of the AI (ASSISTANT-G23, G13; saas#970 of the old product): the providers, their keys,
their models and the model that answers stay in the audit trail of erplora.com (django-auditlog, ACCOUNTS-F36), with
who did it, from where and what changed. A key is never written there, neither in clear nor encrypted: its rotation
shows as its new hint and the time it changed.

The old product kept its own ``AIConfigAuditLog`` beside the general history; here there is one trail (PLAN-SAAS
§1.1: django-auditlog, each app registering its models with ``accounts.auditlog.audit``).
"""

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog

from assistant import services
from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy
from assistant.schemas import CredentialDeleteIn, CredentialIn
from assistant.tests.conftest import API_KEY, staff_ctx

pytestmark = pytest.mark.django_db

ROTATED = "sk-test-9999999999999999999999999999rot8"


def written(entries) -> str:
    """All a log entry keeps about its object, as one string to search for a secret."""
    return " ".join(
        f"{entry.object_repr} {entry.changes} {entry.changes_text} {entry.serialized_data} {entry.additional_data}"
        for entry in entries
    )


def test_the_configuration_of_the_ai_is_audited():
    registered = set(auditlog.get_models())

    assert {AIProvider, AIProviderCredential, AIModel, AIRoutingPolicy} <= registered


def test_a_key_added_and_rotated_leaves_its_hint_and_when_never_the_key(ai_admin, provider):
    ctx = staff_ctx(ai_admin)
    added = services.credential_save(ctx, CredentialIn(provider=provider.pk, label="default", api_key=API_KEY))
    services.credential_save(ctx, CredentialIn(provider=provider.pk, id=added.id, label="default", api_key=ROTATED))

    credential = AIProviderCredential.objects.get(pk=added.id)
    entries = LogEntry.objects.get_for_object(credential).order_by("timestamp")
    create, *updates = entries
    assert create.action == LogEntry.Action.CREATE
    assert any(entry.changes_dict.get("key_hint") == ["wxyz", "rot8"] for entry in updates)
    assert any("rotated_at" in entry.changes_dict for entry in updates)
    token = AIProviderCredential.objects.filter(pk=added.id).values_list("api_key", flat=True).get()
    for secret in (API_KEY, ROTATED, token):
        assert secret not in written(entries)
    assert all("api_key" not in entry.changes_dict for entry in entries)
    assert all("api_key" not in (entry.serialized_data or {}).get("fields", {}) for entry in entries)


def test_a_key_turned_off_or_deleted_stays_in_the_trail(ai_admin, provider):
    ctx = staff_ctx(ai_admin)
    added = services.credential_save(ctx, CredentialIn(provider=provider.pk, label="default", api_key=API_KEY))
    services.credential_save(ctx, CredentialIn(provider=provider.pk, id=added.id, label="default", is_active=False))
    services.credential_delete(ctx, CredentialDeleteIn(id=added.id))

    entries = LogEntry.objects.filter(object_pk=str(added.id)).order_by("timestamp")
    assert [entry.action for entry in entries] == [LogEntry.Action.CREATE, LogEntry.Action.UPDATE, LogEntry.Action.DELETE]
    assert entries[1].changes_dict["is_active"] == ["True", "False"]
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
