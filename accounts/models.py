"""Accounts of saas-next: who signs in, which hubs they belong to, the one-time jump code and the
account's own settings (the Account page: preferences, photo and API keys; plan 2026-10-13, L3-A).

``User`` is ported from ERPlora/saas ``apps/auth/users/models.py`` (email as the identifier),
with a UUIDv7 primary key (PLAN-SAAS §6) and the account's language. ``HubMembership`` is the mirror
of the answered members of each business (``hubs.HubMember``) that the jump to a hub reads: written
only by ``hubs.services.sync_access``, retired once the jump reads ``HubMember`` (``hubs/README.md``).
``AuthExchangeCode`` is ported from the same file, stored hashed and bound to one hub
(PLAN-SAAS §2.1, §3.1 step 5). A hub slug follows the rule shared with hub-next
(``live.slugs``: one DNS label, never a reserved name such as ``hub`` or ``www``) and is never
``hubs``, the platform host of the Hub's admin (ronda 13, PLAN §18).
"""

import base64
import hashlib
import secrets
import string
import uuid
from datetime import date, datetime

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.slugs import hub_slug_validator


#: The versions of the terms (``/legal/terms/``) and of the privacy policy (``/legal/privacy/``) an account accepts
#: today: the «Last updated» date each page shows (``tests/test_terms.py`` keeps them equal). Update the page and
#: its date here together: every account then accepts the new text at its next sign-in.
TERMS_VERSION = date(2026, 10, 13)
PRIVACY_VERSION = date(2026, 10, 13)


