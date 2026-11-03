"""The name of each country ERPlora serves, in the person's language (saas#217).

The ``choices`` of ``Hub.country`` and ``BillingProfile.billing_country``: the assistant's card says a country by them
(``live.assistant.choice_label``), as do the admin and ``/compliance/``. No ORM here, so the public web reads them
without touching a model. The screens name a country with ``Intl`` (``frontend/regions.ts``), and
``frontend/regions.test.ts`` holds both to the same names.
"""

from django.utils.translation import gettext_lazy as _

#: The markets ERPlora serves, a business may be created in (``hubs.schemas.COUNTRIES``; a market added there without a
#: name here fails ``tests/test_countries.py``).
COUNTRY_NAMES = {
    "AT": _("Austria"),
    "BE": _("Belgium"),
    "BG": _("Bulgaria"),
    "HR": _("Croatia"),
    "CY": _("Cyprus"),
    "CZ": _("Czechia"),
    "DK": _("Denmark"),
    "EE": _("Estonia"),
    "FI": _("Finland"),
    "FR": _("France"),
    "DE": _("Germany"),
    "GR": _("Greece"),
    "HU": _("Hungary"),
    "IE": _("Ireland"),
    "IT": _("Italy"),
    "LV": _("Latvia"),
    "LT": _("Lithuania"),
    "LU": _("Luxembourg"),
    "MT": _("Malta"),
    "NL": _("Netherlands"),
    "PL": _("Poland"),
    "PT": _("Portugal"),
    "RO": _("Romania"),
    "SK": _("Slovakia"),
    "SI": _("Slovenia"),
    "ES": _("Spain"),
    "SE": _("Sweden"),
}
#: The countries a payer may be in (``billing.vat.BILLING_COUNTRIES``): those, and the UK, where no business is created.
PAYER_COUNTRY_NAMES = {**COUNTRY_NAMES, "GB": _("United Kingdom")}
