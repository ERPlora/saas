"""Data: the paid cards stop promising infrastructure (Ioan, 2026-10-24; PLAN-SAAS §9, round 2026-10-24b).

0013 seeded Pro, Enterprise and Max with copy that sold infrastructure: «isolated infrastructure», «dedicated
infrastructure with autoscaling, disaster recovery…», «container autoscaling», «disaster recovery (PITR)», «advanced
monitoring», «single-node performance». The plans no longer sell infrastructure (round 6) and nobody runs that, yet
the Store shows it to a business that already pays. From here each card says only what its row gives: its database
throughput against Starter's (``max_db_connections`` 12 / 24 / 48 against 3) or Pro's, Enterprise's messages against
Pro's, no cap on devices or users, its ``support_level`` (priority email; agreed in contract) and Max's named contact,
a feature it keeps. The plans, their prices and their limits do not move.

Only the columns of ``COPY`` are written, each only while it still reads 0013's words: what staff wrote in the admin
is theirs. Reverse: each goes back to 0013's words while it still reads this migration's. Idempotent; a database
without the rows is left as it is. Frozen in literals: a migration is history.
"""

from django.db import migrations

#: slug → column → (0013's words, the words from here).
COPY = {
    "pro": {
        "description_en": (
            "High performance on isolated infrastructure, with a full API for your integrations.",
            "Four times the database capacity of Starter, for businesses with many devices and users, with priority "
            "email support.",
        ),
        "description_es": (
            "Alto rendimiento en infraestructura aislada, con API completa para tus integraciones.",
            "El cuádruple de capacidad de base de datos que Starter, para negocios con muchos dispositivos y usuarios, "
            "con soporte por email prioritario.",
        ),
        "features_en": (
            [
                "Everything in Standard",
                "Four times the database throughput of Starter",
                "Isolated infrastructure",
                "Priority email support (business hours)",
            ],
            [
                "Everything in Standard",
                "Four times the database throughput of Starter",
                "Priority email support (business hours)",
            ],
        ),
        "features_es": (
            [
                "Todo lo del plan Standard",
                "El cuádruple de capacidad de base de datos que Starter",
                "Infraestructura aislada",
                "Soporte por email prioritario (horario laboral)",
            ],
            [
                "Todo lo del plan Standard",
                "El cuádruple de capacidad de base de datos que Starter",
                "Soporte por email prioritario (horario laboral)",
            ],
        ),
    },
    "enterprise": {
        "description_en": (
            "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
            "Twice the database throughput of Pro and more assistant and WhatsApp messages, for businesses with many "
            "devices and users, with support agreed in contract.",
        ),
        "description_es": (
            "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato.",
            "El doble de capacidad de base de datos que Pro y más mensajes del asistente y de WhatsApp, para negocios "
            "con muchos dispositivos y usuarios, con soporte acordado en contrato.",
        ),
        "features_en": (
            [
                "Everything in Pro",
                "Eight times the database throughput of Starter",
                "Automatic container autoscaling",
                "Disaster recovery (PITR)",
                "Advanced monitoring",
                "Support channels and escalation agreed in contract",
            ],
            [
                "Everything in Pro",
                "Eight times the database throughput of Starter",
                "Support channels and escalation agreed in contract",
            ],
        ),
        "features_es": (
            [
                "Todo lo del plan Pro",
                "Ocho veces la capacidad de base de datos de Starter",
                "Autoescalado automático de contenedores",
                "Recuperación ante desastres (PITR)",
                "Monitoreo avanzado",
                "Canales de soporte y escalado acordados en contrato",
            ],
            [
                "Todo lo del plan Pro",
                "Ocho veces la capacidad de base de datos de Starter",
                "Canales de soporte y escalado acordados en contrato",
            ],
        ),
    },
    "max": {
        "description_en": (
            "Maximum single-node performance, for the most demanding businesses.",
            "Sixteen times the database capacity of Starter and a named technical contact, for the most demanding "
            "businesses.",
        ),
        "description_es": (
            "Máximo rendimiento de un solo nodo, para los negocios más exigentes.",
            "Dieciséis veces la capacidad de base de datos que Starter y un responsable técnico asignado, para los "
            "negocios más exigentes.",
        ),
    },
}


def _rewrite(apps, source: int, target: int) -> None:
    Plan = apps.get_model("hubs", "Plan")
    for slug, columns in COPY.items():
        for column, words in columns.items():
            Plan.objects.filter(slug=slug, **{column: words[source]}).update(**{column: words[target]})


def describe_what_the_plans_give(apps, schema_editor):
    _rewrite(apps, 0, 1)


def give_back_the_words_of_0013(apps, schema_editor):
    _rewrite(apps, 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ("hubs", "0019_plan_max_apps"),
    ]

    operations = [
        migrations.RunPython(describe_what_the_plans_give, give_back_the_words_of_0013),
    ]
