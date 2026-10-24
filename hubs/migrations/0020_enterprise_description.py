"""Data: the Enterprise card stops promising dedicated infrastructure (Ioan, 2026-10-24; PLAN-SAAS §9, round 2026-10-24b).

0013 seeded Enterprise's description as «Dedicated infrastructure with autoscaling, disaster recovery and
contract-backed support»: infrastructure the plans no longer sell (round 6) and nobody runs, which the Store shows to a
business that already pays. From here it says only what the row gives, beside Pro's: twice its database throughput
(``max_db_connections`` 24 against 12, eight times Starter's 3), more assistant and WhatsApp messages (3000 / 800
against 1000 / 500) and no cap on devices or users. The plan, its price, its features and its limits do not move.

Only the two descriptions of the ``enterprise`` row are written, each only while it still reads 0013's words: what
staff wrote in the admin is theirs. Reverse: each goes back to 0013's words while it still reads this migration's.
Idempotent; a database without the row is left as it is. Frozen in literals: a migration is history.
"""

from django.db import migrations

#: 0013's words, by column.
OLD = {
    "description_en": "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
    "description_es": "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato.",
}
#: What the card says from here, by column.
NEW = {
    "description_en": (
        "Twice the database throughput of Pro and more assistant and WhatsApp messages, for businesses with many "
        "devices and users."
    ),
    "description_es": (
        "El doble de capacidad de base de datos que Pro y más mensajes del asistente y de WhatsApp, para negocios con "
        "muchos dispositivos y usuarios."
    ),
}


def _rewrite(apps, source: dict[str, str], target: dict[str, str]) -> None:
    Plan = apps.get_model("hubs", "Plan")
    for column, text in target.items():
        Plan.objects.filter(slug="enterprise", **{column: source[column]}).update(**{column: text})


def describe_what_enterprise_gives(apps, schema_editor):
    _rewrite(apps, OLD, NEW)


def give_back_the_words_of_0013(apps, schema_editor):
    _rewrite(apps, NEW, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("hubs", "0019_plan_max_apps"),
    ]

    operations = [
        migrations.RunPython(describe_what_enterprise_gives, give_back_the_words_of_0013),
    ]
