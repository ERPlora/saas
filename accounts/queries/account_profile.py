"""Account → Profile: who the account is, and the change of address waiting for its code."""

import time
from typing import Any

from live.context import OperationContext
from live.operations import INTERNAL, operation

from accounts.models import EmailChangeRequest, ProfilePhoto
from accounts.queries.account_lookup import account_of
from accounts.queries.account_sessions import current_session_key
from accounts.queries.ways_in import email_is_proven
from accounts.schemas import ProfileGetIn, ProfileOut


#: Seconds a code works (the mail says so: ``emails.CODE_MINUTES``).
EMAIL_CODE_LIFETIME = 15 * 60


def email_change_of(user, request):
    """The change of address ``user`` asked for in ``request``'s session and can still finish, if any."""
    change = EmailChangeRequest.objects.filter(user=user).first()
    if (
        change is None
        or change.session_key != current_session_key(request)
        or time.time() - change.created_at.timestamp() > EMAIL_CODE_LIFETIME
    ):
        return None
    return change


def pending_email_of(user, request=None) -> str | None:
    """The address waiting for its code in this session (``accounts.email.change``), if any."""
    change = email_change_of(user, request)
    return change.email if change is not None else None


def profile_of(user, request=None) -> dict[str, Any]:
    photo = ProfilePhoto.objects.filter(user=user).first()
    return {
        "id": user.pk,
        "email": user.email,
        "email_verified": email_is_proven(user, user.email),
        "pending_email": pending_email_of(user, request),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name(),
        "photo": photo.data_url() if photo is not None else None,
        "has_password": user.has_usable_password(),
        "date_joined": user.date_joined,
    }


@operation(
    "accounts.profile.get",
    kind="query",
    permission="accounts.view",
    input=ProfileGetIn,
    output=ProfileOut,
    ai=INTERNAL,  # photo
)
def profile_get(ctx: OperationContext, data: ProfileGetIn) -> dict[str, Any]:
    """Account → Profile of the signed-in account."""
    return profile_of(account_of(ctx), ctx.request)
