"""Django admin of accounts: users (with their preferences and photo), their hub memberships (the jump's
mirror), the one-time codes and the API keys (a superuser revokes them, and issues one for a team account). The sessions are
``allauth.usersessions``' own page, read only; a superuser closes them («Close sessions», ACCOUNTS-F19).

«Open in the Hub admin» (ronda 13, PLAN §18.1.6), on every membership row and on the «Hubs» page
(``/admin/accounts/hubs/``, routed in ``config/urls.py``): the staff jump from ``erplora.com/admin``
to the hub's deep link ``hubs.erplora.com/admin/hub/<slug>/``. The jump starts at the Hub
(``<HUB_ADMIN_ORIGIN>/auth/login?hub=<slug>&next=/admin/hub/<slug>/``), which binds it to the browser
with its ``state`` cookie and sends it to ``/hub-login/?audience=hub-admin`` (``accounts.handoff``):
there the one-time ``hub-admin`` code is minted and auto-posted to ``HUB_ADMIN_CALLBACK_URL``. The
staff never type ``hubs.erplora.com``.

``/admin/login/`` hands over to the SaaS's sign-in, ``LOGIN_URL`` (``admin_login``, installed by
``config/urls.py``), which asks for the mailed code; with ``ACCOUNTS_MFA_ENABLED`` on, the staff enter only with
an authenticator app (``admin_has_permission``, ACCOUNTS-F20; without one, ``/2fa`` to set it up) and the jump also
needs the authenticator app's code in the session.
"""

from urllib.parse import urlencode, urlsplit

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from allauth.usersessions.admin import UserSessionAdmin as AllauthUserSessionAdmin
from allauth.usersessions.models import UserSession

from accounts import queries, services
from accounts.models import (
    API_KEY_SCOPES,
    ApiKey,
    AuthExchangeCode,
    EmailChangeRequest,
    HubMembership,
    ProfilePhoto,
    User,
    UserPreferences,
)

OPEN_IN_HUB_ADMIN = _("Open in the Hub admin")
#: The Vue page of the second factor's settings, where staff without an authenticator app set it up (ACCOUNTS-F20).
TWO_FACTOR_SETTINGS = "/2fa"

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


class ReadOnlyInline(admin.StackedInline):
    """What the account chose in the Account page, seen only: it changes it there."""

    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UserPreferencesInline(ReadOnlyInline):
    model = UserPreferences
    fields = ("theme_mode", "hub_alerts", "updated_at")
    readonly_fields = fields


class ProfilePhotoInline(ReadOnlyInline):
    model = ProfilePhoto
    fields = ("preview", "content_type", "updated_at")
    readonly_fields = fields

    @admin.display(description=_("photo"))
    def preview(self, obj):
        return format_html('<img src="{}" alt="" width="96" height="96" style="object-fit: cover">', obj.data_url())


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserEditForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "language", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser", "language")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("id", "last_login", "date_joined", "terms_accepted_at", "terms_version", "privacy_version")
    inlines = [UserPreferencesInline, ProfilePhotoInline, HubMembershipInline]
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "language")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
        # What the account accepted (ACCOUNTS-G119): evidence, so nobody edits it here.
        (_("Terms and privacy"), {"fields": ("terms_accepted_at", "terms_version", "privacy_version")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),)
    actions = ("close_sessions",)

    def get_inlines(self, request, obj):
        # Adding is email + password only (as Django's UserAdmin); hubs are given once it exists.
        if obj is None:
            return []
        # A read-only box with no row (an account still on the defaults) would be an empty heading.
        return [
            inline
            for inline in self.inlines
            if not issubclass(inline, ReadOnlyInline) or inline.model.objects.filter(user=obj).exists()
        ]

    def has_close_sessions_permission(self, request):
        return request.user.is_superuser

    @admin.action(
        description=_("Close all their sessions"),
        permissions=["close_sessions"],
    )
    def close_sessions(self, request, queryset):
        """An incident (ACCOUNTS-F19): the accounts picked are signed out everywhere and asked for their app's code
        again on every browser."""
        count = services.close_sessions(by=request.user, users=list(queryset.values_list("pk", flat=True)))
        self.message_user(request, gettext("Sessions closed: %(count)s.") % {"count": count}, messages.SUCCESS)


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


