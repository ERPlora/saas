# «ERPlora news» governed no mail (ACCOUNTS-F23): the field leaves the model, its column stays (expand/contract).
#
# The deploy migrates before the tasks of the previous release stop, and they still read and write the column: it
# keeps its data and gets a database default (`db_default`), so a row the new code writes without it is valid. Its
# DROP COLUMN is the contract step, a later release. «Business notices» now names the one mail it governs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_user_terms_acceptance'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpreferences',
            name='marketing_emails',
            field=models.BooleanField(
                default=False, db_default=False, help_text='At most once a month.', verbose_name='ERPlora news'
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='userpreferences', name='marketing_emails'),
            ],
        ),
        migrations.AlterField(
            model_name='userpreferences',
            name='hub_alerts',
            field=models.BooleanField(
                default=True, help_text='When a business is ready to open.', verbose_name='business notices'
            ),
        ),
    ]
