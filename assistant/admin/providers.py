"""«AI providers»: each provider with its models inline and the variable of the environment its key is read from.
The key lives in the environment only: the page and the list say whether that variable holds one, never any part
of it, and nothing here types, changes nor rotates a key.

«Choose models from the provider»: an asynchronous page (the call to the provider never holds a thread other
requests need) that lists the provider's chat models with ``assistant.provider.connection`` and its client, and keeps
the ticked ones with ``assistant.model.select``. «AI models» lists them all, to correct their prices."""

import uuid

from asgiref.sync import sync_to_async
from django.contrib import admin, messages
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.errors import NotFound, OperationError

from assistant import queries, services
from assistant.admin.staff import refusals, staff_context, staff_gate
from assistant.models import AIModel, AIProvider
from assistant.providers.base import ProviderError
from assistant.providers.factory import get_provider
from assistant.schemas import ListedModel, ModelSelectIn, ProviderRef

#: What choosing a provider's models needs: seeing the provider, adding models and deleting them.
CHOOSE_PERMISSIONS = ("assistant.view_aiprovider", "assistant.add_aimodel", "assistant.delete_aimodel")


class ModelInline(admin.TabularInline):
    model = AIModel
    extra = 0
    fields = (
        "is_available",
        "model_id",
        "display_name",
        "context_window",
        "price_input_per_1m",
        "price_output_per_1m",
        "supports_tools",
        "supports_vision",
    )
    ordering = ("-is_available", "model_id")
    show_change_link = True


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ("display_name", "model_id", "provider", "is_available", "price_input_per_1m", "price_output_per_1m", "context_window")
    list_filter = ("is_available", "provider")
    search_fields = ("model_id", "display_name", "provider__name", "provider__slug")
    list_select_related = ("provider",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    inlines = [ModelInline]
    change_form_template = "admin/assistant/aiprovider/change_form.html"
    list_display = ("name", "slug", "kind", "is_enabled", "key_variable", "key_state")
    list_filter = ("kind", "is_enabled")
    search_fields = ("slug", "name")
    readonly_fields = ("key_state", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "slug", "kind", "is_enabled")}),
        (gettext_lazy("Connection"), {"fields": ("base_url", "key_variable", "key_state")}),
        (gettext_lazy("Notes"), {"fields": ("notes", "created_at", "updated_at")}),
    )

    @admin.display(description=gettext_lazy("key"))
    def key_state(self, provider: AIProvider) -> str:
        """Whether its variable holds a key, never any part of it."""
        return _("In the environment") if provider.has_key else _("No key")

    # --- Choose the provider's models ---------------------------------------------------------------------

    def get_urls(self):
        return [
            path("<path:object_id>/models/", self.models_view, name="assistant_aiprovider_models"),
            *super().get_urls(),
        ]

    async def models_view(self, request, object_id):  # noqa: C901
        refused = await staff_gate(self.admin_site, request, CHOOSE_PERMISSIONS)
        if refused is not None:
            return refused
        try:
            object_id = uuid.UUID(str(object_id))
        except ValueError:
            raise Http404 from None
        ctx = await sync_to_async(staff_context)(request)
        if request.method == "POST":
            return await sync_to_async(self._save_choice)(request, ctx, object_id)
        provider, rows, error = None, [], None
        try:
            connection = await sync_to_async(queries.provider_keys.provider_connection)(ctx, ProviderRef(id=object_id))
        except NotFound:
            raise Http404 from None
        except OperationError as problem:
            error = problem.message
            provider = await sync_to_async(lambda: AIProvider.objects.filter(pk=object_id).first())()
        else:
            provider = connection
        if error is None:
            try:
                client = get_provider(
                    kind=connection.kind, api_key=connection.api_key.get_secret_value(), base_url=connection.base_url
                )
                listed = await client.list_models()
            except ProviderError as problem:
                error = _("The provider did not give its models: %(reason)s") % {"reason": problem.message}
            else:
                existing = set(connection.existing)
                rows = [{"model": model, "checked": model.model_id in existing} for model in listed]
                if not rows:
                    error = _("The provider listed no chat models.")
        if provider is None:
            raise Http404
        return await sync_to_async(self._render_choice)(request, object_id, provider, rows, error)

    def _render_choice(self, request, object_id, provider, rows, error):
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Choose models from the provider"),
            "provider_name": provider.name if hasattr(provider, "name") else str(provider),
            "change_url": reverse("admin:assistant_aiprovider_change", args=[object_id]),
            "rows": rows,
            "error": error,
        }
        return TemplateResponse(request, "admin/assistant/aiprovider/models.html", context).render()

    def _save_choice(self, request, ctx, object_id):
        listed = []
        for model_id in request.POST.getlist("listed"):
            try:
                context_window = max(int(request.POST.get(f"context:{model_id}") or 0), 0)
            except ValueError:
                context_window = 0
            listed.append(
                ListedModel(
                    model_id=model_id[:128],
                    display_name=(request.POST.get(f"name:{model_id}") or model_id)[:128],
                    context_window=context_window,
                )
            )
        change_url = reverse("admin:assistant_aiprovider_change", args=[object_id])
        try:
            out = services.model_choice.model_select(
                ctx, ModelSelectIn(provider=object_id, listed=listed, selected=request.POST.getlist("models"))
            )
        except NotFound:
            raise Http404 from None
        except OperationError as refused:
            for message in refusals(refused):
                messages.error(request, message)
            return HttpResponseRedirect(change_url)
        name = AIProvider.objects.filter(pk=object_id).values_list("name", flat=True).first() or ""
        messages.success(
            request,
            _("%(provider)s: %(created)d new, %(kept)d kept, %(deleted)d removed, %(protected)d in use by the policy.")
            % {"provider": name, **out.model_dump()},
        )
        return HttpResponseRedirect(change_url)