def admin_has_permission(request: HttpRequest) -> bool:
    """Who enters the admin (``admin.site.has_permission``, installed by ``config/urls.py``): an active staff account,
    as Django's rule, and with ``ACCOUNTS_MFA_ENABLED`` only one with an authenticator app (ACCOUNTS-F20; PLAN-SAAS
    «2FA obligatorio en el admin»). The account is checked, as in today's SaaS: the sign-in asked the app's code (or
    a browser the account trusts skipped it). Recovery codes alone are no second factor."""
    user = request.user
    if not (user.is_active and user.is_staff):
        return False
    return not settings.ACCOUNTS_MFA_ENABLED or queries.has_totp(user)


def _owes_the_app(request: HttpRequest) -> bool:
    """Signed-in staff kept out of the admin only for lack of an authenticator app."""
    user = request.user
    return user.is_authenticated and user.is_active and user.is_staff and not admin.site.has_permission(request)


@never_cache
def admin_login(request: HttpRequest, extra_context=None) -> HttpResponse:
    """``/admin/login/``: the SaaS's sign-in, never Django's own.

    Django's admin login signs in through ``django.contrib.auth`` alone, without allauth's stages, so
    without the code mailed at every sign-in (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``) and without the
    authenticator app (``ACCOUNTS_MFA_ENABLED``). It signs nobody in (not even by ``POST``): the visitor
    goes to ``LOGIN_URL?next=…`` (the launcher's sign-in, allauth.headless), whose code steps
    (``/verify-email``, ``/2fa/authenticate``) record both. Staff already signed in go where they were
    going; staff without the authenticator app the admin needs (``admin_has_permission``) go to set it up on
    ``/2fa``, which comes back to ``next`` (never a 403: old SAAS_AUTH-F08); any other signed-in account gets 403,
    never the login: the sign-in sends a signed-in account straight to ``next`` (the admin), which would send it back
    here.
    Ported from ERPlora/saas ``_admin_login`` (``config/urls.py``), there only with the second factor on.
    """
    next_url = _admin_next(request)
    if admin.site.has_permission(request):
        return HttpResponseRedirect(next_url)
    if _owes_the_app(request):
        return HttpResponseRedirect(f"{TWO_FACTOR_SETTINGS}?{urlencode({'next': next_url}, safe='/')}")
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


class ApiKeyIssueForm(forms.ModelForm):
    """«Add API key» (ACCOUNTS-F31): a team account, a name, its permissions and when it expires."""

    scopes = forms.MultipleChoiceField(
        label=_("permissions"), choices=list(API_KEY_SCOPES.items()), widget=forms.CheckboxSelectMultiple
    )
    expires_in_days = forms.TypedChoiceField(
        label=_("expires"),
        choices=[("90", _("In 90 days")), ("30", _("In 30 days")), ("", _("Never"))],
        coerce=int,
        empty_value=None,
        required=False,
        initial="90",
    )

    class Meta:
        model = ApiKey
        fields = ("user", "name", "scopes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = get_user_model().objects.filter(is_staff=True, is_active=True).order_by("email")
        self.fields["user"].help_text = _("Team accounts only: a customer creates its own keys in Account › API keys.")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """Who has which key, what it may do, when it was last used (ported from ERPlora/saas ``apps/auth/apikeys``).

    An account issues its keys in the Account page. A superuser issues one here for a team account («Add API key»,
    PLAN-SAAS §1.1, ronda 2026-10-15b), through ``services.issue_api_key``: the answer shows the key once
    (``response_add``, never cached) and nothing keeps it in clear. A key is never changed and the hash is never shown;
    deleting is not offered (revoking is the audit trail). A superuser can cut keys on the spot («Revoke»);
    ``support`` sees them.
    """

    add_form = ApiKeyIssueForm
    add_fieldsets = ((None, {"fields": ("user", "name", "scopes", "expires_in_days")}),)

    list_display = ("name", "user", "display_prefix", "scopes", "created_at", "last_used_at", "expires_at", "revoked_at")
    list_filter = ("revoked_at", "expires_at")
    search_fields = ("name", "prefix", "user__email")
    ordering = ("-created_at",)
    fields = ("name", "user", "display_prefix", "scopes", "created_at", "expires_at", "last_used_at", "revoked_at")
    readonly_fields = fields
    actions = ("revoke",)

    @admin.display(description=_("prefix"))
    def display_prefix(self, obj):
        return f"{obj.display_prefix}…"

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_revoke_permission(self, request):
        return request.user.is_superuser

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        """Issue the key through its operation (never ``obj.save()``) and keep the answer for ``response_add`` only."""
        data = form.cleaned_data
        issued = services.issue_api_key(
            data["user"],
            name=data["name"],
            scopes=data["scopes"],
            expires_in_days=data["expires_in_days"],
            by=request.user,
        )
        obj.pk = issued.key.id
        obj.refresh_from_db()
        request.issued_api_key_secret = issued.secret

    def response_add(self, request, obj, post_url_continue=None):
        response = TemplateResponse(
            request,
            "admin/accounts/apikey/issued.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.opts,
                "title": gettext("API key issued"),
                "key": obj,
                "secret": request.issued_api_key_secret,
            },
        )
        add_never_cache_headers(response)
        return response

    @admin.action(description=_("Revoke the selected keys (they stop working at once)"), permissions=["revoke"])
    def revoke(self, request, queryset):
        count = services.revoke_api_keys(queryset, by=request.user)
        self.message_user(
            request,
            gettext("Keys revoked: %(count)s.") % {"count": count},
            messages.SUCCESS,
        )


