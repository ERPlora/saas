"""Django admin of the AI gateway (``erplora.com/admin``): what ERPlora's staff configure so the assistant answers.

- «AI providers» (ASSISTANT-G15, G59): each provider with its keys and its models inline. A key is typed once in a
  field that never shows it again; the page and the list only say its last four characters, or why the provider has
  no usable key (old SAAS_ASSISTANT-F22 painted it whole). Keys are saved and deleted through
  ``assistant.credential.save|delete`` as the member of the staff who clicks (``staff_context``), which also checks
  the model permission.
- «Model that answers» (G27, G17, G10, G60): the one policy on one page (its list opens it), saved with
  ``assistant.policy.update``; nobody adds nor deletes it.
- «Try a model» (G61): one message to one model, its answer streamed to the page as server-sent events with its
  tokens, time and cost (``assistant.route.resolve`` with the model, then ``assistant.routing.stream``). The run is an
  asynchronous view (the provider's call never holds a thread), for the staff who may change the model that
  answers, at most ``ASSISTANT_TRY_RATELIMIT`` per person; each one is recorded with ``assistant.model.try``.
- «Choose models from the provider» (G24, G14): an asynchronous page (the call to the provider never holds a thread
  other requests need) that lists the provider's chat models with ``assistant.provider.connection`` and its client,
  and keeps the ticked ones with ``assistant.model.select``. «AI models» lists them all, to correct their prices.

Only active staff enter the admin (``accounts.admin.admin_has_permission``) and each page asks the model permission
of Django that backs it; ``support`` gets none of the assistant's (its keys are ERPlora's spend).
"""

import json
import time
import uuid

from asgiref.sync import sync_to_async
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, StreamingHttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext, Scope
from live.errors import NotFound, OperationError

from assistant import crypto, queries, routing, services
from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy, estimate_cost
from assistant.providers.base import ProviderError, ToolSpec, TurnRequest
from assistant.providers.factory import get_provider
from assistant.schemas import (
    CredentialDeleteIn,
    CredentialIn,
    ListedModel,
    ModelSelectIn,
    ModelTryIn,
    NoInput,
    PolicyIn,
    ProviderRef,
    RouteCandidate,
    RouteIn,
)

#: What choosing a provider's models needs: seeing the provider, adding models and deleting them.
CHOOSE_PERMISSIONS = ("assistant.view_aiprovider", "assistant.add_aimodel", "assistant.delete_aimodel")
#: What trying a model needs: the permission that chooses which model answers (a try spends ERPlora's key).
TRY_PERMISSIONS = ("assistant.change_airoutingpolicy",)
#: The longest message a try sends.
TRY_PROMPT_MAX = 4000


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


async def staff_gate(admin_site, request, permissions) -> HttpResponseRedirect | None:
    """For an asynchronous page of the admin: who is not in the admin goes to sign in (as ``admin_view`` does), a
    member of the staff without ``permissions`` gets a 403."""
    if not await sync_to_async(admin_site.has_permission)(request):
        return redirect_to_login(request.get_full_path(), reverse("admin:login", current_app=admin_site.name))
    allowed = await sync_to_async(lambda: all(request.user.has_perm(p) for p in permissions))()
    if not allowed:
        raise PermissionDenied
    return None


# --- Try a model --------------------------------------------------------------------------------------------


def sse(kind: str, payload: dict | None = None) -> bytes:
    """One server-sent event of a try: ``data: {"type": kind, ...payload}``."""
    return f"data: {json.dumps({'type': kind, **(payload or {})}, ensure_ascii=False)}\n\n".encode()


