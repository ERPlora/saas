# The copy of a business's members that the jump read until saas#199: the model leaves the code, its table stays
# (expand/contract).
#
# The deploy migrates before the tasks of the previous release stop, and they still read and write the table: it keeps
# its rows. It loses its foreign key to the account: the code no longer knows the table, so deleting an account with a
# row left in it would fail. Its DROP TABLE is the contract step, a later release.
#
# Going back rebuilds it from the members, the rule the previous release keeps it by (the answered members of a business
# that still opens): the Hub trusts the role the SaaS answers, and a copy left as it was would let in whoever has left
# since. The rows of accounts deleted since go with it, or the foreign key would not come back.

from django.conf import settings
from django.db import migrations, models

CLOSED = ("deleting", "deleted")


def rebuild_the_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    copy = apps.get_model("accounts", "HubMembership")
    copy.objects.using(alias).all().delete()
    members = (
        apps.get_model("hubs", "HubMember")
        .objects.using(alias)
        .filter(accepted_at__isnull=False)
        .exclude(hub__status__in=CLOSED)
        .values_list("user_id", "hub__slug", "role")
    )
    copy.objects.using(alias).bulk_create(
        [copy(user_id=user_id, hub_slug=slug, role=role) for user_id, slug, role in members]
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_user_store_review_account'),
        ('hubs', '0024_support_views_the_daily_usage'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='HubMembership'),
            ],
            database_operations=[
                migrations.AlterField(
                    model_name='hubmembership',
                    name='user',
                    field=models.ForeignKey(
                        db_constraint=False,
                        on_delete=models.CASCADE,
                        related_name='hub_memberships',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='user',
                    ),
                ),
                migrations.RunPython(migrations.RunPython.noop, rebuild_the_copy),
            ],
        ),
    ]
