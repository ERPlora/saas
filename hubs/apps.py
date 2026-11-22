"""The businesses of the SaaS: plans and the taxonomy of sectors and business types.

A LiveAppConfig of kind "platform": always on, at the project root next to ``base/``, without module
fields (no requires, category, premium or menu of its own). Being a LiveAppConfig is what lets the API
mount its router (``live.ninja.mount_app_routers``).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class HubsConfig(LiveAppConfig):
    name = "hubs"
    label = "hubs"
    kind = "platform"
    verbose_name = _("Businesses")
    default_auto_field = "django.db.models.BigAutoField"
    # Every signed-in account (role "account", base.operations) reads and acts on its own businesses;
    # which business and what it may do there is checked in each operation by its HubMember role.
    permissions = {
        "hubs.view": _("View their businesses, members and usage"),
        "hubs.manage": _("Create, change and delete businesses, invite members and transfer ownership"),
    }
    role_permissions = {"account": ["hubs.*"]}

    def ready(self):
        super().ready()
        from allauth.account.signals import email_changed

        from accounts import signals as account_signals
        from hubs import auditlog
        from hubs.services import account_changes
        from hubs import checks  # noqa: F401  (registers the system checks)

        # The audit trail of what a business pays and who pays it (ACCOUNTS-F36).
        auditlog.register()

        # What an account's own changes mean to its businesses (accounts never imports hubs): its sessions
        # end there too, and their snapshots drop it or carry its new address.
        account_signals.sessions_ended.connect(account_changes.end_account_sessions, dispatch_uid="hubs.sessions_ended")
        account_signals.account_deleting.connect(account_changes.account_leaving, dispatch_uid="hubs.account_deleting")
        email_changed.connect(account_changes.account_email_changed, dispatch_uid="hubs.email_changed")
