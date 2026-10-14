"""Reads of accounts: the hubs an account can enter (``accounts.hub.list``, the launcher's), the
re-read of an account before a live re-run, the hubs the admin's «Open in the Hub admin» lists, the
authenticators of the second factor (``mfa.py``), and whether an account proved its email or has any
way in (the invitation of ``hubs``, saas#2541)."""

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode, urlsplit

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Unauthorized
from live.operations import operation

from accounts.models import HubMembership
from accounts.schemas import HubListIn, HubListOut


def hub_slugs_of(user) -> list[str]:
    """The slugs of the hubs ``user`` is a member of, alphabetically."""
    return list(HubMembership.objects.filter(user=user).order_by("hub_slug").values_list("hub_slug", flat=True))


def hubs_with_members() -> list[tuple[str, int]]:
    """Every hub with members, alphabetically, as ``(slug, member count)``.

    The SaaS has no ``Hub`` model yet (``HubMembership`` stands in), so a hub is a slug with members.
    """
    rows = HubMembership.objects.values("hub_slug").annotate(members=Count("id")).order_by("hub_slug")
    return [(row["hub_slug"], row["members"]) for row in rows]


def hub_admin_path(slug: str) -> str:
    """The deep link of the hub ``slug`` in the Hub's admin at ``hubs.erplora.com`` (PLAN §18.1.5)."""
    return f"/admin/hub/{slug}/"


def active_user(pk):
    """The account ``pk`` read again from the database, or ``None`` if it was deleted or deactivated."""
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


def has_totp(user) -> bool:
    """Whether ``user`` has turned on an authenticator app. Recovery codes alone are no second factor:
    they are the way back in when the phone is lost."""
    if not user.is_authenticated:
        return False
    return Authenticator.objects.filter(user_id=user.pk, type=Authenticator.Type.TOTP).exists()


def owns_authenticator(user, ids: Iterable) -> bool:
    """Whether one of ``ids`` (pks of ``Authenticator``) is an authenticator of ``user``."""
    pks = {pk for pk in ids if pk is not None}
    if not pks:
        return False
    return Authenticator.objects.filter(user_id=user.pk, pk__in=pks).exists()


def hub_origin(slug: str) -> str:
    """``scheme://host`` of the hub ``slug``, from the callback the jump posts to (``HUB_CALLBACK_TEMPLATE``)."""
    callback = urlsplit(settings.HUB_CALLBACK_TEMPLATE.format(slug=slug))
    return f"{callback.scheme}://{callback.netloc}"


#: Where a hub starts every jump into it: it binds the jump to the browser (the ``state`` cookie)
#: and only then sends it to the SaaS's ``/hub-login/`` (login CSRF; ``accounts.handoff``).
HUB_START_PATH = "/auth/login"


def local_path(value: str) -> str:
    """``value`` if it is a path on the hub (``/…``, not ``//host`` nor ``/\\host``), else ``/``."""
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
        return "/"
    return value


def hub_start_url(slug: str, next_path: str = "/") -> str:
    """The jump to the hub ``slug``, landing on ``next_path`` there (a non-local path lands on ``/``).

    It starts at the hub: ``http://a.localhost:8000/auth/login?next=/`` locally,
    ``https://a.erplora.com/auth/login?next=/`` in production (``hub_origin``). A link straight to
    ``/hub-login/`` would carry no ``state``, and the Hub refuses it. Also for ``hubs`` (one place).
    """
    return f"{hub_origin(slug)}{HUB_START_PATH}?{urlencode({'next': local_path(next_path)}, safe='/')}"


@operation("accounts.hub.list", kind="query", permission=None, input=HubListIn, output=HubListOut)
def hub_list(ctx: OperationContext, data: HubListIn) -> dict[str, Any]:
    """The hubs of the signed-in account, alphabetically, each with its host and the jump to it.

    No permission: every account may read its own hubs. But only an account: a caller without one
    (anonymous) is refused, whatever route or stream asks.
    """
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to see your businesses."))
    return {
        "hubs": [
            {"slug": slug, "host": urlsplit(hub_origin(slug)).netloc, "url": hub_start_url(slug)}
            for slug in hub_slugs_of(ctx.actor)
        ]
    }


def email_is_proven(user, email: str) -> bool:
    """Whether ``user`` holds ``email`` by proof rather than by having typed it first (saas#2541).

    Proven means a **verified** ``EmailAddress`` for that address (another verified address proves
    nothing). Two kinds of account have nothing to prove and count as proven: staff, and an account with
    **no** address on record (made by an invitation, which leaves no password until the mailbox's owner
    claims it, by the console or by staff). Ported from ERPlora/saas ``apps/auth/users/services.py``.
    """
    if user.is_staff or user.is_superuser:
        return True
    addresses = EmailAddress.objects.filter(user=user)
    if not addresses.exists():
        return True
    return addresses.filter(email__iexact=email, verified=True).exists()


def has_no_way_in(user) -> bool:
    """Whether ``user`` has no way to sign in yet: no usable password and no linked Google. Whoever opens
    its mailbox claims it with «Forgot your password?» or with Google (the invitation's mail says so)."""
    return not user.has_usable_password() and not SocialAccount.objects.filter(user=user).exists()
