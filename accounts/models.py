"""Accounts of saas-next: who signs in, which hubs they belong to and the one-time jump code.

``User`` is ported from ERPlora/saas ``apps/auth/users/models.py`` (email as the identifier),
with a UUIDv7 primary key (PLAN-SAAS §6) and the account's language. ``HubMembership`` is the mirror
of the answered members of each business (``hubs.HubMember``) that the jump to a hub reads: written
only by ``hubs.services.sync_access``, retired once the jump reads ``HubMember`` (``hubs/README.md``).
``AuthExchangeCode`` is ported from the same file, stored hashed and bound to one hub
(PLAN-SAAS §2.1, §3.1 step 5). A hub slug follows the rule shared with hub-next
(``live.slugs``: one DNS label, never a reserved name such as ``hub`` or ``www``) and is never
``hubs``, the platform host of the Hub's admin (ronda 13, PLAN §18).
"""

import hashlib
import uuid

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
