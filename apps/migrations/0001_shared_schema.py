# The `shared` schema of the `saas` database and its two tables (round 16, spec §3.2).
#
# The schema is created IF NOT EXISTS and never dropped: in production `bootstrap_databases`
# creates it first, with the default privileges that give the Hub's role (`hub_shared`) its
# SELECT, INSERT and UPDATE on the tables created here, so it must survive `migrate apps zero`.
# Reversing this migration drops `app` and `app_doc` and leaves the schema.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            "CREATE SCHEMA IF NOT EXISTS shared", reverse_sql=migrations.RunSQL.noop
        ),
        migrations.CreateModel(
            name="App",
            fields=[
                (
                    "id",
                    models.CharField(max_length=63, primary_key=True, serialize=False),
                ),
                ("name_en", models.CharField(max_length=80)),
                ("name_es", models.CharField(max_length=80)),
                ("summary_en", models.CharField(max_length=120)),
                ("summary_es", models.CharField(max_length=120)),
                ("description_en", models.TextField()),
                ("description_es", models.TextField()),
                ("icon", models.CharField(max_length=100)),
                ("icon_svg", models.TextField()),
                ("category", models.CharField(max_length=20)),
                ("premium", models.BooleanField()),
                ("requires", models.JSONField(default=list)),
                ("verticals", models.JSONField(default=list)),
                ("listed", models.BooleanField()),
                ("hub_version", models.CharField(max_length=64)),
                ("registered_at", models.DateTimeField()),
            ],
            options={
                "verbose_name": "app",
                "verbose_name_plural": "apps",
                "db_table": '"shared"."app"',
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="AppDoc",
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
                    "lang",
                    models.CharField(
                        choices=[("es", "es"), ("en", "en")], max_length=8
                    ),
                ),
                ("markdown", models.TextField()),
                ("source_hash", models.CharField(max_length=64)),
                ("updated_at", models.DateTimeField()),
                (
                    "app",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="docs",
                        to="apps.app",
                    ),
                ),
            ],
            options={
                "verbose_name": "app documentation",
                "verbose_name_plural": "app documentation",
                "db_table": '"shared"."app_doc"',
                "constraints": [
                    models.UniqueConstraint(
                        fields=("app", "lang"), name="shared_app_doc_app_lang_unique"
                    )
                ],
            },
        ),
    ]
