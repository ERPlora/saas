"""Django admin of the paying customers: the businesses Stripe charges today with their payer, plan, monthly amount
and the date they became customers (BILLING-F41), filtered by plan, status and country and downloaded as an Excel
of what the list shows. It is read for whoever may read the subscriptions."""

from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import translation
from django.utils.translation import gettext_lazy

from billing import queries
from billing.admin.payment_records import ReadOnlyAdmin
from billing.models import PayingCustomer
from billing.money import from_cents
from hubs.countries import PAYER_COUNTRY_NAMES
from hubs.models import Subscription


class _PayingCustomerFilter(admin.SimpleListFilter):
    """A filter offering only the values some paying customer has, each by its name."""

    field = ""
    names: dict = {}

    def lookups(self, request, model_admin):
        return [(value, self.names.get(value, value)) for value in queries.paying_customer_values(self.field)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.field: self.value()})
        return queryset


class PayingCustomerStatusFilter(_PayingCustomerFilter):
    title = gettext_lazy("status")
    parameter_name = "status"
    field = "status"
    names = dict(Subscription.Status.choices)


class PayingCustomerCountryFilter(_PayingCustomerFilter):
    title = gettext_lazy("country")
    parameter_name = "country"
    field = "hub__billing_profile__billing_country"
    names = PAYER_COUNTRY_NAMES


@admin.register(PayingCustomer)
class PayingCustomerAdmin(ReadOnlyAdmin):
    """Read only, for whoever may read the subscriptions; the rows and what they show come from
    ``queries.paying_customers``."""

    list_display = ("business", "payer", "country", "customer_kind", "plan_name", "interval", "monthly",
                    "customer_since", "status")
    list_display_links = None
    list_filter = (("plan", admin.RelatedOnlyFieldListFilter), PayingCustomerStatusFilter, PayingCustomerCountryFilter)
    search_fields = ("hub__name", "hub__slug", "hub__billing_profile__billing_name", "hub__billing_profile__tax_id")
    actions = None

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("hubs.view_subscription")

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def get_queryset(self, request):
        return queries.paying_customers()

    def get_urls(self):
        own = [path("excel/", self.admin_site.admin_view(self.excel_view), name="billing_payingcustomer_excel")]
        return own + super().get_urls()

    @admin.display(description=gettext_lazy("Business"), ordering="hub__name")
    def business(self, obj):
        return obj.hub.name

    @admin.display(description=gettext_lazy("Payer"))
    def payer(self, obj):
        return queries.paying_customer_payer(obj)

    @admin.display(description=gettext_lazy("Country"))
    def country(self, obj):
        code = queries.paying_customer_country(obj)
        return PAYER_COUNTRY_NAMES.get(code, code)

    @admin.display(description=gettext_lazy("Customer"))
    def customer_kind(self, obj):
        return queries.CUSTOMER_KINDS[queries.paying_customer_kind(obj)]

    @admin.display(description=gettext_lazy("Plan"), ordering="plan__display_order")
    def plan_name(self, obj):
        return obj.plan.translated("name")

    @admin.display(description=gettext_lazy("Billing frequency"), ordering="billing_interval")
    def interval(self, obj):
        return obj.get_billing_interval_display()

    @admin.display(description=gettext_lazy("Monthly tax base (€)"))
    def monthly(self, obj):
        cents = queries.monthly_cents(obj)
        return None if cents is None else from_cents(cents)

    @admin.display(description=gettext_lazy("Customer since"), ordering="customer_since")
    def customer_since(self, obj):
        return obj.customer_since

    def excel_view(self, request):
        """«Download Excel»: what the list shows with its filters and its search; a filter it does not know goes back
        to the list, which says so."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        try:
            shown = self.get_changelist_instance(request).get_queryset(request)
        except IncorrectLookupParameters:
            return redirect(f"{reverse('admin:billing_payingcustomer_changelist')}?{request.GET.urlencode()}")
        document = queries.paying_customers_csv(shown, translation.get_language())
        response = HttpResponse(document["content"], content_type=document["content_type"])
        response["Content-Disposition"] = f'attachment; filename="{document["filename"]}"'
        return response
