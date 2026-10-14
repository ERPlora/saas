"""The tax data of 2026-10-14: the EU-27 general rates in force in 2026, the Spanish territories outside the
scope of VAT, the UK as a third country since 2021-01-01, the categories of what ERPlora sells, the fiscal
policy and ERPlora's identity (Modelo 036). Only what is missing is created.

The data is COPIED here, never imported from ``billing.seed``: a migration describes a date, and must not
change meaning the day the live seed does (``manage.py seed_tax_rules`` writes today's data). The reverse
keeps the rows: by then the rates may have been edited in the admin, and reversing further (to ``zero``)
drops the tables with them.
"""

from decimal import Decimal

from django.db import migrations

EU_VAT_RATES = {
    "AT": "20",
    "BE": "21",
    "BG": "20",
    "CY": "19",
    "CZ": "21",
    "DE": "19",
    "DK": "25",
    "EE": "24",
    "ES": "21",
    "FI": "25.5",
    "FR": "20",
    "GR": "24",
    "HR": "25",
    "HU": "27",
    "IE": "23",
    "IT": "22",
    "LT": "21",
    "LU": "17",
    "LV": "21",
    "MT": "18",
    "NL": "21",
    "PL": "23",
    "PT": "23",
    "RO": "21",
    "SE": "25",
    "SI": "22",
    "SK": "23",
}
NON_VAT_TERRITORIES = [("ES", "IC"), ("ES", "CE"), ("ES", "ML")]
UNITED_KINGDOM = ("GB", "2021-01-01")
SEEDED_FROM = "2020-01-01"
GENERIC = "service.generic"
CATEGORIES = [
    (
        "service.generic",
        "Service (generic)",
        "Any service without a category of its own. The net of every rule.",
    ),
    (
        "service.saas_subscription",
        "SaaS subscription",
        "The plans of a business, billed through Stripe.",
    ),
    (
        "service.software_license",
        "Software licence",
        "The paid modules, one-off or by subscription.",
    ),
    ("service.training", "Training", "Training and onboarding invoiced apart."),
    ("service.support", "Support", "Support and maintenance under contract."),
    (
        "product.hardware",
        "Hardware",
        "Physical equipment (POS, printers, cash drawer): a supply of goods, not a service.",
    ),
]
ERPLORA = {
    "legal_name": "ERPLORA CLOUD SL",
    "trade_name": "ERPlora",
    "tax_id": "B27593136",
    "street": "Avda. de Lisboa, 17, 2º C",
    "city": "Coslada",
    "postal_code": "28822",
    "province": "Madrid",
    "country": "ES",
    "vat_regime": "general",
    "email": "billing@erplora.com",
    "website": "https://erplora.com",
    "currency": "EUR",
}


def _rules():
    for country, rate in EU_VAT_RATES.items():
        yield country, "", Decimal(rate), True, SEEDED_FROM
    for country, region in NON_VAT_TERRITORIES:
        yield country, region, Decimal("0.00"), False, SEEDED_FROM
    country, in_force_from = UNITED_KINGDOM
    yield country, "", Decimal("0.00"), False, in_force_from


def seed(apps, schema_editor):
    TaxCategory = apps.get_model("billing", "TaxCategory")
    TaxRule = apps.get_model("billing", "TaxRule")
    FiscalPolicy = apps.get_model("billing", "FiscalPolicy")
    CompanyConfig = apps.get_model("billing", "CompanyConfig")

    known = set(TaxCategory.objects.values_list("key", flat=True))
    for key, name, description in CATEGORIES:
        if key not in known:
            TaxCategory.objects.create(key=key, name=name, description=description)
    for country, region, rate, subject, valid_from in _rules():
        if not TaxRule.objects.filter(
            country_code=country, region_code=region, category_id=GENERIC
        ).exists():
            TaxRule.objects.create(
                category_id=GENERIC,
                country_code=country,
                region_code=region,
                rate_pct=rate,
                is_subject=subject,
                valid_from=valid_from,
                is_active=True,
            )
    if not FiscalPolicy.objects.exists():
        FiscalPolicy.objects.create()
    if not CompanyConfig.objects.exists():
        CompanyConfig.objects.create(**ERPLORA)


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
