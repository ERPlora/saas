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
        from allauth.account.signals import user_logged_in as signed_in
        from allauth.usersessions import signals as usersessions
        from django.contrib.auth.signals import user_logged_in

        from accounts import checks  # noqa: F401  (registers the system checks)
        from accounts.services import (
            accept_legal_texts,
            password_changed_ends_sessions,
            prove_mailbox_by_reset,
            record_sign_in,
        )

        # A sign-in drops the account's dead sessions in one go and records its own, in place of allauth's receiver,
        # which asked about every open session on its own (``record_sign_in``). allauth.usersessions is ready by now:
        # it comes first in INSTALLED_APPS.
        signed_in.disconnect(receiver=usersessions.on_user_logged_in)
        signed_in.connect(record_sign_in, dispatch_uid="accounts.record_sign_in")

        # A password set from the key mailed by «Forgot your password?» proves the mailbox (L1-A2).
        password_reset.connect(prove_mailbox_by_reset, dispatch_uid="accounts.prove_mailbox_by_reset")
        # A new password ends the account's sessions in its businesses too (PLAN-SAAS §2.1; L3-A).
        for name, signal in (("changed", password_changed), ("set", password_set), ("reset", password_reset)):
            signal.connect(password_changed_ends_sessions, dispatch_uid=f"accounts.ends_sessions.password_{name}")
        # Creating the account and signing in accept today's terms and privacy policy (ACCOUNTS-G119).
        user_signed_up.connect(accept_legal_texts, dispatch_uid="accounts.accept_legal_texts.signed_up")
        user_logged_in.connect(accept_legal_texts, dispatch_uid="accounts.accept_legal_texts.logged_in")
        # Who changed an account, its access to a business, its keys and its sessions (ACCOUNTS-F36).
        from accounts import auditlog

        auditlog.register()

        # The admin's index names each section once, in the staff's language (config/tests/test_admin_index.py):
        # allauth's ``account`` only holds the email addresses (it read «Accounts», as this app does), and its
        # authenticators and sessions are named after their classes, which no catalog translates. Display only:
        # migrations read ``Meta`` (``_meta.original_attrs``), so no label, table or migration changes.
        from allauth.mfa.models import Authenticator
        from allauth.usersessions.models import UserSession
        from django.apps import apps

        apps.get_app_config("account").verbose_name = _("Email addresses")
        Authenticator._meta.verbose_name = _("authenticator")
        Authenticator._meta.verbose_name_plural = _("authenticators")
        UserSession._meta.verbose_name = _("user session")
        UserSession._meta.verbose_name_plural = _("user sessions")
