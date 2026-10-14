"""Data: the platform's ``support`` group sees the account plane of every business, and changes nothing
(PLAN-SAAS §2.1 round 11: superuser + ``support``, view only; plan 2026-10-13, L1-A2).

``view_*`` of ``Hub``, ``HubMember``, ``HubOwnershipTransfer``, ``BillingProfile``, ``Subscription``,
``SubscriptionItem`` and ``SessionRevocation``, as ``accounts``' ``0003_support_group`` gives it the accounts.
Without the group (created by that migration) there is nothing to give. Reverse: the permissions leave the
group.
"""

from django.db import migrations

SUPPORT_GROUP = "support"
VIEW_ONLY_MODELS = (
    "hub",
    "hubmember",
    "hubownershiptransfer",
    "billingprofile",
    "subscription",
    "subscriptionitem",
    "sessionrevocation",
)


def _permissions(apps, alias):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    for model_name in VIEW_ONLY_MODELS:
        model = apps.get_model("hubs", model_name)
        # On a fresh database Django creates content types and permissions after migrating
        # (post_migrate); these rows are the same ones, so it finds them and adds no duplicate.
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="hubs", model=model_name)
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
        ("hubs", "0006_adopt_seed_hubs"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(let_support_view, stop_support_viewing),
    ]
