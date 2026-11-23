"""«Assistant usage records»: what each business (or demo) spent by month and model, its messages of the plan's
allowance, tokens, dictations, characters read aloud and cost. Read only for everybody: rows are written by the gateway
alone (``assistant.message.claim|release``, ``assistant.usage.record``)."""

from django.contrib import admin
from django.utils.translation import gettext, gettext_lazy

from assistant.models import AssistantUsage


class UsageKindFilter(admin.SimpleListFilter):
    """Businesses, demos or accounts (the assistant of erplora.com's own panel)."""

    title = gettext_lazy("kind")
    parameter_name = "kind"

    def lookups(self, request, model_admin):
        return [
            ("business", gettext_lazy("Businesses")),
            ("demo", gettext_lazy("Demos")),
            ("account", gettext_lazy("Accounts")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "business":
            return queryset.filter(hub__isnull=False)
        if self.value() == "demo":
            return queryset.exclude(demo="")
        if self.value() == "account":
            return queryset.filter(user__isnull=False)
        return queryset


@admin.register(AssistantUsage)
class AssistantUsageAdmin(admin.ModelAdmin):
    """What each business (or demo, or account with the panel's assistant) spent through the gateway, by month and
    model (ASSISTANT-F24): read only for everybody, so no member of the staff gives a business its allowance back by editing
    or deleting its row."""

    # What the staff look for first (the allowance spent and what it cost) before the measures, so a desk's width shows
    # them without scrolling the table.
    list_display = (
        "spender",
        "period",
        "answered_by",
        "messages",
        "cost",
        "tokens_input",
        "tokens_output",
        "tokens_embedding",
        "transcriptions",
        "speech_characters",
    )
    list_filter = (UsageKindFilter, "month", "model")
    search_fields = ("hub__name", "hub__slug", "demo", "user__email", "model")
    list_select_related = ("hub", "user")
    date_hierarchy = "month"
    fields = (
        "hub",
        "demo",
        "user",
        "month",
        "model",
        "messages",
        "tokens_input",
        "tokens_output",
        "tokens_embedding",
        "transcriptions",
        "speech_characters",
        "cost_usd",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields

    @admin.display(description=gettext_lazy("business, demo or account"), ordering="hub__name")
    def spender(self, row: AssistantUsage) -> str:
        if row.user_id is not None:
            return row.user.email
        return row.demo or f"{row.hub.name} ({row.hub.slug})"

    @admin.display(description=gettext_lazy("month"), ordering="month")
    def period(self, row: AssistantUsage) -> str:
        return row.month.strftime("%Y-%m")

    @admin.display(description=gettext_lazy("model"), ordering="model")
    def answered_by(self, row: AssistantUsage) -> str:
        return row.model or gettext("Not recorded")

    @admin.display(description=gettext_lazy("cost (USD)"), ordering="cost_usd")
    def cost(self, row: AssistantUsage) -> str:
        return format(row.cost_usd.normalize(), "f")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
