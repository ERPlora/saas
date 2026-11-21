"""«Model that answers»: the one policy on one page (its list opens it), saved with ``assistant.policy.update``;
nobody adds nor deletes it. «Try a model» opens from it, and its run is ``model_tries``."""

from asgiref.sync import sync_to_async
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext as _
from live.errors import OperationError

from assistant import queries, services
from assistant.admin.model_tries import (
    TRY_PERMISSIONS,
    TRY_PROMPT_MAX,
    event_stream,
    prepare_try,
    refused_try,
    too_many_tries,
    try_events,
)
from assistant.admin.staff import refusals, staff_context, staff_gate
from assistant.models import AIRoutingPolicy
from assistant.schemas import NoInput, PolicyIn


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
                services.model_choice.policy_update(
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
        shown = queries.routing_policy.policy_show(ctx, NoInput())
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
            "choices": [{"id": model.pk, "label": queries.routing_policy.model_label(model)} for model in queries.routing_policy.choosable_models()],
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
