"""``0008_retire_azure_speech``: the kind of Azure AI Speech leaves, and a provider of it leaves with it (saas#242).

A row of that kind would be a choice no form accepts and an API no client speaks: it goes with its keys and its models,
and the policy lets go of a model of it. Nothing else moves, whatever its identifier. On the way back the kind returns
and the rows do not: a key is not kept around to restore it.

The tests migrate inside the test's transaction (Postgres DDL is transactional), so the rollback restores everything.
"""

import logging

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db

BEFORE = [("assistant", "0007_aiprovider_azure_speech")]
AFTER = [("assistant", "0008_retire_azure_speech")]
KEY = "not-a-real-key-wxyz"


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


@pytest.fixture
def before():
    return migrate(BEFORE)


def provider_of(apps, slug: str, kind: str):
    provider = apps.get_model("assistant", "AIProvider").objects.create(slug=slug, name=slug, kind=kind)
    apps.get_model("assistant", "AIProviderCredential").objects.create(
        provider=provider, label="default", api_key=KEY, key_hint="wxyz"
    )
    model = apps.get_model("assistant", "AIModel").objects.create(provider=provider, model_id=f"{slug}-1", display_name=slug)
    return provider, model


def test_a_provider_of_that_kind_leaves_with_its_keys_and_its_models(before):
    provider_of(before, "azure-speech", "azure_speech")
    provider_of(before, "azure-eu", "azure_speech")

    after = migrate(AFTER)

    assert not after.get_model("assistant", "AIProvider").objects.exists()
    assert not after.get_model("assistant", "AIProviderCredential").objects.exists()
    assert not after.get_model("assistant", "AIModel").objects.exists()


def test_it_leaves_even_with_a_key_that_can_no_longer_be_read(before, settings):
    from assistant.tests.conftest import FERNET_KEY, OTHER_FERNET_KEY

    settings.FERNET_KEY = OTHER_FERNET_KEY
    provider_of(before, "azure-speech", "azure_speech")
    settings.FERNET_KEY = FERNET_KEY

    after = migrate(AFTER)

    assert not after.get_model("assistant", "AIProvider").objects.exists()


def test_every_other_provider_stays_with_its_keys_and_its_models_whatever_its_identifier(before):
    provider_of(before, "azure-speech", "openai")
    provider_of(before, "anthropic", "anthropic")
    provider_of(before, "voice", "azure_speech")

    after = migrate(AFTER)

    stays = {"azure-speech": "openai", "anthropic": "anthropic"}
    assert dict(after.get_model("assistant", "AIProvider").objects.values_list("slug", "kind")) == stays
    assert set(after.get_model("assistant", "AIProviderCredential").objects.values_list("provider__slug", flat=True)) == set(stays)
    assert set(after.get_model("assistant", "AIModel").objects.values_list("provider__slug", flat=True)) == set(stays)


@pytest.mark.parametrize("slot", ["active_model", "fallback_model"])
def test_the_policy_lets_go_of_a_model_of_it_and_keeps_the_other(before, slot):
    """Its foreign keys protect the model: a policy set by hand must not stop the deploy."""
    _, voice = provider_of(before, "azure-speech", "azure_speech")
    _, chat = provider_of(before, "openai", "openai")
    other = "fallback_model" if slot == "active_model" else "active_model"
    policy = before.get_model("assistant", "AIRoutingPolicy").objects.create(**{slot: voice, other: chat})

    after = migrate(AFTER)

    kept = after.get_model("assistant", "AIRoutingPolicy").objects.get(pk=policy.pk)
    assert getattr(kept, f"{slot}_id") is None
    assert getattr(kept, f"{other}_id") == chat.pk


def test_it_says_which_it_removed_and_never_a_key(before, caplog):
    provider_of(before, "azure-speech", "azure_speech")

    with caplog.at_level(logging.WARNING, logger="assistant.migrations"):
        migrate(AFTER)

    assert "assistant.migration.azure_speech_removed providers=['azure-speech']" in caplog.text
    assert KEY not in caplog.text


def test_with_no_provider_of_that_kind_it_says_nothing_and_changes_nothing(before, caplog):
    provider_of(before, "openai", "openai")

    with caplog.at_level(logging.WARNING, logger="assistant.migrations"):
        after = migrate(AFTER)

    assert "azure_speech_removed" not in caplog.text
    assert after.get_model("assistant", "AIProvider").objects.count() == 1


def test_the_kind_is_gone_from_the_choices_and_the_way_back_returns_it_without_the_rows(before):
    provider_of(before, "azure-speech", "azure_speech")

    after = migrate(AFTER)
    assert "azure_speech" not in dict(after.get_model("assistant", "AIProvider")._meta.get_field("kind").choices)

    back = migrate(BEFORE)
    AIProvider = back.get_model("assistant", "AIProvider")
    assert "azure_speech" in dict(AIProvider._meta.get_field("kind").choices)
    assert not AIProvider.objects.exists()

    provider_of(back, "azure-speech", "azure_speech")
    assert not migrate(AFTER).get_model("assistant", "AIProvider").objects.exists()
