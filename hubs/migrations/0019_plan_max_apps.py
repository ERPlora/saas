"""How many modules a business may choose to turn on (Ioan, 2026-10-24): ``Plan.max_apps``.

Every module is on every plan; a plan caps only the modules the business picks, not the ones they require. 0 = no
limit, which every plan of the catalogue keeps (the figures are set later), so no row changes. The column has a
database default, so a row the code before it writes without the column is valid during a deploy. Reversible.
"""

from django.db import migrations, models


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
    ]
