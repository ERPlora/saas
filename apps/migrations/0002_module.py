# Module, only commercial (round 16, spec decision 7; PLAN-SAAS §2.6): in the SaaS's own schema
# (public), tied to `shared.app` by `slug` without a database FK (plan §3.l).

import uuid

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0001_shared_schema"),
    ]

    operations = [
        migrations.CreateModel(
            name="Module",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "slug",
                    models.CharField(
                        help_text="The label of the paid app in the Hub, as the catalog lists it.",
                        max_length=63,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[a-z][a-z0-9]*(_[a-z0-9]+)*$",
                                "Enter the label of an app of the Hub (inventory, whatsapp_inbox…).",
                            )
                        ],
                        verbose_name="app",
                    ),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("free", "Free"),
                            ("basic", "Basic"),
                            ("pro", "Pro"),
                            ("enterprise", "Enterprise"),
                        ],
                        default="basic",
                        max_length=16,
                        verbose_name="tier",
                    ),
                ),
                (
                    "price_monthly_cents",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Net monthly price in euro cents, VAT excluded.",
                        verbose_name="monthly price (cents)",
                    ),
                ),
                (
                    "price_annual_cents",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Net annual price in euro cents, VAT excluded (0 = no annual option).",
                        verbose_name="annual price (cents)",
                    ),
                ),
                (
                    "stripe_product_id",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Stripe product"
                    ),
                ),
                (
                    "stripe_price_id_monthly",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Stripe monthly price"
                    ),
                ),
                (
                    "stripe_price_id_annual",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Stripe annual price"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="On sale for new purchases.",
                        verbose_name="active",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "module",
                "verbose_name_plural": "modules",
                "ordering": ["slug"],
            },
        ),
    ]
