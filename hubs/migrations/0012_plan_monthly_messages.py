"""The monthly messages of each plan, assistant and WhatsApp (Ioan, 2026-10-15; PLAN-SAAS §3.6).

Two columns on ``Plan``: ``assistant_messages_per_month`` (one request of the user to the assistant is one
message) and ``whatsapp_messages_per_month``. 0 = none, never «unlimited». There is no pack nor overage
(ADR-0474): a business that needs more moves a plan up. They travel in the hub's state snapshot and the Hub
counts them.

The columns are new, so every row already in production reads 0 after ``AddField``; ``RunPython`` gives the
plans the seed (``sync_hub_plans``, empty since 0013) carried the figures of that day, frozen here as literals (a migration is
history: a later change of the seed never rewrites what this one did). Standard doubles Starter;
``payment-test`` reads as Starter; the upgrade-only tiers (``pro``, ``enterprise``, ``max``) get the figures of
the old stack (ADR-0474, levels pro and enterprise). Only a row that exists is written.

Reverse: the two columns go (``RunPython`` has nothing to undo). Idempotent; a database without the rows is
left as it is.
"""

from django.db import migrations, models

#: slug → (assistant, WhatsApp) messages a month on 2026-10-15, the seed's plans.
MONTHLY_MESSAGES = {
    "free": (30, 30),
    "starter": (300, 150),
    "standard": (600, 300),
    "payment-test": (300, 150),
    # The upgrade-only tiers: the old stack's levels (ADR-0474), pro and enterprise.
    "pro": (1000, 500),
    "enterprise": (3000, 800),
    "max": (3000, 800),
}


def give_monthly_messages(apps, schema_editor):
    Plan = apps.get_model("hubs", "Plan")
    for slug, (assistant, whatsapp) in MONTHLY_MESSAGES.items():
        Plan.objects.filter(slug=slug).update(
            assistant_messages_per_month=assistant, whatsapp_messages_per_month=whatsapp
        )


class Migration(migrations.Migration):
    dependencies = [
        ("hubs", "0011_three_plans_on_sale"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="assistant_messages_per_month",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Requests to the AI assistant a business may make each month (0 = none).",
                verbose_name="AI assistant messages a month",
            ),
        ),
        migrations.AddField(
            model_name="plan",
            name="whatsapp_messages_per_month",
            field=models.PositiveIntegerField(
                default=0,
                help_text="WhatsApp messages a business may send each month (0 = none).",
                verbose_name="WhatsApp messages a month",
            ),
        ),
        migrations.RunPython(give_monthly_messages, migrations.RunPython.noop),
    ]
