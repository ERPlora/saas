"""Data: the database line of the cards says what a recovery keeps.

0013 seeded Free and Starter with «Managed database, … with continuous backups and point-in-time recovery for 14
days», which 0021 kept (Standard, Pro, Enterprise and Max say «Everything in …»). The public web, the plan's page, the
panel's Store and the assistant paint it. A business that invoices with VeriFactu in production never goes back whole
to a moment: what it sent to the tax agency stays sent, so the Hub refuses that return and restores a copy aside, from
which it gets back what it lost. From here the line says both, as Business Central and Jetpack's
backups for WooCommerce word it: the window, and what a recovery keeps.

The line is the unit, not the card: wherever a plan's features still read 0013's line word for word, that line moves
to this migration's, in its place; every other line, and a line staff rewrote in the admin, stay theirs. Reverse: the
line goes back to 0013's words wherever it still reads this migration's. Idempotent; a database without the rows is
left as it is. Frozen in literals: a migration is history.
"""

from django.db import migrations

#: column → (0013's line, the line from here).
LINES = {
    "features_en": (
        "Managed database, replicated across several European data centres, with continuous backups and "
        "point-in-time recovery for 14 days",
        "Managed database, replicated across several European data centres, with continuous backups: recover your "
        "data from any moment of the last 14 days, and what was already sent to the tax agency is kept",
    ),
    "features_es": (
        "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
        "continuas y recuperación a cualquier momento de los últimos 14 días",
        "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad continuas: "
        "recuperas los datos de cualquier momento de los últimos 14 días, y lo ya enviado a Hacienda se conserva",
    ),
}


def _rewrite(apps, source: int, target: int) -> None:
    Plan = apps.get_model("hubs", "Plan")
    for column, words in LINES.items():
        for pk, lines in Plan.objects.filter(**{f"{column}__contains": [words[source]]}).values_list("pk", column):
            rewritten = [words[target] if line == words[source] else line for line in lines]
            Plan.objects.filter(pk=pk).update(**{column: rewritten})


def say_what_a_recovery_keeps(apps, schema_editor):
    _rewrite(apps, 0, 1)


def give_back_the_line_of_0013(apps, schema_editor):
    _rewrite(apps, 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ("hubs", "0028_hub_maintenance"),
    ]

    operations = [
        migrations.RunPython(say_what_a_recovery_keeps, give_back_the_line_of_0013),
    ]
