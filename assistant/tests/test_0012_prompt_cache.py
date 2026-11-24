"""``0012_prompt_cache``: a model keeps the prices of the provider's cache, and a month's row the tokens it read from
the cache and wrote to it.

Claude Haiku 5.5 at Anthropic's own address gets Anthropic's prices of its cache (USD per million tokens: a read
0.01, a write that lasts five minutes 0.125). Any other model keeps them empty, so its cache is paid as input, as
before. The rows already kept read and wrote nothing of the cache.

The tests migrate inside the test's transaction (Postgres DDL is transactional), so the rollback restores everything.
"""

from decimal import Decimal

import pytest

from assistant.tests.test_0009_keys_from_environment import migrate

pytestmark = pytest.mark.django_db

BEFORE = [("assistant", "0011_usage_per_model")]
AFTER = [("assistant", "0012_prompt_cache")]


@pytest.fixture
def before():
    return migrate(BEFORE)


def provider_of(apps, kind: str, base_url: str = ""):
    return apps.get_model("assistant", "AIProvider").objects.create(
        slug=f"{kind}-{len(base_url)}", name=kind, kind=kind, base_url=base_url, key_variable=f"{kind.upper()}_API_KEY"
    )


def model_of(apps, provider, model_id: str):
    return apps.get_model("assistant", "AIModel").objects.create(
        provider=provider, model_id=model_id, display_name=model_id, price_input_per_1m=Decimal("0.10")
    )


def prices_of(apps, model) -> tuple:
    kept = apps.get_model("assistant", "AIModel").objects.get(pk=model.pk)
    return kept.price_cache_read_per_1m, kept.price_cache_write_per_1m


def test_haiku_at_anthropic_gets_the_prices_of_its_cache(before):
    haiku = model_of(before, provider_of(before, "anthropic"), "claude-haiku-5-5")

    after = migrate(AFTER)

    assert prices_of(after, haiku) == (Decimal("0.01"), Decimal("0.125"))


def test_another_model_or_a_haiku_elsewhere_keeps_them_empty(before):
    qwen = model_of(before, provider_of(before, "openai", "https://dashscope.example.com/v1"), "qwen3.7-plus")
    proxied = model_of(before, provider_of(before, "anthropic", "https://proxy.example.com"), "claude-haiku-5-5")

    after = migrate(AFTER)

    assert prices_of(after, qwen) == (None, None)
    assert prices_of(after, proxied) == (None, None)


def test_a_row_already_kept_read_and_wrote_nothing_of_the_cache(before):
    from django.utils import timezone

    user = before.get_model("accounts", "User").objects.create(email="a@example.com")
    row = before.get_model("assistant", "AssistantUsage").objects.create(user_id=user.pk, month=timezone.now().date().replace(day=1), tokens_input=500)

    after = migrate(AFTER)

    kept = after.get_model("assistant", "AssistantUsage").objects.get(pk=row.pk)
    assert (kept.tokens_input, kept.tokens_cache_read, kept.tokens_cache_write) == (500, 0, 0)


def test_the_way_back_drops_them(before):
    model_of(before, provider_of(before, "anthropic"), "claude-haiku-5-5")
    migrate(AFTER)

    back = migrate(BEFORE)

    fields = {field.name for field in back.get_model("assistant", "AIModel")._meta.get_fields()}
    assert "price_cache_read_per_1m" not in fields
