"""A row of the assistant's usage per business, month and model (a demo, per demo and model; an account, per account,
month and model). The rows kept before it stay as they are, with the model empty: nothing recorded which model
answered them.

Going back joins the rows of each business and month (each demo; each account and month) into one again, their
figures added and the earliest mark of each mail kept, so the constraints of one row per month fit again.
"""

from django.conf import settings
from django.db import migrations, models

FIGURES = (
    "messages",
    "tokens_input",
    "tokens_output",
    "tokens_embedding",
    "transcriptions",
    "speech_characters",
    "cost_usd",
)
MARKS = ("near_warned_at", "spent_warned_at")


def join_the_models(apps, schema_editor):
    usage = apps.get_model("assistant", "AssistantUsage").objects.using(schema_editor.connection.alias)
    kept = {}
    for row in usage.order_by("created_at", "id"):
        key = ("demo", row.demo) if row.demo else (row.hub_id, row.user_id, row.month)
        first = kept.setdefault(key, row)
        if first is row:
            continue
        for figure in FIGURES:
            setattr(first, figure, getattr(first, figure) + getattr(row, figure))
        for mark in MARKS:
            setattr(first, mark, min(filter(None, (getattr(first, mark), getattr(row, mark))), default=None))
        row.delete()
    for row in kept.values():
        row.model = ""
        row.save(update_fields=[*FIGURES, *MARKS, "model"])


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0010_haiku_answers"),
        ("hubs", "0033_member_accountant_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="assistantusage",
            options={
                "ordering": ["-month", "hub__name", "demo", "user__email", "model"],
                "verbose_name": "assistant usage record",
                "verbose_name_plural": "assistant usage records",
            },
        ),
        migrations.RemoveConstraint(model_name="assistantusage", name="assistant_usage_one_per_month"),
        migrations.RemoveConstraint(model_name="assistantusage", name="assistant_usage_one_per_demo"),
        migrations.RemoveConstraint(model_name="assistantusage", name="assistant_usage_one_per_account_month"),
        migrations.AddField(
            model_name="assistantusage",
            name="model",
            field=models.CharField(
                blank=True,
                default="",
                help_text="The name the provider's API gives it; empty in the records from before the model was kept.",
                max_length=128,
                verbose_name="model",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, join_the_models),
        migrations.AddConstraint(
            model_name="assistantusage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("hub__isnull", False)),
                fields=("hub", "month", "model"),
                name="assistant_usage_one_per_model_month",
            ),
        ),
        migrations.AddConstraint(
            model_name="assistantusage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("demo", ""), _negated=True),
                fields=("demo", "model"),
                name="assistant_usage_one_per_demo_model",
            ),
        ),
        migrations.AddConstraint(
            model_name="assistantusage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("user", "month", "model"),
                name="assistant_usage_one_per_account_model_month",
            ),
        ),
    ]
