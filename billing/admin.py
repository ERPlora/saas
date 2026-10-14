"""Django admin of billing: the rate table, the fiscal policy, ERPlora's identity and the VIES log.

Ported from ERPlora/saas ``apps/dashboard/fiscal/admin.py`` (origin/develop), the VAT part. A new rate, a
country raising its VAT or a service with its own rate are solved here, without a deploy (saas#1063). The
two singletons open straight on their row; the VIES log is read-only, except the manual override (adding
a row by hand) and «Check now in VIES», which adds rows through the same door as the panel and spends the
same per-person budget.
"""

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from billing import queries, services
from billing.models import CompanyConfig, FiscalPolicy, TaxCategory, TaxRule, VatCheck
from billing.money import from_cents
from billing.vies import is_uk_vat_number


class SingletonAdminMixin:
    """A singleton in the admin: the changelist and ``/add/`` open the one row (``/add/`` only while there
    is none), and it is never deleted."""

    def has_add_permission(self, request):
        """Only while there is no row, and only for whoever may add it."""
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def _url(self, action, *args):
        meta = self.model._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_{action}", args=args)

    def changelist_view(self, request, extra_context=None):
        row = self.model.objects.first()
        return redirect(
            self._url("change", row.pk) if row is not None else self._url("add")
        )

    def add_view(self, request, form_url="", extra_context=None):
        row = self.model.objects.first()
        if row is not None:
            return redirect(self._url("change", row.pk))
        return super().add_view(request, form_url=form_url, extra_context=extra_context)


