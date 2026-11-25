"""A model keeps the prices of its provider's cache, and a month's row the input tokens read from it and written to it.

Claude Haiku 5.5 at Anthropic's own address gets Anthropic's prices of its cache (USD per million tokens: a read
0.01, a write that lasts five minutes 0.125). Any other model keeps them empty: its cache is paid as input.
"""

from decimal import Decimal

from django.db import migrations, models

HAIKU = "claude-haiku-5-5"
CACHE_READ, CACHE_WRITE = Decimal("0.01"), Decimal("0.125")


def haiku_cache_prices(apps, schema_editor):
    models_ = apps.get_model("assistant", "AIModel").objects.using(schema_editor.connection.alias)
    models_.filter(model_id=HAIKU, provider__kind="anthropic", provider__base_url="").update(
        price_cache_read_per_1m=CACHE_READ, price_cache_write_per_1m=CACHE_WRITE
    )


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0011_usage_per_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='aimodel',
            name='price_cache_read_per_1m',
            field=models.DecimalField(blank=True, decimal_places=4, help_text="USD per million input tokens read from the provider's cache. Empty: the input price.", max_digits=10, null=True, verbose_name='cache read price'),
        ),
        migrations.AddField(
            model_name='aimodel',
            name='price_cache_write_per_1m',
            field=models.DecimalField(blank=True, decimal_places=4, help_text="USD per million input tokens written to the provider's cache. Empty: the input price.", max_digits=10, null=True, verbose_name='cache write price'),
        ),
        migrations.AddField(
            model_name='assistantusage',
            name='tokens_cache_read',
            field=models.PositiveBigIntegerField(default=0, help_text="Of the input tokens, those read from the provider's cache.", verbose_name='cache read tokens'),
        ),
        migrations.AddField(
            model_name='assistantusage',
            name='tokens_cache_write',
            field=models.PositiveBigIntegerField(default=0, help_text="Of the input tokens, those written to the provider's cache.", verbose_name='cache write tokens'),
        ),
        migrations.RunPython(haiku_cache_prices, migrations.RunPython.noop),
    ]
