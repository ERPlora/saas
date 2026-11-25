"""Today's tax data, written by ``manage.py seed_tax_rules``.

The rates are COPIED here, not read from
``billing.vat_countries.EU_VAT_RATES`` (the live backstop): a seed describes a date. The migration
``0002_seed_tax_data`` carries its own frozen copy of the data of 2026-10-14 and never imports this
module. From here on rates are edited in the admin, not in the code.

``seed_tax_data`` only CREATES what is missing and never overwrites: a rate edited in the admin, a UK rule
scheduled by hand on another date or a policy switched on by somebody is theirs. It takes the model
classes it writes (the command hands it the live ones).
"""

from decimal import Decimal

#: The general VAT rate of each EU-27 member state in force in 2026 (Estonia 24 % since Jul-2025, Romania
#: 21 % since Aug-2025, Slovakia 23 % since Jan-2025, Finland 25.5 % since Sep-2024).
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

#: The territories of a member state OUTSIDE the scope of VAT: not a 0 % rate, a sale not subject.
NON_VAT_TERRITORIES = [("ES", "IC"), ("ES", "CE"), ("ES", "ML")]

#: Post-Brexit the UK is a third country: a service supplied there from Spain is outside the scope of
#: Spanish VAT (art. 69 LIVA). In force from the day the transition period ended.
UNITED_KINGDOM = ("GB", "2021-01-01")

#: What ERPlora sells, in fiscal terms: (key, name, description).
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

#: The seeded rules are in force from before any sale of the SaaS, so none is left without a rate.
SEEDED_FROM = "2020-01-01"

#: ERPlora's identity, as the Modelo 036 filed on 24/04/2026 states it (justificante 0367501832214).
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

GENERIC = "service.generic"


def _rules():
    """(country, region, rate, subject, valid_from) of every seeded rule of the generic category."""
    for country, rate in EU_VAT_RATES.items():
        yield country, "", Decimal(rate), True, SEEDED_FROM
    for country, region in NON_VAT_TERRITORIES:
        yield country, region, Decimal("0.00"), False, SEEDED_FROM
    country, in_force_from = UNITED_KINGDOM
    yield country, "", Decimal("0.00"), False, in_force_from


def _seed_categories(TaxCategory, *, dry_run: bool) -> int:
    known = set(TaxCategory.objects.values_list("key", flat=True))
    missing = [category for category in CATEGORIES if category[0] not in known]
    if not dry_run:
        for key, name, description in missing:
            TaxCategory.objects.create(key=key, name=name, description=description)
    return len(missing)


def _seed_rules(TaxRule, *, dry_run: bool) -> int:
    created = 0
    for country, region, rate, subject, valid_from in _rules():
        # A territory that already has a generic rule (seeded or written in the admin) keeps it.
        if TaxRule.objects.filter(
            country_code=country, region_code=region, category_id=GENERIC
        ).exists():
            continue
        created += 1
        if not dry_run:
            TaxRule.objects.create(
                category_id=GENERIC,
                country_code=country,
                region_code=region,
                rate_pct=rate,
                is_subject=subject,
                valid_from=valid_from,
                is_active=True,
            )
    return created


def _seed_only_row(model, values: dict, *, dry_run: bool) -> int:
    """The one row of ``model``, with ``values``, unless it has one already."""
    if model.objects.exists():
        return 0
    if not dry_run:
        model.objects.create(**values)
    return 1


def seed_tax_data(
    *, TaxCategory, TaxRule, FiscalPolicy, CompanyConfig, dry_run: bool = False
) -> dict[str, int]:
    """Create what is missing of today's tax data; return how many rows of each kind it (would) create."""
    return {
        "categories": _seed_categories(TaxCategory, dry_run=dry_run),
        "rules": _seed_rules(TaxRule, dry_run=dry_run),
        "fiscal_policy": _seed_only_row(FiscalPolicy, {}, dry_run=dry_run),
        "company": _seed_only_row(CompanyConfig, ERPLORA, dry_run=dry_run),
    }
