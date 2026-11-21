"""The member of the staff acting on the assistant's admin pages, as the services see them, and the gate of its
asynchronous pages."""

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse
from live.context import OperationContext, Scope
from live.errors import OperationError


def staff_context(request) -> OperationContext:
    """The member of the staff acting, as the services see it: their own channel, ``assistant.manage`` (which the
    services back with the model permission of each change) and the admin's language."""
    return OperationContext(
        scope=Scope("user", str(request.user.pk)),
        actor=request.user,
        permissions=frozenset({"assistant.manage"}),
        language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
        request=request,
    )


def refusals(error: OperationError) -> list[str]:
    return list((error.fields or {}).values()) or [error.message]


async def staff_gate(admin_site, request, permissions) -> HttpResponseRedirect | None:
    """For an asynchronous page of the admin: who is not in the admin goes to sign in (as ``admin_view`` does), a
    member of the staff without ``permissions`` gets a 403."""
    if not await sync_to_async(admin_site.has_permission)(request):
        return redirect_to_login(request.get_full_path(), reverse("admin:login", current_app=admin_site.name))
    allowed = await sync_to_async(lambda: all(request.user.has_perm(p) for p in permissions))()
    if not allowed:
        raise PermissionDenied
    return None
