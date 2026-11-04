# The contract step of 0011 (saas#199): the table of the copy of a business's members goes, with its permissions and,
# when no audit entry names it, its content type.
#
# 0011 left the table for the tasks of the release before it. Every release deployed since (82a437c on) knows nothing of
# it, and ``ecs-rollback.sh`` only goes back to the revision right before the one running, so nothing reads it any more.
#
# The audit entries of this type are kept: ``auditlog.LogEntry.content_type`` cascades, so deleting the content type
# would take with it what ``cleanup_old_logs`` still keeps (90 days). It stays while an entry names it, the staff go on
# reading them (their type by its code name, with no link), and ``cleanup_old_logs`` takes it with the last one
# (``accounts.services.forget_the_retired_audit_type``). A line of Django's admin history only loses its type.
#
# The model comes back into the state just to be deleted: Django then drops the table and, going back, recreates it
# empty as 0011 left it, without its foreign key. From there 0011's own way back rebuilds it from the members. Django
# makes no content type or permission for a model outside the code, so going back brings those back here.

import uuid

import django.db.models.deletion
import django.utils.timezone
import live.slugs
from django.conf import settings
from django.db import migrations, models

MODEL = "hubmembership"
ACTIONS = ("add", "change", "delete", "view")


def forget_what_names_it(apps, schema_editor):
    alias = schema_editor.connection.alias
    kind = apps.get_model("contenttypes", "ContentType").objects.using(alias).filter(app_label="accounts", model=MODEL)
    apps.get_model("auth", "Permission").objects.using(alias).filter(content_type__in=kind).delete()
    if not apps.get_model("auditlog", "LogEntry").objects.using(alias).filter(content_type__in=kind).exists():
        kind.delete()


def bring_back_what_names_it(apps, schema_editor):
    alias = schema_editor.connection.alias
    kind, _ = (
        apps.get_model("contenttypes", "ContentType")
        .objects.using(alias)
        .get_or_create(app_label="accounts", model=MODEL)
    )
    permissions = {
        action: apps.get_model("auth", "Permission")
        .objects.using(alias)
        .get_or_create(content_type=kind, codename=f"{action}_{MODEL}", defaults={"name": f"Can {action} hub membership"})[0]
        for action in ACTIONS
    }
    support = apps.get_model("auth", "Group").objects.using(alias).filter(name="support").first()
    if support is not None:
        support.permissions.add(permissions["view"])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_retire_the_hub_membership_copy'),
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('auditlog', '0017_add_actor_email'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='HubMembership',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                        ('hub_slug', models.CharField(max_length=63, validators=[live.slugs.hub_slug_validator], verbose_name='hub')),
                        ('role', models.CharField(choices=[('hub_owner', 'Owner'), ('hub_admin', 'Admin'), ('hub_manager', 'Manager'), ('hub_employee', 'Employee')], max_length=16, verbose_name='role')),
                        ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created at')),
                        ('user', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name='hub_memberships', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                    ],
                    options={
                        'verbose_name': 'hub membership',
                        'verbose_name_plural': 'hub memberships',
                        'ordering': ['hub_slug'],
                        'constraints': [models.UniqueConstraint(fields=('user', 'hub_slug'), name='accounts_membership_user_hub')],
                    },
                ),
            ],
        ),
        migrations.DeleteModel(name='HubMembership'),
        migrations.RunPython(forget_what_names_it, bring_back_what_names_it),
    ]
