from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class AccountsConfig(LiveAppConfig):
    """Accounts, sign-in and the jump to a hub. A platform app (``kind = "platform"``): always on,
    at the project root next to ``base/`` (round 15, PLAN §20.2); the API mounts its router
    (``live.ninja.mount_app_routers``). No menu and no permissions of its own yet."""

    name = "accounts"
    label = "accounts"
    kind = "platform"
    verbose_name = _("Accounts")

    def ready(self):
        from allauth.account.signals import password_reset

        from accounts import checks  # noqa: F401  (registers the system checks)
        from accounts.services import prove_mailbox_by_reset

        # A password set from the key mailed by «Forgot your password?» proves the mailbox (L1-A2).
        password_reset.connect(prove_mailbox_by_reset, dispatch_uid="accounts.prove_mailbox_by_reset")
