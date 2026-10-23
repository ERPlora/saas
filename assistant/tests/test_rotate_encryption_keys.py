"""Changing the key of the credentials without losing any (ASSISTANT-G03, G41; #1016 of the old product; PLAN-SAAS §7
block 11: «rotar FERNET_KEY no pierde credenciales»).

The rotation: the new key goes in ``FERNET_KEY`` and the old one in ``FERNET_KEY_PREVIOUS`` (it only reads), then
``rotate_encryption_keys`` writes every value again with the new key; after that the old key can be dropped. Every
column kept with ``FERNET_KEY`` is rotated: the providers' keys and WhatsApp's business tokens and PINs. The list
is derived from the models (the old command's hand-written list left seven columns out, #1016), and a guard fails
when an encrypted field appears that the rotation does not know. A value no key opens is never written: it is
reported and the command ends in error, so the old key is not dropped while something still needs it.
"""

from io import StringIO

import pytest
from cryptography.fernet import Fernet
from django.apps import apps
from django.core.management import CommandError, call_command
from django.db.models import TextField, Value
from django.db.models.functions import Cast
from live.errors import PermissionDenied
from live.models import OutboxEvent

from assistant import services
from assistant.models import AIProviderCredential
from assistant.schemas import EncryptionRotateIn
from assistant.services import platform_context
from assistant.tests.conftest import API_KEY, FERNET_KEY, OTHER_FERNET_KEY, staff_ctx
from hubs.tests.conftest import business, create_business, owner, plans  # noqa: F401 - shared fixtures
from whatsapp.models import PhoneNumber

pytestmark = pytest.mark.django_db

TOKEN = "EAAG-test-business-token"
PIN = "246810"
#: A key that is neither the current one nor the previous one.
THIRD_KEY = "mzb3YKpGuzVK4xfI4qZl7RvBWqvT0yQAXM2LFWJ6Gks="


@pytest.fixture
def kept(provider, business):
    """A provider's key and a WhatsApp number, written with the key the platform has today."""
    credential = AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    number = PhoneNumber.objects.create(
        hub=business,
        phone_number_id="106540352242922",
        display_phone="+34 910 00 00 00",
        waba_id="102290129340398",
        access_token=TOKEN,
        registration_pin=PIN,
    )
    return credential, number


def new_key(settings):
    """Step 1 of a rotation: the new key in ``FERNET_KEY``, the one before only to read."""
    settings.FERNET_KEY_PREVIOUS = FERNET_KEY
    settings.FERNET_KEY = OTHER_FERNET_KEY


def tokens() -> dict[str, str]:
    """The token in each encrypted column, as the database keeps it."""
    out = {}
    for model, name in ((AIProviderCredential, "api_key"), (PhoneNumber, "access_token"), (PhoneNumber, "registration_pin")):
        for pk, token in model.objects.annotate(raw=Cast(name, TextField())).values_list("pk", "raw"):
            out[f"{model._meta.label}.{name}:{pk}"] = token
    return out


def run(*args) -> str:
    out = StringIO()
    call_command("rotate_encryption_keys", *args, stdout=out)
    return out.getvalue()


def test_every_column_kept_with_the_key_of_the_credentials_is_rotated():
    assert {f"{model._meta.label}.{name}" for model, name in services.encrypted_columns()} == {
        "assistant.AIProviderCredential.api_key",
        "whatsapp.PhoneNumber.access_token",
        "whatsapp.PhoneNumber.registration_pin",
    }


def test_no_encrypted_field_of_the_project_is_left_out_of_the_rotation():
    """The guard of #1016: an encrypted field nobody added to the rotation would be lost the day the old key goes."""
    unknown = [
        f"{model._meta.label}.{field.name} ({type(field).__module__}.{type(field).__name__})"
        for model in apps.get_models()
        for field in model._meta.concrete_fields
        if "encrypt" in type(field).__name__.lower() and type(field) not in services.ROTATED_FIELD_CLASSES
    ]

    assert unknown == []


