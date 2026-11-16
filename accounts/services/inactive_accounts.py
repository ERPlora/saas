"""GDPR: the accounts unused for two years go."""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from live.context import OperationContext
from live.errors import LiveMisuse
from live.operations import INTERNAL, operation

from accounts.schemas import InactiveAccountIn, InactiveAccountOut
from accounts.services.account_businesses import belongs_to_a_business
from accounts.services.account_deletion import _erase_account

logger = logging.getLogger("accounts.services")


#: Days without signing in on erplora.com that make an account unused (two years).
INACTIVE_DAYS = 730
#: ``accounts.profile.erase_inactive``: a system context only (no role grants it), on the account's channel.
ERASE_INACTIVE = "accounts.erase_inactive"


def _unused_since(inactive_days: int):
    """The accounts that may go: active, not staff, and without signing in (or, never signed in, created) since
    ``inactive_days`` ago."""
    from django.db.models import Q

    cutoff = timezone.now() - timedelta(days=inactive_days)
    return get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False).filter(
        Q(last_login__lt=cutoff) | Q(last_login__isnull=True, date_joined__lt=cutoff)
    )


def inactive_account_ids(*, inactive_days: int = INACTIVE_DAYS) -> list:
    """The ids of the accounts unused for ``inactive_days``, the oldest first: the candidates of a run."""
    return list(_unused_since(inactive_days).order_by("date_joined", "pk").values_list("pk", flat=True))


@operation(
    "accounts.profile.erase_inactive",
    kind="command",
    permission=ERASE_INACTIVE,
    input=InactiveAccountIn,
    output=InactiveAccountOut,
    ai=INTERNAL,  # scheduled
)
def profile_erase_inactive(ctx: OperationContext, data: InactiveAccountIn) -> dict:
    """Erase an account unused for ``inactive_days`` as its owner would delete it (``_erase_account``), on its own
    channel. Read again under its row's lock, so a sign-in since it was picked keeps it (``active``); one that belongs to
    a business stays (``member``): its last sign-in on erplora.com says nothing of its days in the business. Called
    only by ``erase_inactive_account``; no route."""
    if ctx.scope.key != str(data.user_id):
        raise LiveMisuse(f"accounts.profile.erase_inactive runs on the account's channel, not {ctx.scope.key!r}.")
    user = _unused_since(data.inactive_days).select_for_update().filter(pk=data.user_id).first()
    if user is None:
        return {"outcome": "active"}
    if belongs_to_a_business(user):
        return {"outcome": "member"}
    if not data.dry_run:
        _erase_account(ctx, user)
        logger.info("accounts.inactive_account_erased user=%s", data.user_id)
    return {"outcome": "erased"}


def erase_inactive_account(user_id, *, inactive_days: int = INACTIVE_DAYS, dry_run: bool = False) -> str:
    """``manage.py anonymize_old_users``'s step for one account: ``erased``, ``member`` or ``active``."""
    from live.context import Scope, system_context

    return profile_erase_inactive(
        system_context(Scope("user", str(user_id))),
        InactiveAccountIn(user_id=user_id, inactive_days=inactive_days, dry_run=dry_run),
    ).outcome
