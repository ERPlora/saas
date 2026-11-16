"""The platform's staff: ERPlora's own admin and support accounts, never a customer of a hub."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from accounts.services.account_businesses import on_a_business


class PlatformRoleRefused(Exception):
    """The account cannot take a platform role: it is a customer of a hub, or the role is unknown."""


class SupportGroupMissing(Exception):
    """The ``support`` group (data migration ``0003_support_group``) is not in the database."""


#: Platform roles, only for the SaaS admin: never stored in ``hubs.HubMember`` nor sent to a hub.
PLATFORM_ADMIN = "admin"
PLATFORM_SUPPORT = "support"
PLATFORM_ROLES = (PLATFORM_ADMIN, PLATFORM_SUPPORT)
#: The group of ``support`` (view only on accounts), created by a data migration.
SUPPORT_GROUP = "support"


def create_platform_user(email: str, role: str, password: str | None = None):
    """Create or update a member of the platform's staff; return ``(user, created)``.

    ``admin`` is a superuser; ``support`` is staff in the ``support`` group (view only). An
    existing account takes the role and keeps its password unless ``password`` is given; a new
    one without ``password`` has no usable password. A customer of a hub (also one whose invitation still waits, or
    whose business is in its days of recovery: ``on_a_business``) and the store review account are refused: platform
    and customer roles never share an account.
    """
    if role not in PLATFORM_ROLES:
        raise PlatformRoleRefused(f"unknown platform role {role!r}")
    user_model = get_user_model()
    email = user_model.objects.normalize_email(email).lower()
    with transaction.atomic():
        support = Group.objects.filter(name=SUPPORT_GROUP).first()
        if support is None:
            raise SupportGroupMissing(SUPPORT_GROUP)
        user = user_model.objects.select_for_update().filter(email=email).first()
        created = user is None
        if created:
            user = user_model(email=email)
        elif on_a_business(user):
            raise PlatformRoleRefused(f"{email} is a customer of a hub")
        elif user.is_store_review_account:
            # Its sign-in skips the mailed code: never a way into the admin.
            raise PlatformRoleRefused(f"{email} is a store review account")
        if password is not None:
            user.set_password(password)
        elif created:
            user.set_unusable_password()
        user.is_staff = True
        user.is_superuser = role == PLATFORM_ADMIN
        user.save()
        if role == PLATFORM_SUPPORT:
            user.groups.add(support)
        else:
            user.groups.remove(support)
    return user, created