def test_after_rotating_the_old_key_can_go_and_every_credential_still_reads(settings, kept):
    new_key(settings)

    printed = run()
    settings.FERNET_KEY_PREVIOUS = ""

    assert AIProviderCredential.objects.get().api_key == API_KEY
    number = PhoneNumber.objects.get()
    assert (number.access_token, number.registration_pin) == (TOKEN, PIN)
    assert all(Fernet(OTHER_FERNET_KEY.encode()).decrypt(token.encode()) for token in tokens().values())
    assert "assistant.AIProviderCredential.api_key: 1 rotated, 0 already current, 0 unreadable" in printed
    assert printed.rstrip().endswith("rotated=3 current=0 unreadable=0")


def test_the_rotation_never_prints_a_value_nor_its_token(settings, kept):
    before = tokens()
    new_key(settings)

    printed = run() + run("--dry-run")

    for secret in (API_KEY, TOKEN, PIN, *before.values(), *tokens().values()):
        assert secret not in printed


def test_a_dry_run_counts_and_writes_nothing(settings, kept):
    before = tokens()
    new_key(settings)

    printed = run("--dry-run")

    assert tokens() == before
    assert printed.rstrip().endswith("(dry run) rotated=3 current=0 unreadable=0")
    assert not OutboxEvent.objects.filter(name="assistant.encryption.rotated").exists()


def test_values_already_written_with_the_new_key_are_left_alone(settings, kept):
    new_key(settings)
    run()
    after_first = tokens()

    printed = run()

    assert tokens() == after_first
    assert printed.rstrip().endswith("rotated=0 current=3 unreadable=0")


def test_the_rotation_changes_no_date_of_the_rows(settings, kept):
    credential, number = kept
    stamps = (AIProviderCredential.objects.get().updated_at, AIProviderCredential.objects.get().rotated_at)
    new_key(settings)

    run()

    assert (AIProviderCredential.objects.get().updated_at, AIProviderCredential.objects.get().rotated_at) == stamps


def test_a_value_no_key_opens_is_never_written_and_the_rotation_fails(settings, kept):
    _credential, number = kept
    lost = Fernet(THIRD_KEY.encode()).encrypt(b"999999").decode()
    PhoneNumber.objects.filter(pk=number.pk).update(registration_pin=Value(lost, output_field=TextField()))
    new_key(settings)
    out = StringIO()

    with pytest.raises(CommandError, match=r"1 value no key opens"):
        call_command("rotate_encryption_keys", stdout=out)

    assert tokens()[f"whatsapp.PhoneNumber.registration_pin:{number.pk}"] == lost
    settings.FERNET_KEY_PREVIOUS = ""
    assert AIProviderCredential.objects.get().api_key == API_KEY
    assert PhoneNumber.objects.get().access_token == TOKEN
    assert f"unreadable: whatsapp.PhoneNumber.registration_pin {number.pk}" in out.getvalue()
    assert lost not in out.getvalue()


def test_without_the_key_of_the_credentials_nothing_rotates(settings, kept):
    before = tokens()
    settings.FERNET_KEY = ""

    with pytest.raises(CommandError, match="The key of the credentials is not configured"):
        run()

    assert tokens() == before


def test_a_rotation_is_announced_with_its_counts(settings, kept):
    new_key(settings)

    run()

    [event] = OutboxEvent.objects.filter(name="assistant.encryption.rotated")
    assert event.payload == {"rotated": 3, "current": 0, "unreadable": 0}


def test_only_the_platform_rotates_the_key(ai_admin):
    with pytest.raises(PermissionDenied):
        services.encryption_rotate(staff_ctx(ai_admin), EncryptionRotateIn())

    assert services.encryption_rotate(platform_context(), EncryptionRotateIn(dry_run=True)).unreadable == 0
