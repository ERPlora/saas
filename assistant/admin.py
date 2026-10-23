"""Django admin of the AI gateway (``erplora.com/admin``): what ERPlora's staff configure so the assistant answers.

- «AI providers» (ASSISTANT-G15, G59): each provider with its keys inline. A key is typed once in a field that never
  shows it again; the page and the list only say its last four characters, or why the provider has no usable key
  (old SAAS_ASSISTANT-F22 painted it whole). Keys are saved and deleted through ``assistant.credential.save|delete``
  as the member of the staff who clicks (``staff_context``), which also checks the model permission.

Only active staff enter the admin (``accounts.admin.admin_has_permission``) and each page asks the model permission
of Django that backs it; ``support`` gets none of the assistant's (its keys are ERPlora's spend).
"""

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Prefetch
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope
from live.errors import OperationError

from assistant import crypto, services
from assistant.models import AIProvider, AIProviderCredential
from assistant.schemas import CredentialDeleteIn, CredentialIn


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


def key_state(credential: AIProviderCredential | None) -> str:
    """What the staff read of a key: its end, or why there is none to use."""
    if credential is None:
        return _("No key")
    if not credential.is_readable:
        return _("Unreadable: type the key again")
    return credential.masked_key


def refusals(error: OperationError) -> list[str]:
    return list((error.fields or {}).values()) or [error.message]


class CredentialForm(forms.ModelForm):
    """A key of the provider: its label, whether it is active and the key itself, typed once and never shown."""

    new_key = forms.CharField(
        label=gettext_lazy("Key"),
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off", "size": 40}),
        help_text=gettext_lazy("Typed once, never shown again. Empty: keep the key it has."),
    )

    class Meta:
        model = AIProviderCredential
        fields = ("label", "is_active")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        if self.instance._state.adding and not cleaned.get("new_key"):
            self.add_error("new_key", _("Type the provider's key."))
        if cleaned.get("new_key") and not crypto.configured():
            self.add_error("new_key", _("The key of the credentials is not configured: no provider key can be kept."))
        return cleaned


class CredentialInline(admin.TabularInline):
    model = AIProviderCredential
    form = CredentialForm
    extra = 0
    fields = ("label", "new_key", "key_state", "is_active", "rotated_at", "updated_by")
    readonly_fields = ("key_state", "rotated_at", "updated_by")
    verbose_name = gettext_lazy("key")
    verbose_name_plural = gettext_lazy("keys")

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        may_type = self.has_add_permission(request, obj) or self.has_change_permission(request, obj)
        return fields if may_type else [name for name in fields if name != "new_key"]

    @admin.display(description=gettext_lazy("key ends in"))
    def key_state(self, credential: AIProviderCredential) -> str:
        if credential is None or credential._state.adding:
            return "—"
        return key_state(credential)


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    inlines = [CredentialInline]
    list_display = ("name", "slug", "kind", "is_enabled", "active_key")
    list_filter = ("kind", "is_enabled")
    search_fields = ("slug", "name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "slug", "kind", "is_enabled")}),
        (gettext_lazy("Connection"), {"fields": ("base_url",)}),
        (gettext_lazy("Notes"), {"fields": ("notes", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        active = AIProviderCredential.objects.filter(is_active=True).order_by("-updated_at")
        return super().get_queryset(request).prefetch_related(
            Prefetch("credentials", queryset=active, to_attr="active_credentials")
        )

    @admin.display(description=gettext_lazy("key"))
    def active_key(self, provider: AIProvider) -> str:
        credentials = getattr(provider, "active_credentials", None)
        if credentials is None:
            credentials = list(provider.credentials.filter(is_active=True).order_by("-updated_at"))
        return key_state(credentials[0] if credentials else None)

    def save_formset(self, request, form, formset, change):
        if formset.model is not AIProviderCredential:
            return super().save_formset(request, form, formset, change)
        ctx = staff_context(request)
        formset.new_objects, formset.changed_objects, formset.deleted_objects = [], [], []
        for row in formset.deleted_forms:
            if row.instance._state.adding:
                continue
            try:
                services.credential_delete(ctx, CredentialDeleteIn(id=row.instance.pk))
                formset.deleted_objects.append(row.instance)
            except OperationError as refused:
                for message in refusals(refused):
                    messages.error(request, message)
        for row in formset.forms:
            if row in formset.deleted_forms or not row.has_changed():
                continue
            adding = row.instance._state.adding
            try:
                services.credential_save(
                    ctx,
                    CredentialIn(
                        provider=form.instance.pk,
                        id=None if adding else row.instance.pk,
                        label=row.cleaned_data.get("label") or "default",
                        is_active=bool(row.cleaned_data.get("is_active")),
                        api_key=row.cleaned_data.get("new_key") or None,
                    ),
                )
            except OperationError as refused:
                for message in refusals(refused):
                    messages.error(request, message)
                continue
            if adding:
                formset.new_objects.append(row.instance)
            else:
                formset.changed_objects.append((row.instance, row.changed_data))