@admin.register(CompanyConfig)
class CompanyConfigAdmin(SingletonAdminMixin, admin.ModelAdmin):
    fieldsets = (
        (
            gettext_lazy("Legal identity"),
            {"fields": ("legal_name", "trade_name", "tax_id")},
        ),
        (
            gettext_lazy("Address"),
            {"fields": ("street", "city", "postal_code", "province", "country")},
        ),
        (gettext_lazy("VAT and currency"), {"fields": ("vat_regime", "currency")}),
        (gettext_lazy("Contact"), {"fields": ("email", "phone", "website")}),
        (
            gettext_lazy("History"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaxCategory)
class TaxCategoryAdmin(admin.ModelAdmin):
    """What ERPlora sells, in fiscal terms."""

    list_display = ("key", "name", "rule_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("key", "name", "description")
    ordering = ("key",)

    @admin.display(description=gettext_lazy("Rules"))
    def rule_count(self, obj):
        return obj.rules.count()


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    """The % by country, region and category, with validity: a change of rate is scheduled here with a
    future ``valid_from``, and older sales keep resolving the rate they had."""

    list_display = (
        "country_code",
        "region_code",
        "category",
        "rate_display",
        "rate_pct",
        "valid_from",
        "valid_to",
        "is_active",
    )
    list_filter = ("country_code", "category", "is_subject", "is_active")
    search_fields = ("country_code", "region_code", "category__key")
    list_editable = ("rate_pct", "is_active")
    list_select_related = ("category",)
    ordering = ("country_code", "region_code", "-valid_from")
    autocomplete_fields = ("category",)
    fieldsets = (
        (None, {"fields": ("category", "country_code", "region_code")}),
        (
            gettext_lazy("Rate"),
            {
                "fields": ("rate_pct", "is_subject"),
                "description": gettext_lazy(
                    "Untick «Subject to VAT» for a territory outside the scope of the tax (Canary Islands, "
                    "Ceuta, Melilla, third countries). It is not a 0 % rate: the AEAT gets it as a sale not "
                    "subject to VAT."
                ),
            },
        ),
        (gettext_lazy("Validity"), {"fields": ("valid_from", "valid_to", "is_active")}),
    )

    @admin.display(description=gettext_lazy("Applies"))
    def rate_display(self, obj):
        if not obj.is_subject:
            return _("Not subject")
        return format_html("{}%", obj.rate_pct)


@admin.register(FiscalPolicy)
class FiscalPolicyAdmin(SingletonAdminMixin, admin.ModelAdmin):
    """The issuer and the One-Stop Shop: ``oss_progress`` shows how far the threshold is, because crossing
    it unnoticed is invoicing wrong."""

    readonly_fields = ("oss_progress",)
    fieldsets = (
        (gettext_lazy("Issuer"), {"fields": ("issuer_country", "issuer_region")}),
        (
            gettext_lazy("Intra-EU B2B (ROI / VIES)"),
            {
                "fields": ("intra_eu_reverse_charge",),
                "description": gettext_lazy(
                    "While unticked, Spanish VAT is charged to EVERY customer, EU businesses included. Even "
                    "when ticked, each sale also needs a current VIES verdict on the customer's VAT number "
                    "(see «VAT checks»); otherwise VAT is charged anyway."
                ),
            },
        ),
        (
            gettext_lazy("One-Stop Shop (OSS)"),
            {
                "fields": ("oss_registered", "oss_threshold", "oss_progress"),
                "description": gettext_lazy(
                    "Below the threshold the issuer's country VAT is charged. Above it —or with the OSS "
                    "registration ticked, which binds for two years— the customer's country rate applies."
                ),
            },
        ),
        (
            gettext_lazy("Carried from the old SaaS"),
            {
                "fields": ("oss_carried_year", "oss_carried_current_cents", "oss_carried_previous_cents"),
                "description": gettext_lazy(
                    "Until the invoices live here, the cross-border B2C sales of the year come from the old "
                    "SaaS: type them for the current year and the year before. Without them the total is "
                    "unknown and the threshold could be crossed without anybody noticing."
                ),
            },
        ),
    )

    @admin.display(description=gettext_lazy("Cross-border B2C this year"))
    def oss_progress(self, obj):
        year = timezone.localdate().year
        if not queries.oss_total_is_known(obj, year):
            return _("Unknown: carry this year's amounts from the old SaaS below (threshold %(threshold)s €)") % {
                "threshold": obj.oss_threshold
            }
        total = from_cents(queries.cross_border_b2c_cents(obj, year))
        applies = (
            _("destination rate")
            if queries.uses_destination_rate(obj)
            else _("issuer rate")
        )
        return format_html("{} / {} € → {}", total, obj.oss_threshold, applies)


@admin.register(VatCheck)
class VatCheckAdmin(admin.ModelAdmin):
    """The log of VIES queries — the proof, not a boolean. Read-only: rewriting a row forges the proof that
    defends an invoice issued without VAT. The only row written by hand is the override, with its author
    and reason (contract §7)."""

    list_display = (
        "vat_number",
        "status",
        "requested_at",
        "consultation_number",
        "is_current",
        "override_by",
    )
    list_filter = ("status", "requested_at")
    search_fields = ("vat_number", "consultation_number", "returned_name")
    date_hierarchy = "requested_at"
    ordering = ("-requested_at",)
    actions = ["recheck_in_vies"]
    fields = (
        "vat_number",
        "status",
        "requested_at",
        "consultation_number",
        "returned_name",
        "returned_address",
        "override_by",
        "override_reason",
        "override_at",
    )

    @admin.display(boolean=True, description=gettext_lazy("Current"))
    def is_current(self, obj):
        return obj.is_current

    def get_readonly_fields(self, request, obj=None):
        """To add one, the number and the reason are asked; the override fills the rest."""
        if obj is None:
            return tuple(
                field
                for field in self.fields
                if field not in ("vat_number", "override_reason")
            )
        return self.fields

    def get_form(self, request, obj=None, **kwargs):
        """The reason is NOT optional: without it there is no override."""
        form = super().get_form(request, obj, **kwargs)
        if obj is None and "override_reason" in form.base_fields:
            form.base_fields["override_reason"].required = True
        return form

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        """A query is not edited: rewriting it forges the proof."""
        return False

    @admin.action(description=gettext_lazy("Check now in VIES"), permissions=["add"])
    def recheck_in_vies(self, request, queryset):
        """Ask VIES again about the selected numbers, now: each answer is a NEW row (saas#1949). The lever
        for a number the Commission could not confirm at the sale, so the override stays the exception."""
        numbers = list(
            dict.fromkeys(
                queryset.order_by("vat_number").values_list("vat_number", flat=True)
            )
        )
        for position, number in enumerate(numbers):
            if is_uk_vat_number(number):
                messages.warning(
                    request,
                    _("%(vat)s: a UK number is HMRC's, not VIES': nothing was asked.")
                    % {"vat": number},
                )
                continue
            try:
                check = services.check_vat_number(number, spender=request.user)
            except services.VatCheckThrottled:
                messages.error(
                    request,
                    _(
                        "Too many VAT checks in the last minute. Not checked, try again shortly: %(numbers)s"
                    )
                    % {"numbers": ", ".join(numbers[position:])},
                )
                return
            except services.VatCheckNotRecorded:
                messages.error(
                    request,
                    _(
                        "%(vat)s: the answer could not be saved, so it proves nothing. Try again."
                    )
                    % {"vat": number},
                )
                continue
            if check.status == VatCheck.VERIFIED:
                messages.success(
                    request,
                    _("%(vat)s: confirmed in VIES (consultation %(consultation)s).")
                    % {
                        "vat": check.vat_number,
                        "consultation": check.consultation_number,
                    },
                )
            elif check.status == VatCheck.INVALID:
                messages.warning(
                    request,
                    _("%(vat)s: not registered in VIES. VAT is charged.")
                    % {"vat": check.vat_number},
                )
            else:
                messages.warning(
                    request,
                    _(
                        "%(vat)s: VIES could not answer. VAT is still charged; try again later."
                    )
                    % {"vat": check.vat_number},
                )

    def save_model(self, request, obj, form, change):
        """Adding by hand is exactly an override, written through the same door as the code
        (``services.record_manual_override``), so the rule —author and reason— is one."""
        check = services.record_manual_override(
            obj.vat_number,
            by=request.user.email or request.user.get_username(),
            reason=form.cleaned_data.get("override_reason", ""),
        )
        obj.pk = check.pk
        obj.refresh_from_db()
        messages.warning(
            request,
            _(
                "VAT number %(vat)s marked as valid BY HAND. Who did it and why is on the record: it is the only "
                "way to invoice without VAT when VIES does not confirm the number."
            )
            % {"vat": obj.vat_number},
        )
