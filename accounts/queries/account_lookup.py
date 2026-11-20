"""The account behind a call: the signed-in one, or one read again by its id."""

import uuid

from django.contrib.auth import get_user_model
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Unauthorized


def active_user(pk):
    """The account ``pk`` read again from the database, or ``None`` if it was deleted or deactivated."""
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


def stored_staff_flags(pk) -> tuple[bool, bool] | None:
    """``(is_staff, is_superuser)`` of account ``pk`` as saved, or ``None`` if it is not saved yet (``User.clean``
    tells raising a flag from keeping it)."""
    return get_user_model().objects.filter(pk=pk).values_list("is_staff", "is_superuser").first()


def account_of(ctx: OperationContext):
    """The account behind ``ctx``; without one, 401 (a live stream or a route always has one)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to manage your account."))
    return ctx.actor


def active_account(account_id: str):
    """The active account whose id is ``account_id`` (the Hub's session names it), or ``None`` (none, off, no id)."""
    try:
        account = uuid.UUID(account_id)
    except (TypeError, ValueError, AttributeError):
        return None
    return active_user(account)