@admin.register(EmailChangeRequest)
class EmailChangeRequestAdmin(admin.ModelAdmin):
    """Read only: a change of email waiting for its code (``accounts.email.change``); never the code's hash nor the
    session it is bound to."""

    list_display = ("user", "email", "attempts", "created_at")
    search_fields = ("user__email", "email")
    fields = ("user", "email", "attempts", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# allauth's page of the sessions searches ``user__username``, which this account model has not.
admin.site.unregister(UserSession)

# allauth names neither its model nor its fields (Django's «user session», «created at»…, English in every language):
# the admin names them in the staff's language (ACCOUNTS-F19). Only the live names: Django's migrations read the
# model's own options (``_meta.original_attrs``), so allauth's migrations stay as they are.
UserSession._meta.verbose_name = _("user session")
UserSession._meta.verbose_name_plural = _("user sessions")


@admin.register(UserSession)
class UserSessionAdmin(AllauthUserSessionAdmin):
    """Who is signed in where (``allauth.usersessions``): read only. Deleting a row would only hide a session that
    still signs in; a superuser ends the picked ones with «Close the selected sessions» (ACCOUNTS-F19), which also
    asks their businesses; ``support`` sees them. Every column and label is named here, in the staff's language."""

    list_display = ("account", "signed_in", "last_used", "ip_address", "browser")
    search_fields = ["user__email", "ip"]
    fields = ("account", "signed_in", "last_used", "ip_address", "browser", "session_key", "session_data")
    readonly_fields = fields
    actions = ("close_sessions",)

    @admin.display(description=_("Account"), ordering="user__email")
    def account(self, session):
        return session.user

    @admin.display(description=_("Signed in"), ordering="created_at")
    def signed_in(self, session):
        return session.created_at

    @admin.display(description=_("Last used"), ordering="last_seen_at")
    def last_used(self, session):
        return session.last_seen_at

    @admin.display(description=_("IP address"), ordering="ip")
    def ip_address(self, session):
        return session.ip

    @admin.display(description=_("Browser"))
    def browser(self, session):
        return session.user_agent

    @admin.display(description=_("Session data"))
    def session_data(self, session):
        return session.data

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_close_sessions_permission(self, request):
        return request.user.is_superuser

    @admin.action(description=_("Close the selected sessions"), permissions=["close_sessions"])
    def close_sessions(self, request, queryset):
        count = services.close_sessions(by=request.user, sessions=list(queryset))
        self.message_user(request, gettext("Sessions closed: %(count)s.") % {"count": count}, messages.SUCCESS)
