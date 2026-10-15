"""Data: the platform's ``support`` group sees the signed authorisations of every business, and decides
nothing (PLAN-SAAS §2.1 round 11: superuser + ``support``, view only; plan 2026-10-15).

``view_representationgrant``, as ``hubs``' ``0007_support_views_the_account_plane`` gives it the account plane.
Approving, returning or withdrawing needs ``change_representationgrant``, which only a member of the staff
granted it holds. Without the group (created by ``accounts``' ``0003_support_group``) there is nothing to give.
Reverse: the permission leaves the group.
"""

from django.db import migrations

SUPPORT_GROUP = "support"
VIEW_ONLY_MODELS = ("representationgrant",)


def _permissions(apps, alias):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    for model_name in VIEW_ONLY_MODELS:
        model = apps.get_model("fiscal", model_name)
        # On a fresh database Django creates content types and permissions after migrating
        # (post_migrate); these rows are the same ones, so it finds them and adds no duplicate.
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="fiscal", model=model_name)
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=content_type,
            codename=f"view_{model_name}",
            defaults={"name": f"Can view {model._meta.verbose_name_raw}"},
        )
        yield permission


def let_support_view(apps, schema_editor):
    alias = schema_editor.connection.alias
    group = apps.get_model("auth", "Group").objects.using(alias).filter(name=SUPPORT_GROUP).first()
    if group is not None:
        group.permissions.add(*_permissions(apps, alias))


def stop_support_viewing(apps, schema_editor):
    alias = schema_editor.connection.alias
    group = apps.get_model("auth", "Group").objects.using(alias).filter(name=SUPPORT_GROUP).first()
    if group is not None:
        group.permissions.remove(*_permissions(apps, alias))


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_support_group"),
        ("fiscal", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(let_support_view, stop_support_viewing),
    ]
