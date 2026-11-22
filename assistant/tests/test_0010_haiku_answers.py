"""``0010_haiku_answers``: where the assistant already answers, Claude Haiku 5.5 becomes the model that answers.

It answers better, sooner and at half the cost per message than Qwen 3.7 Plus, which stays as its fallback. The
migration runs once, at the deploy: a choice made afterwards in the admin is kept. Whether each one answers is
decided on every turn by its key: without Anthropic's key the turn skips Haiku and goes to the fallback. A database
where no model answers yet (a new one, the tests') is left as it is: the staff set it up from the admin.

The tests migrate inside the test's transaction (Postgres DDL is transactional), so the rollback restores everything.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db

BEFORE = [("assistant", "0009_keys_from_environment")]
AFTER = [("assistant", "0010_haiku_answers")]
QWEN_URL = "https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"


def migrate(target):
    MigrationExecutor(connection).migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


@pytest.fixture
def before():
    return migrate(BEFORE)


def model_of(apps, provider, model_id: str, **fields):
    return apps.get_model("assistant", "AIModel").objects.create(
        provider=provider, model_id=model_id, display_name=model_id, **fields
    )


@pytest.fixture
def production(before):
    """What answers before the deploy: Qwen 3.7 Plus, with OpenAI's GPT-5.4 mini as its fallback."""
    Provider = before.get_model("assistant", "AIProvider")
    qwen = Provider.objects.create(slug="qwen", name="Qwen", kind="openai", base_url=QWEN_URL, key_variable="DASHSCOPE_API_KEY")
    openai = Provider.objects.create(slug="openai", name="OpenAI", kind="openai", key_variable="OPENAI_API_KEY")
    answering = model_of(before, qwen, "qwen3.7-plus")
    fallback = model_of(before, openai, "gpt-5.4-mini")
    before.get_model("assistant", "AIRoutingPolicy").objects.create(active_model=answering, fallback_model=fallback)
    return {"qwen": answering, "gpt": fallback}


def policy_of(apps):
    return apps.get_model("assistant", "AIRoutingPolicy").objects.select_related(
        "active_model__provider", "fallback_model"
    ).get()


def test_haiku_answers_with_qwen_as_its_fallback(production):
    after = migrate(AFTER)

    policy = policy_of(after)
    haiku = policy.active_model
    assert (haiku.model_id, haiku.display_name, haiku.context_window) == ("claude-haiku-5-5", "Claude Haiku 5.5", 1_000_000)
    assert (haiku.price_input_per_1m, haiku.price_output_per_1m) == (Decimal("0.10"), Decimal("0.50"))
    assert (haiku.is_available, haiku.supports_tools, haiku.supports_vision) == (True, True, True)
    anthropic = haiku.provider
    assert (anthropic.slug, anthropic.name, anthropic.kind, anthropic.base_url, anthropic.key_variable, anthropic.is_enabled) == (
        "anthropic",
        "Anthropic",
        "anthropic",
        "",
        "ANTHROPIC_API_KEY",
        True,
    )
    assert policy.fallback_model_id == production["qwen"].pk


def test_an_anthropic_provider_and_a_haiku_already_kept_are_used_as_they_are(production, before):
    claude = before.get_model("assistant", "AIProvider").objects.create(
        slug="claude", name="Claude", kind="anthropic", key_variable="ANTHROPIC_API_KEY"
    )
    kept = model_of(before, claude, "claude-haiku-5-5", price_input_per_1m=Decimal("0.2"), price_output_per_1m=Decimal("0.9"))

    after = migrate(AFTER)

    assert policy_of(after).active_model_id == kept.pk
    assert after.get_model("assistant", "AIProvider").objects.filter(kind="anthropic").count() == 1
    haiku = after.get_model("assistant", "AIModel").objects.get(pk=kept.pk)
    assert (haiku.price_input_per_1m, haiku.price_output_per_1m) == (Decimal("0.2"), Decimal("0.9"))


def test_a_kept_haiku_without_prices_gets_them(production, before):
    anthropic = before.get_model("assistant", "AIProvider").objects.create(
        slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY"
    )
    kept = model_of(before, anthropic, "claude-haiku-5-5")

    haiku = migrate(AFTER).get_model("assistant", "AIModel").objects.get(pk=kept.pk)

    assert (haiku.price_input_per_1m, haiku.price_output_per_1m) == (Decimal("0.10"), Decimal("0.50"))


def test_without_qwen_the_fallback_stays_as_it_was(before):
    Provider = before.get_model("assistant", "AIProvider")
    openai = Provider.objects.create(slug="openai", name="OpenAI", kind="openai", key_variable="OPENAI_API_KEY")
    answering = model_of(before, openai, "gpt-5.5")
    fallback = model_of(before, openai, "gpt-5.4-mini")
    before.get_model("assistant", "AIRoutingPolicy").objects.create(active_model=answering, fallback_model=fallback)

    policy = policy_of(migrate(AFTER))

    assert (policy.active_model.model_id, policy.fallback_model_id) == ("claude-haiku-5-5", fallback.pk)


def test_a_haiku_that_was_the_fallback_answers_and_leaves_the_fallback_empty_without_qwen(before):
    """Haiku cannot be its own fallback: without Qwen, the slot it leaves stays empty."""
    Provider = before.get_model("assistant", "AIProvider")
    openai = Provider.objects.create(slug="openai", name="OpenAI", kind="openai", key_variable="OPENAI_API_KEY")
    anthropic = Provider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY")
    answering = model_of(before, openai, "gpt-5.5")
    haiku = model_of(before, anthropic, "claude-haiku-5-5", price_input_per_1m=Decimal("0.1"), price_output_per_1m=Decimal("0.5"))
    before.get_model("assistant", "AIRoutingPolicy").objects.create(active_model=answering, fallback_model=haiku)

    policy = policy_of(migrate(AFTER))

    assert (policy.active_model_id, policy.fallback_model_id) == (haiku.pk, None)


def test_where_no_model_answers_yet_nothing_is_added(before):
    before.get_model("assistant", "AIRoutingPolicy").objects.create()

    after = migrate(AFTER)

    assert not after.get_model("assistant", "AIProvider").objects.exists()
    assert not after.get_model("assistant", "AIModel").objects.exists()
    assert policy_of(after).active_model_id is None


def test_a_new_database_stays_empty(before):
    after = migrate(AFTER)

    assert not after.get_model("assistant", "AIRoutingPolicy").objects.exists()
    assert not after.get_model("assistant", "AIProvider").objects.exists()


def test_the_way_back_leaves_the_choice_as_it_is(production):
    migrate(AFTER)

    back = migrate(BEFORE)

    assert policy_of(back).active_model.model_id == "claude-haiku-5-5"
