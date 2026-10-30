"""Schema: ``Hub.data_copy_mailed_at``, when the owner of a deleted business was told the copy of its data is ready,
and ``Hub.data_copy_mail_attempts``, the passes its mail could not leave (PLAN-DB round 2026-10-30, proposals (a) and
(k); ``services.reconcile``). Nullable, and a default in the database, so the code before it keeps running during the
deploy (expand); backwards, the columns go.
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
        migrations.AddField(
            model_name='hub',
            name='data_copy_mail_attempts',
            field=models.PositiveSmallIntegerField(db_default=0, default=0, verbose_name="tries of the copy's mail"),
        ),
    ]
