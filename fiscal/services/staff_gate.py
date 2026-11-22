"""The check every decision of the staff goes through: an active member of the staff holding the permission."""

from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import PermissionDenied


def _staff_with(ctx: OperationContext, permission: str):
    """The active member of the staff running ``ctx`` who holds ``permission``; anybody else, 403."""
    user = ctx.actor
    if not (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and user.has_perm(permission)
    ):
        raise PermissionDenied(
            _("Only ERPlora's staff decide on an authorisation."),
            code="fiscal.staff_only",
        )
    return user
