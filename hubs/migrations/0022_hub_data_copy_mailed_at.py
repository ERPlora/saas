"""Schema: ``Hub.data_copy_mailed_at``, when the owner of a deleted business was told the copy of its data is ready
(PLAN-DB round 2026-10-30, proposals (a) and (k); ``services.reconcile``). Nullable, so the code before it keeps
running during the deploy (expand); backwards, the column goes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hubs', '0021_plan_copy_on_sale'),
    ]

    operations = [
        migrations.AddField(
            model_name='hub',
            name='data_copy_mailed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='copy of the data announced at'),
        ),
    ]
