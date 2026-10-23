"""The writes of the AI gateway (``assistant.services``), each an operation the admin and the commands call.

This file: a provider's key (ASSISTANT-G26, G16; old SAAS_ASSISTANT-F22 step 2 and 4). The key is kept encrypted
with its last four characters as hint; typing another one is a rotation (when, by whom); the outbox, the input's
``repr`` and the errors never carry it. Only an active member of the staff with the credential's model permission
saves or deletes one.
"""

import pytest
from live.errors import OperationError, PermissionDenied
from live.models import OutboxEvent

from assistant import services
from assistant.models import AIProviderCredential
from assistant.schemas import CredentialDeleteIn, CredentialIn
from assistant.tests.conftest import API_KEY, grant, staff_ctx

pytestmark = pytest.mark.django_db

NEW_KEY = "sk-test-1111111111111111111111111111abcd"


def save(user, **fields):
    return services.credential_save(staff_ctx(user), CredentialIn(**fields))


def events(name: str) -> list[OutboxEvent]:
    return list(OutboxEvent.objects.filter(name=name).order_by("created_at"))


def test_the_input_never_shows_the_key():
    data = CredentialIn(provider="0190b3a0-0000-7000-8000-000000000000", label="default", api_key=API_KEY)

    assert API_KEY not in repr(data)
    assert API_KEY not in str(data.model_dump())


def test_a_new_key_is_kept_encrypted_with_its_hint_and_its_author(ai_admin, provider):
    out = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)

    credential = AIProviderCredential.objects.get(pk=out.id)
    assert credential.api_key == API_KEY
    assert (credential.key_hint, credential.is_active) == ("wxyz", True)
    assert credential.created_by == ai_admin and credential.updated_by == ai_admin
    assert credential.rotated_at is None
    assert out.masked_key == "…wxyz"
    [event] = events("assistant.credential.saved")
    assert event.payload == {"provider": str(provider.pk), "credential": str(credential.pk), "rotated": False}


def test_a_new_credential_needs_its_key(ai_admin, provider):
    with pytest.raises(OperationError) as refused:
        save(ai_admin, provider=provider.pk, label="default")

    assert (refused.value.status, refused.value.code) == (422, "assistant.key_required")
    assert not AIProviderCredential.objects.exists()


def test_saving_without_a_key_keeps_the_one_there_was(ai_admin, provider):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)

    save(ai_admin, provider=provider.pk, id=first.id, label="main", is_active=False)

    credential = AIProviderCredential.objects.get(pk=first.id)
    assert (credential.api_key, credential.label, credential.is_active) == (API_KEY, "main", False)
    assert credential.rotated_at is None


def test_typing_another_key_rotates_it(ai_admin, provider, make_user):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)
    other = grant(make_user("other-admin@erplora.com", is_staff=True), "change_aiprovidercredential")

    out = save(other, provider=provider.pk, id=first.id, label="default", api_key=NEW_KEY)

    credential = AIProviderCredential.objects.get(pk=first.id)
    assert credential.api_key == NEW_KEY
    assert credential.key_hint == "abcd" and out.masked_key == "…abcd"
    assert credential.rotated_at is not None
    assert credential.created_by == ai_admin and credential.updated_by == other
    assert events("assistant.credential.saved")[-1].payload["rotated"] is True


def test_the_outbox_never_carries_the_key(ai_admin, provider):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)
    save(ai_admin, provider=provider.pk, id=first.id, label="default", api_key=NEW_KEY)

    for event in OutboxEvent.objects.filter(name__startswith="assistant."):
        assert API_KEY not in str(event.payload) and NEW_KEY not in str(event.payload)


def test_a_label_already_used_by_the_provider_is_refused(ai_admin, provider):
    save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)

    with pytest.raises(OperationError) as refused:
        save(ai_admin, provider=provider.pk, label="default", api_key=NEW_KEY)

    assert (refused.value.status, refused.value.code) == (409, "assistant.label_taken")


def test_without_the_key_of_the_credentials_nothing_is_saved(ai_admin, provider, settings):
    settings.FERNET_KEY = ""

    with pytest.raises(OperationError) as refused:
        save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)

    assert (refused.value.status, refused.value.code) == (503, "assistant.encryption_not_configured")
    assert not AIProviderCredential.objects.exists()


def test_a_member_of_the_staff_without_the_permission_cannot_save_a_key(plain_staff, provider):
    with pytest.raises(PermissionDenied) as refused:
        save(plain_staff, provider=provider.pk, label="default", api_key=API_KEY)

    assert refused.value.code == "assistant.staff_only"
    assert not AIProviderCredential.objects.exists()


def test_an_account_that_is_not_staff_cannot_save_a_key(make_user, provider):
    customer = grant(make_user("customer@example.com"), "add_aiprovidercredential")

    with pytest.raises(PermissionDenied):
        save(customer, provider=provider.pk, label="default", api_key=API_KEY)


def test_rotating_needs_the_change_permission(make_user, provider, ai_admin):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)
    adder = grant(make_user("adder@erplora.com", is_staff=True), "add_aiprovidercredential")

    with pytest.raises(PermissionDenied):
        save(adder, provider=provider.pk, id=first.id, label="default", api_key=NEW_KEY)

    assert AIProviderCredential.objects.get(pk=first.id).api_key == API_KEY


def test_deleting_a_key_forgets_it(ai_admin, provider):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)

    services.credential_delete(staff_ctx(ai_admin), CredentialDeleteIn(id=first.id))

    assert not AIProviderCredential.objects.exists()
    [event] = events("assistant.credential.deleted")
    assert event.payload == {"provider": str(provider.pk), "credential": str(first.id)}


def test_deleting_needs_the_delete_permission(make_user, provider, ai_admin):
    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)
    viewer = grant(make_user("viewer@erplora.com", is_staff=True), "view_aiprovidercredential")

    with pytest.raises(PermissionDenied):
        services.credential_delete(staff_ctx(viewer), CredentialDeleteIn(id=first.id))

    assert AIProviderCredential.objects.filter(pk=first.id).exists()


def test_a_change_that_types_no_key_leaves_an_unreadable_token_as_it_was(ai_admin, provider, settings):
    """The WORKBOOK's promise (F02): a key no live key opens reads as «Unreadable», and saving the row without typing
    another one never writes the stored token again (it waits for its key to come back or to be typed again)."""
    from django.db import connection

    from assistant.tests.conftest import OTHER_FERNET_KEY

    first = save(ai_admin, provider=provider.pk, label="default", api_key=API_KEY)
    with connection.cursor() as cursor:
        cursor.execute("SELECT api_key FROM assistant_aiprovidercredential WHERE id = %s", [first.id])
        [(token,)] = cursor.fetchall()
    settings.FERNET_KEY = OTHER_FERNET_KEY  # the key that wrote the token is gone: it reads as empty

    save(ai_admin, provider=provider.pk, id=first.id, label="main", is_active=False)

    with connection.cursor() as cursor:
        cursor.execute("SELECT api_key, label, is_active FROM assistant_aiprovidercredential WHERE id = %s", [first.id])
        [(kept, label, is_active)] = cursor.fetchall()
    assert (kept, label, is_active) == (token, "main", False)
    settings.FERNET_KEY = "mbAv33BqhZbROx9FgnZVR3XPEUopApIq3G-xQR4E58w="  # its key comes back: the key still reads
    assert AIProviderCredential.objects.get(pk=first.id).api_key == API_KEY
