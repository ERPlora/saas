"""Today's tax data, written by ``manage.py seed_tax_rules``.

Ported from ERPlora/saas ``fiscal/migrations/0006_seed_tax_rules.py``, ``0020_seed_united_kingdom_tax_rule.py``
and ``management/commands/seed_company_036.py`` (origin/develop). The rates are COPIED here, not read from
``billing.vat.EU_VAT_RATES`` (the live backstop): a seed describes a date. The migration
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


def seed_tax_data(
    *, TaxCategory, TaxRule, FiscalPolicy, CompanyConfig, dry_run: bool = False
) -> dict[str, int]:
    """Create what is missing of today's tax data; return how many rows of each kind it (would) create."""
    created = {"categories": 0, "rules": 0, "fiscal_policy": 0, "company": 0}

    known = set(TaxCategory.objects.values_list("key", flat=True))
    for key, name, description in CATEGORIES:
        if key not in known:
            created["categories"] += 1
            if not dry_run:
                TaxCategory.objects.create(key=key, name=name, description=description)

    for country, region, rate, subject, valid_from in _rules():
        # A territory that already has a generic rule (seeded or written in the admin) keeps it.
        if TaxRule.objects.filter(
            country_code=country, region_code=region, category_id=GENERIC
        ).exists():
            continue
        created["rules"] += 1
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

    if not FiscalPolicy.objects.exists():
        created["fiscal_policy"] += 1
        if not dry_run:
            FiscalPolicy.objects.create()

    if not CompanyConfig.objects.exists():
        created["company"] += 1
        if not dry_run:
            CompanyConfig.objects.create(**ERPLORA)

    return created
