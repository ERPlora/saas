"""``0009_keys_from_environment``: a provider's key leaves the database for the environment.

The table of the keys goes, with what it held: the key now lives in the secret of erplora.com only. Each provider names
the variable it reads, set from what it is: its API's own variable at an address of its API's own company, Alibaba's
for Alibaba Cloud Model Studio (Qwen), and none for any other address (a proxy, another compatible provider), so a key
never travels to an address it was not meant for until the staff choose. On the way back the table returns empty and
the variable goes.

The tests migrate inside the test's transaction (Postgres DDL is transactional), so the rollback restores everything.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db

BEFORE = [("assistant", "0008_retire_azure_speech")]
AFTER = [("assistant", "0009_keys_from_environment")]
QWEN_URL = "https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"


def migrate(target):
    # The rows the test wrote are checked now, as a commit would: a deploy finds them committed long before.
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


@pytest.fixture
def before():
    return migrate(BEFORE)


def provider_of(apps, slug: str, kind: str, base_url: str = ""):
    provider = apps.get_model("assistant", "AIProvider").objects.create(slug=slug, name=slug, kind=kind, base_url=base_url)
    apps.get_model("assistant", "AIProviderCredential").objects.create(
        provider=provider, label="default", api_key="not-a-real-key-wxyz", key_hint="wxyz"
    )
    return provider


def test_each_provider_reads_the_variable_of_what_it_is(before):
    provider_of(before, "openai", "openai")
    provider_of(before, "openai-eu", "openai", "https://eu.api.openai.com/v1")
    provider_of(before, "qwen", "openai", QWEN_URL)
    provider_of(before, "dashscope", "openai", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    provider_of(before, "anthropic", "anthropic")
    provider_of(before, "gemini", "gemini")
    provider_of(before, "deepseek", "deepseek")
    provider_of(before, "proxy", "openai", "https://proxy.example.com/v1")
    provider_of(before, "claude-proxy", "anthropic", "https://proxy.example.com/anthropic")

    after = migrate(AFTER)

    assert dict(after.get_model("assistant", "AIProvider").objects.values_list("slug", "key_variable")) == {
        "openai": "OPENAI_API_KEY",
        "openai-eu": "OPENAI_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "proxy": "",
        "claude-proxy": "",
    }


@pytest.mark.parametrize(
    ("kind", "base_url"),
    [
        ("openai", "https://notopenai.com/v1"),
        ("openai", "https://openai.com.example.net/v1"),
        ("openai", "https://fakealiyuncs.com/compatible-mode/v1"),
        ("anthropic", "https://myanthropic.com"),
    ],
)
def test_an_address_that_only_looks_like_a_company_s_gets_no_variable(before, kind, base_url):
    provider_of(before, "lookalike", kind, base_url)

    after = migrate(AFTER)

    assert after.get_model("assistant", "AIProvider").objects.get(slug="lookalike").key_variable == ""


def test_the_keys_of_the_database_are_gone_with_their_table(before):
    provider_of(before, "openai", "openai")

    after = migrate(AFTER)

    assert "assistant_aiprovidercredential" not in connection.introspection.table_names()
    assert after.get_model("assistant", "AIProvider").objects.count() == 1
    with pytest.raises(LookupError):
        after.get_model("assistant", "AIProviderCredential")


def test_the_way_back_returns_the_table_empty_and_takes_the_variable(before):
    provider_of(before, "qwen", "openai", QWEN_URL)
    migrate(AFTER)

    back = migrate(BEFORE)

    assert "assistant_aiprovidercredential" in connection.introspection.table_names()
    assert not back.get_model("assistant", "AIProviderCredential").objects.exists()
    fields = {field.name for field in back.get_model("assistant", "AIProvider")._meta.get_fields()}
    assert "key_variable" not in fields
    assert migrate(AFTER).get_model("assistant", "AIProvider").objects.get().key_variable == "DASHSCOPE_API_KEY"