def event_stream(chunks) -> StreamingHttpResponse:
    response = StreamingHttpResponse(chunks, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


async def refused_try(message: str):
    yield sse("error", {"message": message})
    yield sse("done")


def parse_tools(raw: str) -> list[ToolSpec] | None:
    """The tools typed (a JSON list of ``{"name", "description", "parameters"}``, or OpenAI's ``{"function": …}``);
    ``[]`` for none, ``None`` when it is not a list of named tools."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    tools = []
    for item in data:
        spec = item.get("function", item) if isinstance(item, dict) else None
        name = spec.get("name") if isinstance(spec, dict) else None
        if not isinstance(name, str) or not name.strip():
            return None
        parameters = spec.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(parameters, dict):
            return None
        tools.append(ToolSpec(name=name.strip(), description=str(spec.get("description") or ""), parameters=parameters))
    return tools


def too_many_tries(request) -> bool:
    """Count this try of the member of the staff; whether it went past ``ASSISTANT_TRY_RATELIMIT``."""
    return is_ratelimited(
        request,
        group="assistant.try_model",
        key=lambda group, request: f"user:{request.user.pk}",
        rate=settings.ASSISTANT_TRY_RATELIMIT,
        increment=True,
    )


def prepare_try(request, ctx: OperationContext) -> tuple[RouteCandidate, TurnRequest] | str:
    """The model and the turn of a try, recorded; or the message that refuses it (in the staff's language)."""
    try:
        model = uuid.UUID(request.POST.get("model") or "")
    except ValueError:
        return _("Choose the model to try from the list.")
    prompt = (request.POST.get("prompt") or "").strip()[:TRY_PROMPT_MAX]
    if not prompt:
        return _("Write the message to send.")
    tools = parse_tools(request.POST.get("tools", ""))
    if tools is None:
        return _("The tools are not well written: write a list of tools as in the example, each with its name.")
    try:
        [candidate] = queries.route_resolve(ctx, RouteIn(model=model)).candidates
        services.model_try(ctx, ModelTryIn(model=model, prompt_chars=len(prompt), tools=len(tools)))
    except OperationError as refused:
        return refused.message
    return candidate, TurnRequest(model_id=candidate.model_id, messages=[{"role": "user", "content": prompt}], tools=tools)


async def try_events(candidate: RouteCandidate, turn: TurnRequest):
    """The events of the model's answer, then its ``metrics`` (tokens, milliseconds and USD) and ``done``."""
    started = time.monotonic()
    usage = {"input_tokens": 0, "output_tokens": 0}
    async for event in routing.stream([candidate], lambda _candidate: turn):
        if event.type == "usage":
            usage = {"input_tokens": event.payload["input_tokens"], "output_tokens": event.payload["output_tokens"]}
        yield sse(event.type, event.payload)
    cost = estimate_cost(
        candidate.price_input_per_1m, candidate.price_output_per_1m, usage["input_tokens"], usage["output_tokens"]
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    yield sse("metrics", {"latency_ms": latency_ms, **usage, "cost_usd": format(cost.normalize(), "f")})
    yield sse("done")


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ("display_name", "model_id", "provider", "is_available", "price_input_per_1m", "price_output_per_1m", "context_window")
    list_filter = ("is_available", "provider")
    search_fields = ("model_id", "display_name", "provider__name", "provider__slug")
    list_select_related = ("provider",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    inlines = [CredentialInline, ModelInline]
    change_form_template = "admin/assistant/aiprovider/change_form.html"
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

    # --- Choose the provider's models ---------------------------------------------------------------------

    def get_urls(self):
        return [
            path("<path:object_id>/models/", self.models_view, name="assistant_aiprovider_models"),
            *super().get_urls(),
        ]

    async def models_view(self, request, object_id):
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
            connection = await sync_to_async(queries.provider_connection)(ctx, ProviderRef(id=object_id))
        except NotFound:
            raise Http404 from None
        except OperationError as problem:
            error = problem.message
            provider = await sync_to_async(lambda: AIProvider.objects.filter(pk=object_id).first())()
        else:
            provider = connection
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
            out = services.model_select(
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


@admin.register(AIRoutingPolicy)
class AIRoutingPolicyAdmin(admin.ModelAdmin):
    """The one policy: its list and its row open «Model that answers»; nobody adds nor deletes it."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("policy/", wrap(self.policy_view), name="assistant_airoutingpolicy_policy"),
            path("policy/try/", wrap(self.try_view), name="assistant_airoutingpolicy_try"),
            path("policy/try/run/", self.try_run, name="assistant_airoutingpolicy_try_run"),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:assistant_airoutingpolicy_policy"))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:assistant_airoutingpolicy_policy"))

    def policy_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        ctx = staff_context(request)
        here = reverse("admin:assistant_airoutingpolicy_policy")
        if request.method == "POST":
            try:
                services.policy_update(
                    ctx,
                    PolicyIn(
                        active_model=request.POST.get("active_model") or None,
                        fallback_model=request.POST.get("fallback_model") or None,
                    ),
                )
            except OperationError as refused:
                for message in refusals(refused):
                    messages.error(request, message)
            except ValueError:
                messages.error(request, _("Choose the models from the list."))
            else:
                messages.success(request, _("The model that answers was saved."))
            return HttpResponseRedirect(here)
        shown = queries.policy_show(ctx, NoInput())
        choices = {choice.id for choice in shown.choices}
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Model that answers"),
            "shown": shown,
            "can_change": self.has_change_permission(request),
            "try_url": reverse("admin:assistant_airoutingpolicy_try"),
            "active_missing": shown.active_model is not None and shown.active_model not in choices,
            "fallback_missing": shown.fallback_model is not None and shown.fallback_model not in choices,
        }
        return TemplateResponse(request, "admin/assistant/airoutingpolicy/policy.html", context)

    def try_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Try a model"),
            "policy_url": reverse("admin:assistant_airoutingpolicy_policy"),
            "run_url": reverse("admin:assistant_airoutingpolicy_try_run"),
            "choices": [{"id": model.pk, "label": queries.model_label(model)} for model in queries.choosable_models()],
            "prompt_max": TRY_PROMPT_MAX,
        }
        return TemplateResponse(request, "admin/assistant/airoutingpolicy/try.html", context)

    async def try_run(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        refused = await staff_gate(self.admin_site, request, TRY_PERMISSIONS)
        if refused is not None:
            return refused
        if await sync_to_async(too_many_tries)(request):
            return HttpResponse(
                _("Too many tries in a minute: wait a moment and try again."),
                status=429,
                content_type="text/plain; charset=utf-8",
            )
        ctx = await sync_to_async(staff_context)(request)
        prepared = await sync_to_async(prepare_try)(request, ctx)
        if isinstance(prepared, str):
            return event_stream(refused_try(prepared))
        return event_stream(try_events(*prepared))
