"""Django admin of the API keys: who has which key, a superuser revokes them and issues one for a team account."""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.template.response import TemplateResponse
from django.utils.cache import add_never_cache_headers
from django.utils.text import capfirst
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from accounts.models import API_KEY_SCOPES, ApiKey
from accounts.services import api_keys


class ApiKeyIssueForm(forms.ModelForm):
    """«Add API key»: a team account, a name, its permissions and when it expires."""

    scopes = forms.MultipleChoiceField(
        label=capfirst(_("permissions")), choices=list(API_KEY_SCOPES.items()), widget=forms.CheckboxSelectMultiple
    )
    expires_in_days = forms.TypedChoiceField(
        label=capfirst(_("expires")),
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
    """Who has which key, what it may do, when it was last used.

    An account issues its keys in the Account page. A superuser issues one here for a team account («Add API key»),
    through ``api_keys.issue_api_key``: the answer shows the key once (``response_add``, never cached) and nothing
    keeps it in clear. A key is never changed and the hash is never shown; deleting is not offered (revoking is the
    audit trail). A superuser can cut keys on the spot («Revoke»); ``support`` sees them.
    """

    add_form = ApiKeyIssueForm
    add_fieldsets = ((None, {"fields": ("user", "name", "scopes", "expires_in_days")}),)

    list_display = (
        "name",
        "user",
        "display_prefix",
        "permissions",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    )
    list_filter = ("revoked_at", "expires_at")
    search_fields = ("name", "prefix", "user__email")
    ordering = ("-created_at",)
    fields = ("name", "user", "display_prefix", "permissions", "created_at", "expires_at", "last_used_at", "revoked_at")
    readonly_fields = fields
    actions = ("revoke",)

    @admin.display(description=_("prefix"))
    def display_prefix(self, obj):
        return f"{obj.display_prefix}…"

    @admin.display(description=_("permissions"))
    def permissions(self, obj):
        """What the key may open, in the words of the Account page («Businesses · read»), never the raw scopes."""
        return ", ".join(str(API_KEY_SCOPES.get(scope, scope)) for scope in obj.scopes)

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
        issued = api_keys.issue_api_key(
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
        count = api_keys.revoke_api_keys(queryset, by=request.user)
        self.message_user(
            request,
            gettext("Keys revoked: %(count)s.") % {"count": count},
            messages.SUCCESS,
        )
