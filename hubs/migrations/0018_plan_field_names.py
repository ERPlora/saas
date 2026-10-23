"""HUBS-F31 and HUBS-F05: the fields of a plan get names the admin shows in the staff's language («Precio al mes»,
«Solo como mejora»…), where a Spanish admin read «PRICE MONTHLY» and «Por is active». Only Django's state changes: no
SQL, both ways.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hubs', '0017_taxonomy_field_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plan',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created at'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='display_order',
            field=models.IntegerField(default=0, verbose_name='order'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='included_level',
            field=models.CharField(choices=[('free', 'Free'), ('basic', 'Basic'), ('pro', 'Pro'), ('enterprise', 'Enterprise')], default='free', max_length=16, verbose_name='level of modules'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='includes_custom_domain',
            field=models.BooleanField(default=False, verbose_name='own domain'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='internal_only',
            field=models.BooleanField(default=False, help_text='Never offered to customers; only staff may buy it (saas#1052).', verbose_name='internal'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Available for new subscriptions.', verbose_name='active'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='max_db_connections',
            field=models.PositiveIntegerField(default=1, help_text='Database transactions a hub runs at a time per process (PLAN §14.2).', verbose_name='database transactions at a time'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='max_devices',
            field=models.PositiveIntegerField(default=0, help_text='Devices per hub (0 = unlimited).', verbose_name='devices'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='max_hubs_per_org',
            field=models.PositiveIntegerField(default=1, help_text='Hubs a customer may run on this plan (0 = unlimited).', verbose_name='businesses per customer'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='max_users',
            field=models.PositiveIntegerField(default=0, help_text='Active users per hub (0 = unlimited).', verbose_name='people'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='price_annual',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Annual price in EUR, VAT excluded (0 = no annual option).', max_digits=10, verbose_name='annual price'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='price_monthly',
            field=models.DecimalField(decimal_places=2, help_text='Monthly price in EUR, VAT excluded (net).', max_digits=10, verbose_name='monthly price'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='slug',
            field=models.SlugField(help_text='Stable identifier of the plan (free, starter…).', unique=True, verbose_name='identifier'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='statement_timeout_seconds',
            field=models.PositiveIntegerField(default=5, help_text='Longest database statement of a hub, in seconds (PLAN §14.2).', verbose_name='longest database statement (seconds)'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='stripe_price_id',
            field=models.CharField(blank=True, help_text='Stripe price of the monthly option.', max_length=255, verbose_name='Stripe monthly price'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='stripe_price_id_annual',
            field=models.CharField(blank=True, help_text='Stripe price of the annual option.', max_length=255, verbose_name='Stripe annual price'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='stripe_product_id',
            field=models.CharField(blank=True, max_length=255, verbose_name='Stripe product'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='support_level',
            field=models.CharField(choices=[('community', 'Community forum'), ('email', 'Email'), ('priority_email', 'Priority email'), ('contract', 'Agreed in contract')], default='community', max_length=16, verbose_name='support'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='trial_period_days',
            field=models.PositiveIntegerField(default=0, help_text='Free trial days (0 = no trial).', verbose_name='trial days'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='updated at'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='upgrade_only',
            field=models.BooleanField(default=False, help_text='Only offered as an upgrade, never at sign-up.', verbose_name='only as an upgrade'),
        ),
    ]
