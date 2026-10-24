"""How many modules a business may choose to turn on (Ioan, 2026-10-24): ``Plan.max_apps``.

Every module is on every plan; a plan caps only the modules the business picks, not the ones they require (as Odoo's
«one app free» plus its dependencies). 0 = no limit.

The column is new, so every row already in production reads 0 after ``AddField``; ``RunPython`` gives the plans of
the catalogue their figure, frozen here as literals (a migration is history). Free 15 and each plan up doubles the one
below: never under what a business born on the biggest vertical template chooses (the restaurant's 12 roots on
2026-10-24, with ``tip`` and ``website`` on their way) plus a margin. ``payment-test`` reads as Starter; the
upgrade-only tiers (``pro``, ``enterprise``, ``max``) keep 0, no cap. Only a row that exists is written, and a plan
staff added keeps 0. The column has a database default, so a row the code before it writes without the column is valid
during a deploy.

Reverse: the column goes (``RunPython`` has nothing to undo). Idempotent; a database without the rows is left as it is.
"""

from django.db import migrations, models

#: slug → modules a business may choose to turn on, on 2026-10-24.
MAX_APPS = {
    "free": 15,
    "starter": 30,
    "standard": 60,
    "payment-test": 30,
}


def give_module_caps(apps, schema_editor):
    Plan = apps.get_model("hubs", "Plan")
    for slug, max_apps in MAX_APPS.items():
        Plan.objects.filter(slug=slug).update(max_apps=max_apps)


class Migration(migrations.Migration):

    dependencies = [
        ('hubs', '0018_plan_field_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='max_apps',
            field=models.PositiveIntegerField(db_default=0, default=0, help_text='Modules a business may choose to turn on; the ones they require do not count (0 = unlimited).', verbose_name='modules turned on'),
        ),
        migrations.RunPython(give_module_caps, migrations.RunPython.noop),
    ]