class UserManager(BaseUserManager):
    """Manager of ``User``: the email is the identifier."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The email must be set.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if (
            extra_fields["is_staff"] is not True
            or extra_fields["is_superuser"] is not True
        ):
            raise ValueError(
                "A superuser must have is_staff=True and is_superuser=True."
            )
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """An ERPlora account: signs in with its email."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    email = models.EmailField(_("email"), unique=True, max_length=255)
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    language = models.CharField(
        _("language"),
        max_length=8,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    # What the account accepted by creating it or signing in under «By continuing you agree to our Terms &
    # Privacy Policy» (ACCOUNTS-G119): when, and the version of each text. Empty until its first sign-in.
    terms_accepted_at = models.DateTimeField(_("terms accepted at"), null=True, blank=True)
    terms_version = models.DateField(_("terms version"), null=True, blank=True)
    privacy_version = models.DateField(_("privacy policy version"), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name


class HubMembership(models.Model):
    """A user's access to one hub, with the role the hub will give them.

    The roles are the customer's (what a person is inside a hub) and travel to the hub as they
    are. Their ``hub_`` prefix keeps them apart from the platform's roles (Django's superuser and
    the ``support`` group of the admin), which are never stored here nor given to a hub's member:
    they only reach the Hub's Django admin, as ``platform_*``, with a ``hub-admin`` code. No
    customer role implies ``is_staff``.
    """

    class Role(models.TextChoices):
        OWNER = "hub_owner", _("Owner")
        ADMIN = "hub_admin", _("Admin")
        MANAGER = "hub_manager", _("Manager")
        EMPLOYEE = "hub_employee", _("Employee")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hub_memberships",
        verbose_name=_("user"),
    )
    hub_slug = models.CharField(
        _("hub"), max_length=63, validators=[hub_slug_validator]
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("hub membership")
        verbose_name_plural = _("hub memberships")
        ordering = ["hub_slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "hub_slug"], name="accounts_membership_user_hub"
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.hub_slug} ({self.get_role_display()})"


class AuthExchangeCode(models.Model):
    """A one-time, short-lived code that opens a session in one hub (OIDC authorization code).

    Only its SHA-256 travels to the database: a leaked row cannot be replayed. Bound to one
    user, one audience and one hub; ``used_at`` is stamped once, atomically, on redemption.
    ``hub-session`` opens a member's session in ``<slug>.erplora.com``; ``hub-admin`` opens a staff
    session in the Hub's admin at ``hubs.erplora.com``, on that hub (ronda 13, PLAN §18).
    """

    HUB_SESSION_AUDIENCE = "hub-session"
    HUB_ADMIN_AUDIENCE = "hub-admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    code_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_exchange_codes",
    )
    audience = models.CharField(max_length=32, default=HUB_SESSION_AUDIENCE)
    hub_slug = models.CharField(max_length=63, validators=[hub_slug_validator])
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("exchange code")
        verbose_name_plural = _("exchange codes")
        indexes = [models.Index(fields=["expires_at"], name="accounts_code_expires_at")]

    def __str__(self):
        return f"exchange-code<{self.user_id}@{self.hub_slug}>"

    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()


class UserPreferences(models.Model):
    """What the account chose in Account → Preferences: the theme mode and whether it gets business notices.

    Ported from ERPlora/saas ``apps/dashboard/settings`` without what the single panel dropped (palette,
    currency, menu order, developer mode; plan 2026-10-13 §3, round 17). The language is ``User.language``,
    which the mails and the jump to a hub already read. ``hub_alerts`` governs the mail that a business is
    ready (``hubs.emails.send_ready``); security, invoices and payments, a deleted business and what asks the
    person to act have no switch (ACCOUNTS-F23). «ERPlora news» (``marketing_emails``) governed no mail: its
    column waits for the contract step with a database default (migration 0009). No row means the defaults.
    """

    class ThemeMode(models.TextChoices):
        # The vocabulary of the shell (packages/ui shell/theme.ts, ``ThemeMode``).
        SYSTEM = "system", _("System")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences", verbose_name=_("user")
    )
    theme_mode = models.CharField(_("appearance"), max_length=8, choices=ThemeMode.choices, default=ThemeMode.SYSTEM)
    hub_alerts = models.BooleanField(
        _("business notices"), default=True, help_text=_("When a business is ready to open.")
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("preferences")
        verbose_name_plural = _("preferences")

    def __str__(self):
        return f"preferences<{self.user_id}>"


class ProfilePhoto(models.Model):
    """The account's photo: a small image kept in the database, already cleaned (``accounts.photos``).

    In the database because the SaaS has no media storage (``STORAGES["default"]`` is the task's own disk,
    lost on every deploy) and an avatar is small (``photos.MAX_PHOTO_BYTES``); the panel gets it as a data
    URL. One row per account, gone with it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="photo", verbose_name=_("user")
    )
    content_type = models.CharField(_("type"), max_length=16)
    data = models.BinaryField(_("image"))
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")

    def __str__(self):
        return f"photo<{self.user_id}>"

    def data_url(self) -> str:
        return f"data:{self.content_type};base64,{base64.b64encode(bytes(self.data)).decode()}"


#: Every account key starts so: the environment is written in the key (Stripe's ``sk_live_``), and ``erps``
#: tells it apart from a hub's ``erpk_live_`` (hub-next; plan 2026-10-13 §7 point 12, decided in L3-A).
API_KEY_PREFIX = "erps_live_"
API_KEY_SECRET_LENGTH = 48
#: The first characters of the secret, kept in clear and indexed: how a key is found before its hash is
#: compared (and how its owner tells it apart in the list).
API_KEY_PREFIX_LENGTH = 8
#: base62: a double click selects the whole key.
API_KEY_ALPHABET = string.ascii_letters + string.digits

#: What a key may open, with what the panel says next to it. ``<app>.read`` opens the app's queries and
#: ``<app>.write`` its commands, and only those declared with ``expose_api=True`` (``accounts.api_auth``).
API_KEY_SCOPES = {
    "hubs.read": _("Businesses · read"),
    "hubs.write": _("Businesses · write"),
    "billing.read": _("Invoices · read"),
}


class UnknownScope(ValueError):
    """A scope nobody registered: a typo, caught before it is written anywhere."""


def validate_scopes(scopes) -> list[str]:
    """``scopes`` without repeats, in order, or ``UnknownScope`` naming the unknown ones."""
    unknown = [scope for scope in scopes if scope not in API_KEY_SCOPES]
    if unknown:
        raise UnknownScope(f"unknown API key scope(s): {', '.join(sorted(unknown))}")
    return list(dict.fromkeys(scopes))


class ApiKey(models.Model):
    """A key that makes a request act as its account, bounded by its scopes (ported from ERPlora/saas
    ``apps/auth/apikeys``, ADR-0467: a key of a person; the hub keys are hub-next's, PLAN-SAAS §2.4).

    The table keeps the SHA-256 of the key and nothing else: its owner sees it once, when it is created.
    SHA-256 suffices for 48 random base62 characters (~285 bits); a slow hash would only slow every call.
    Revoking keeps the row (the audit trail); deleting the account deletes its keys.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys", verbose_name=_("user")
    )
    name = models.CharField(_("name"), max_length=120)
    prefix = models.CharField(_("prefix"), max_length=API_KEY_PREFIX_LENGTH, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(_("permissions"), default=list, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    last_used_at = models.DateTimeField(_("last used at"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)

    class Meta:
        verbose_name = _("API key")
        verbose_name_plural = _("API keys")
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"{self.name} ({self.display_prefix}…)"

    @property
    def display_prefix(self) -> str:
        return f"{API_KEY_PREFIX}{self.prefix}"

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def new_secret(cls) -> tuple[str, str, str]:
        """A fresh key: ``(secret, prefix, hash)``. The secret exists in clear only in this return value."""
        body = "".join(secrets.choice(API_KEY_ALPHABET) for _ in range(API_KEY_SECRET_LENGTH))
        raw = f"{API_KEY_PREFIX}{body}"
        return raw, body[:API_KEY_PREFIX_LENGTH], cls.hash_key(raw)

    @staticmethod
    def parse(raw: str) -> str | None:
        """The 48 characters after ``erps_live_`` of a well-formed key, ``None`` for anything else."""
        raw = (raw or "").strip()
        if not raw.startswith(API_KEY_PREFIX):
            return None
        body = raw.removeprefix(API_KEY_PREFIX)
        if len(body) != API_KEY_SECRET_LENGTH or any(char not in API_KEY_ALPHABET for char in body):
            return None
        return body

    def is_usable(self, now: datetime) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


class EmailChangeRequest(models.Model):
    """An account's change of email waiting for the code mailed to the new address (``accounts.email.change``).

    Bound to the session that asked (``session_key``): the code is of no use in any other. Only the code's
    SHA-256 is kept. The tries are counted here, consumed by one conditional ``UPDATE`` each, so requests
    racing in parallel cannot get more than ``services.EMAIL_CODE_ATTEMPTS`` between them. One per account: a
    new request replaces the one waiting; gone with the account.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_change", verbose_name=_("user")
    )
    session_key = models.CharField(max_length=40)
    email = models.EmailField(_("new email"), max_length=255)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("change of email")
        verbose_name_plural = _("changes of email")

    def __str__(self):
        return f"email-change<{self.user_id}>"
