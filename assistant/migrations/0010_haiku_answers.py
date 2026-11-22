"""Where the assistant already answers, Claude Haiku 5.5 becomes the model that answers, with Qwen 3.7 Plus as its
fallback.

It runs once, at the deploy, so a choice made afterwards in the admin is kept. Whether each one answers is decided on
every turn by its key in the environment: without Anthropic's key the turn goes to the fallback. A database where no
model answers yet is left as it is: the staff set it up from the admin. An Anthropic provider at its own address and a
Haiku already kept are used as they are; a Haiku without prices gets Anthropic's (USD per million tokens).
"""

from decimal import Decimal

from django.db import migrations

HAIKU = "claude-haiku-5-5"
QWEN = "qwen3.7-plus"
PRICE_IN, PRICE_OUT = Decimal("0.10"), Decimal("0.50")


def anthropic_provider(providers):
    found = providers.filter(kind="anthropic", base_url="").order_by("created_at").first()
    if found is not None:
        return found
    return providers.create(slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY")


def haiku_of(models, provider):
    haiku = models.filter(provider=provider, model_id=HAIKU).first()
    if haiku is None:
        return models.create(
            provider=provider,
            model_id=HAIKU,
            display_name="Claude Haiku 5.5",
            context_window=1_000_000,
            price_input_per_1m=PRICE_IN,
            price_output_per_1m=PRICE_OUT,
            supports_tools=True,
            supports_vision=True,
        )
    if not haiku.price_input_per_1m and not haiku.price_output_per_1m:
        models.filter(pk=haiku.pk).update(price_input_per_1m=PRICE_IN, price_output_per_1m=PRICE_OUT)
    return haiku


def haiku_answers(apps, schema_editor):
    alias = schema_editor.connection.alias
    policy = apps.get_model("assistant", "AIRoutingPolicy").objects.using(alias).filter(active_model__isnull=False).first()
    if policy is None:
        return
    models = apps.get_model("assistant", "AIModel").objects.using(alias)
    haiku = haiku_of(models, anthropic_provider(apps.get_model("assistant", "AIProvider").objects.using(alias)))
    qwen = models.filter(model_id=QWEN).exclude(pk=haiku.pk).order_by("created_at").first()
    policy.active_model = haiku
    if qwen is not None:
        policy.fallback_model = qwen
    elif policy.fallback_model_id == haiku.pk:
        policy.fallback_model = None
    policy.updated_by = None
    policy.save(update_fields=["active_model", "fallback_model", "updated_by", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0009_keys_from_environment'),
    ]

    operations = [
        migrations.RunPython(haiku_answers, migrations.RunPython.noop),
    ]
