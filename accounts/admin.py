"""Django admin of accounts: users, their hub memberships (the jump's mirror) and the one-time codes (read only).

«Open in the Hub admin» (ronda 13, PLAN §18.1.6), on every membership row and on the «Hubs» page
(``/admin/accounts/hubs/``, routed in ``config/urls.py``): the staff jump from ``erplora.com/admin``
to the hub's deep link ``hubs.erplora.com/admin/hub/<slug>/``. The jump starts at the Hub
(``<HUB_ADMIN_ORIGIN>/auth/login?hub=<slug>&next=/admin/hub/<slug>/``), which binds it to the browser
with its ``state`` cookie and sends it to ``/hub-login/?audience=hub-admin`` (``accounts.handoff``):
there the one-time ``hub-admin`` code is minted and auto-posted to ``HUB_ADMIN_CALLBACK_URL``. The
staff never type ``hubs.erplora.com``.

With ``ACCOUNTS_MFA_ENABLED`` on, the jump needs the second factor in the session and
``/admin/login/`` is allauth's login (``admin_login``, installed by ``config/urls.py``).
"""

from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from accounts import queries, services
from accounts.models import AuthExchangeCode, HubMembership, User

OPEN_IN_HUB_ADMIN = _("Open in the Hub admin")

#: Why the jump to the Hub admin failed, by the ``?error=`` the Hub sends back to «Hubs» (ERPlora/saas#1):
#: the codes of ``hub-next/base/auth.py`` and ``auth_views.py``, and the 400s of ``/internal/auth/redeem``
#: (``accounts/internal.py``), which the Hub forwards as they are.
JUMP_FAILED = {
    "invalid_code": _("The access to the Hub admin expired or was already used. Open it again from this page."),
    "invalid_request": _(
        "The Hub sent ERPlora a request it could not read. Try again; if it keeps happening, tell the development team."
    ),
    "hub_unauthorized": _(
        "ERPlora rejected the Hub's signed request (wrong internal key or clock out of sync). Tell the development team."
    ),
    "saas_unavailable": _("The Hub could not reach ERPlora to check the access. Try again in a moment."),
    "unknown_role": _(
        "The Hub does not accept your account's role. Only ERPlora's administrators and support can open the Hub admin."
    ),
    "not_platform_staff": _("Your account is not part of ERPlora's staff, so it cannot open the Hub admin."),
    "user_inactive": _("Your account is deactivated in the Hub admin. Ask an ERPlora administrator to reactivate it."),
}
#: Any other code: the value comes from the URL, so it is never shown.
JUMP_FAILED_UNKNOWN = _("The Hub admin could not be opened. Try again from this page.")


def open_hub_admin_url(slug: str) -> str | None:
    """The admin's jump to ``slug`` in the Hub admin, or ``None`` if ``slug`` is no hub (rows saved unvalidated).

    ``http://hubs.localhost:8000/auth/login?hub=a&next=/admin/hub/a/`` locally,
    ``https://hubs.erplora.com/auth/login?hub=a&next=/admin/hub/a/`` in production (``HUB_ADMIN_ORIGIN``).
    """
    if not services.is_hub_slug(slug):
        return None
    query = urlencode({"hub": slug, "next": queries.hub_admin_path(slug)}, safe="/")
    return f"{settings.HUB_ADMIN_ORIGIN}{queries.HUB_START_PATH}?{query}"


class UserCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class HubMembershipInline(admin.TabularInline):
    """The account's access to hubs, seen only: it mirrors the members of each business (``hubs`` admin)."""

    model = HubMembership
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserEditForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "language", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser", "language")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("id", "last_login", "date_joined")
    inlines = [HubMembershipInline]
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "language")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),)

    def get_inlines(self, request, obj):
        # Adding is email + password only (as Django's UserAdmin); hubs are given once it exists.
        return self.inlines if obj is not None else []


@admin.register(HubMembership)
class HubMembershipAdmin(admin.ModelAdmin):
    """Read only: the mirror of the businesses' members that the jump reads, written only by
    ``hubs.services.sync_access`` (L1-A2). People are added, changed and removed on the business
    (``hubs`` admin, «Members»)."""

    list_display = ("user", "hub_slug", "role", "created_at", "open_in_hub_admin")
    list_filter = ("role",)
    search_fields = ("user__email", "hub_slug")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Hub admin"))
    def open_in_hub_admin(self, obj):
        url = open_hub_admin_url(obj.hub_slug)
        if url is None:
            return self.get_empty_value_display()
        return format_html('<a class="button" href="{}">{}</a>', url, OPEN_IN_HUB_ADMIN)


def _admin_next(request: HttpRequest) -> str:
    """Where the admin was going: a path of this host, never the login itself (it would loop)."""
    index = reverse("admin:index")
    next_url = request.GET.get("next") or index
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return index
    if urlsplit(next_url).path == reverse("admin:login"):
        return index
    return next_url


@never_cache
def admin_login(request: HttpRequest, extra_context=None) -> HttpResponse:
    """``/admin/login/``: Django's own with the flag off; allauth's login with ``ACCOUNTS_MFA_ENABLED`` on.

    Django's admin login signs in through ``django.contrib.auth`` alone, without allauth's stages, so
    without the second factor. With the flag on it signs nobody in (not even by ``POST``): the visitor
    goes to ``LOGIN_URL?next=…``, whose code stage records the second factor. Staff already signed
    in go where they were going; any other signed-in account gets 403, never the login: allauth's
    login sends a signed-in account straight to ``next`` (the admin), which would send it back here.
    Ported from ERPlora/saas ``_admin_login`` (``config/urls.py``).
    """
    if not settings.ACCOUNTS_MFA_ENABLED:
        return AdminSite.login(admin.site, request, extra_context)
    next_url = _admin_next(request)
    if admin.site.has_permission(request):
        return HttpResponseRedirect(next_url)
    if request.user.is_authenticated:
        raise PermissionDenied
    return HttpResponseRedirect(f"{settings.LOGIN_URL}?{urlencode({'next': next_url}, safe='/')}")


def hubs_view(request: HttpRequest) -> HttpResponse:
    """«Hubs» (``/admin/accounts/hubs/``): every hub with members, each with «Open in the Hub admin».

    Wrapped in ``admin.site.admin_view`` by ``config/urls.py``: only active staff, and of them only
    whoever may view memberships (superuser and ``support``). A failed jump comes back here with
    ``?error=<code>``: the page says why, from ``JUMP_FAILED``, never echoing the value.
    """
    if not request.user.has_perm("accounts.view_hubmembership"):
        raise PermissionDenied
    if "error" in request.GET:
        messages.error(request, JUMP_FAILED.get(request.GET["error"], JUMP_FAILED_UNKNOWN))
    hubs = [
        {"slug": slug, "members": members, "url": open_hub_admin_url(slug)}
        for slug, members in queries.hubs_with_members()
    ]
    context = {
        **admin.site.each_context(request),
        "title": _("Hubs"),
        "opts": HubMembership._meta,
        "hubs": hubs,
        "open_in_hub_admin": OPEN_IN_HUB_ADMIN,
    }
    return TemplateResponse(request, "admin/accounts/hubs.html", context)


@admin.register(AuthExchangeCode)
class AuthExchangeCodeAdmin(admin.ModelAdmin):
    """Audit only: a code is minted by /hub-login/ and spent by the hub, never by hand."""

    list_display = ("user", "hub_slug", "audience", "created_at", "expires_at", "used_at")
    list_filter = ("audience", "hub_slug")
    search_fields = ("user__email", "hub_slug")
    exclude = ("code_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
