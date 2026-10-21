from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class AccountsConfig(LiveAppConfig):
    """Accounts, sign-in, the jump to a hub and the Account page (profile, security, preferences, API keys). A
    platform app (``kind = "platform"``): always on, at the project root next to ``base/`` (round 15, PLAN
    §20.2); the API mounts its router (``live.ninja.mount_app_routers``). No menu of its own (the panel's
    is ``base/navigation.py``).

    Every signed-in account (role ``account``, ``base.operations``) reads (``accounts.view``) and changes
    (``accounts.manage``) its own account; the operations only ever touch the caller's."""

    name = "accounts"
    label = "accounts"
    kind = "platform"
    verbose_name = _("Accounts")
    permissions = ["accounts.view", "accounts.manage"]
    role_permissions = {"account": ["accounts.*"]}

    def ready(self):
        from allauth.account.signals import password_changed, password_reset, password_set, user_signed_up
        from django.contrib.auth.signals import user_logged_in

        from accounts import checks  # noqa: F401  (registers the system checks)
        from accounts.services import accept_legal_texts, password_changed_ends_sessions, prove_mailbox_by_reset

        # A password set from the key mailed by «Forgot your password?» proves the mailbox (L1-A2).
        password_reset.connect(prove_mailbox_by_reset, dispatch_uid="accounts.prove_mailbox_by_reset")
        # A new password ends the account's sessions in its businesses too (PLAN-SAAS §2.1; L3-A).
        for name, signal in (("changed", password_changed), ("set", password_set), ("reset", password_reset)):
            signal.connect(password_changed_ends_sessions, dispatch_uid=f"accounts.ends_sessions.password_{name}")
        # Creating the account and signing in accept today's terms and privacy policy (ACCOUNTS-G119).
        user_signed_up.connect(accept_legal_texts, dispatch_uid="accounts.accept_legal_texts.signed_up")
        user_logged_in.connect(accept_legal_texts, dispatch_uid="accounts.accept_legal_texts.logged_in")
