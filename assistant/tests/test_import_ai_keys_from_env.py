"""Loading the providers' keys from the environment (ASSISTANT-G02, G21; the old ``import_ai_keys_from_env``): the
command reads ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY`` and ``DEEPSEEK_API_KEY`` and keeps each
one encrypted in its provider, which it adds if missing, through ``assistant.credential.import`` as the platform.

A key already kept stays as it is unless ``--force``; ``--dry-run`` writes nothing. Nothing it prints holds a key:
only its last four characters (the old command printed the same).
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from live.errors import PermissionDenied
from live.models import OutboxEvent

from assistant import services
from assistant.models import AIProvider, AIProviderCredential
from assistant.schemas import CredentialImportIn
from assistant.services import platform_context
from assistant.tests.conftest import staff_ctx

pytestmark = pytest.mark.django_db

OPENAI = "sk-test-openai-000000000000000000000000ab12"
ANTHROPIC = "sk-ant-test-0000000000000000000000000cd34"
GEMINI = "AIza-test-000000000000000000000000000ef56"
DEEPSEEK = "sk-test-deepseek-0000000000000000000gh78"
NEWER = "sk-test-openai-999999999999999999999999zz99"


@pytest.fixture
def env(settings):
    """The four keys in the environment, as ``config/settings.py`` reads them."""
    settings.OPENAI_API_KEY = OPENAI
    settings.ANTHROPIC_API_KEY = ANTHROPIC
    settings.GEMINI_API_KEY = GEMINI
    settings.DEEPSEEK_API_KEY = DEEPSEEK
    return settings


def run(*args) -> str:
    out = StringIO()
    call_command("import_ai_keys_from_env", *args, stdout=out)
    return out.getvalue()


def key_of(slug: str, label: str = "default") -> AIProviderCredential:
    return AIProviderCredential.objects.get(provider__slug=slug, label=label)


def test_each_key_of_the_environment_is_kept_in_its_provider_which_is_added_if_missing(env):
    printed = run()

    assert {(p.slug, p.name, p.kind) for p in AIProvider.objects.all()} == {
        ("openai", "OpenAI", "openai"),
        ("anthropic", "Anthropic", "anthropic"),
        ("gemini", "Google Gemini", "gemini"),
        ("deepseek", "DeepSeek", "deepseek"),
    }
    assert key_of("openai").api_key == OPENAI and key_of("openai").key_hint == "ab12"
    assert key_of("gemini").api_key == GEMINI and key_of("gemini").is_active
    assert "openai: created key 'default' (…ab12)" in printed
    assert printed.rstrip().endswith("created=4 rotated=0 kept=0 skipped=0")


def test_the_keys_are_never_printed(env):
    printed = run() + run("--force") + run("--dry-run", "--force")

    for key in (OPENAI, ANTHROPIC, GEMINI, DEEPSEEK):
        assert key not in printed
        assert key[:-4] not in printed


def test_an_existing_provider_keeps_its_name_and_address(env):
    AIProvider.objects.create(slug="openai", name="OpenAI (EU)", kind="openai", base_url="https://eu.api.openai.com/v1")

    run("--providers", "openai")

    provider = AIProvider.objects.get(slug="openai")
    assert (provider.name, provider.base_url) == ("OpenAI (EU)", "https://eu.api.openai.com/v1")
    assert key_of("openai").api_key == OPENAI


def test_a_key_already_kept_stays_unless_forced(env):
    run("--providers", "openai")
    env.OPENAI_API_KEY = NEWER

    kept = run("--providers", "openai")
    assert key_of("openai").api_key == OPENAI and key_of("openai").rotated_at is None
    assert "openai: kept key 'default' (…ab12); --force replaces it" in kept

    forced = run("--providers", "openai", "--force")
    credential = key_of("openai")
    assert (credential.api_key, credential.key_hint) == (NEWER, "zz99")
    assert credential.rotated_at is not None
    assert "openai: rotated key 'default' (…zz99)" in forced
    assert forced.rstrip().endswith("created=0 rotated=1 kept=0 skipped=0")


def test_a_forced_key_turns_an_inactive_one_back_on(env):
    run("--providers", "openai")
    AIProviderCredential.objects.update(is_active=False)

    run("--providers", "openai", "--force")

    assert key_of("openai").is_active


def test_an_empty_variable_is_skipped(env):
    env.ANTHROPIC_API_KEY = "  "
    env.GEMINI_API_KEY = ""

    printed = run()

    assert "anthropic: skipped, ANTHROPIC_API_KEY is empty" in printed
    assert not AIProvider.objects.filter(slug__in=["anthropic", "gemini"]).exists()
    assert printed.rstrip().endswith("created=2 rotated=0 kept=0 skipped=2")


def test_only_the_providers_asked_for_are_loaded_with_their_label(env):
    printed = run("--providers", "openai, deepseek", "--label", "backup")

    assert sorted(AIProviderCredential.objects.values_list("provider__slug", "label")) == [("deepseek", "backup"), ("openai", "backup")]
    assert "deepseek: created key 'backup' (…gh78)" in printed


def test_an_unknown_provider_is_refused_before_writing(env):
    with pytest.raises(CommandError, match=r"Unknown provider\(s\): mistral\. Known: openai, anthropic, gemini, deepseek\."):
        run("--providers", "openai,mistral")

    assert not AIProvider.objects.exists()


def test_a_dry_run_says_what_would_happen_and_writes_nothing(env):
    run("--providers", "openai")
    env.OPENAI_API_KEY = NEWER

    printed = run("--dry-run", "--force")

    assert "openai: would rotate key 'default' (…zz99)" in printed
    assert "anthropic: would create key 'default' (…cd34)" in printed
    assert key_of("openai").api_key == OPENAI
    assert list(AIProvider.objects.values_list("slug", flat=True)) == ["openai"]
    assert printed.rstrip().endswith("(dry run) created=3 rotated=1 kept=0 skipped=0")


def test_without_the_key_of_the_credentials_nothing_is_kept(env):
    env.FERNET_KEY = ""

    with pytest.raises(CommandError, match="The key of the credentials is not configured"):
        run("--providers", "openai")

    assert not AIProviderCredential.objects.exists()


def test_an_imported_key_announces_its_save(env):
    run("--providers", "openai")

    [event] = OutboxEvent.objects.filter(name="assistant.credential.saved")
    assert event.payload == {"provider": str(key_of("openai").provider_id), "credential": str(key_of("openai").pk), "rotated": False}


def test_only_the_platform_imports_keys(ai_admin):
    with pytest.raises(PermissionDenied):
        services.credential_import(staff_ctx(ai_admin), CredentialImportIn(kind="openai", api_key=OPENAI))

    assert services.credential_import(platform_context(), CredentialImportIn(kind="openai", api_key=OPENAI)).action == "created"
