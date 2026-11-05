"""The kind of Azure AI Speech leaves, and a provider of it leaves with it (saas#242, PLAN-SAAS round 2026-11-04c).

A row of that kind would be a choice no form accepts and an API no client speaks: it goes with its keys and its models,
and the policy lets go of a model of it (its foreign keys protect the model). Its identifiers go to the log, never a key.
On the way back the kind returns and the rows do not: a key is not kept around to restore it.
"""

import logging

from django.db import migrations, models

logger = logging.getLogger("assistant.migrations")


def remove_providers_of_azure_speech(apps, schema_editor):
    alias = schema_editor.connection.alias
    providers = apps.get_model("assistant", "AIProvider").objects.using(alias).filter(kind="azure_speech")
    slugs = sorted(providers.values_list("slug", flat=True))
    if not slugs:
        return
    policies = apps.get_model("assistant", "AIRoutingPolicy").objects.using(alias)
    for slot in ("active_model", "fallback_model"):
        policies.filter(**{f"{slot}__provider__kind": "azure_speech"}).update(**{slot: None})
    providers.delete()
    logger.warning("assistant.migration.azure_speech_removed providers=%s", slugs)



class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0007_aiprovider_azure_speech'),
    ]

    operations = [
        migrations.RunPython(remove_providers_of_azure_speech, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='aiprovider',
            name='kind',
            field=models.CharField(choices=[('openai', 'OpenAI'), ('anthropic', 'Anthropic'), ('gemini', 'Google Gemini'), ('deepseek', 'DeepSeek')], help_text="The API the provider speaks. A provider compatible with OpenAI's is «OpenAI» with its address.", max_length=16, verbose_name='API'),
        ),
    ]
