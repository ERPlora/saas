"""Who may run the reads of the AI gateway.

``staff_with`` is the gate every operation of the staff passes: an active member of the staff holding the model
permission of Django that backs it. ``platform_only`` is the gate of the operations only the platform runs.
"""

from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import PermissionDenied


def staff_with(ctx: OperationContext, *permissions: str):
    """The active member of the staff running ``ctx`` who holds every one of ``permissions``; anybody else, 403."""
    user = ctx.actor
    if not (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and all(user.has_perm(permission) for permission in permissions)
    ):
        with translation.override(ctx.language):
            raise PermissionDenied(
                _("Only ERPlora's staff with this permission configure the AI."), code="assistant.staff_only"
            )
    return user


def platform_only(ctx: OperationContext) -> None:
    """Only the platform (the Hub's doors, the commands) runs this operation."""
    if ctx.actor != "system":
        with translation.override(ctx.language):
            raise PermissionDenied(_("Only the platform asks this."), code="assistant.platform_only")
