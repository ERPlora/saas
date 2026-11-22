"""Where ERPlora invoices and sells: the member states and their general VAT rates, the countries a sale may
go to, Stripe's tax id type per country and the Spanish regions a postal code names."""

from __future__ import annotations

import re
from decimal import Decimal

#: General VAT rate of each EU-27 member state — the backstop, not the source (the source is ``TaxRule``).
EU_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"),
    "BE": Decimal("21"),
    "BG": Decimal("20"),
    "CY": Decimal("19"),
    "CZ": Decimal("21"),
    "DE": Decimal("19"),
    "DK": Decimal("25"),
    "EE": Decimal("24"),
    "ES": Decimal("21"),
    "FI": Decimal("25.5"),
    "FR": Decimal("20"),
    "GR": Decimal("24"),
    "HR": Decimal("25"),
    "HU": Decimal("27"),
    "IE": Decimal("23"),
    "IT": Decimal("22"),
    "LT": Decimal("21"),
    "LU": Decimal("17"),
    "LV": Decimal("21"),
    "MT": Decimal("18"),
    "NL": Decimal("21"),
    "PL": Decimal("23"),
    "PT": Decimal("23"),
    "RO": Decimal("21"),
    "SE": Decimal("25"),
    "SI": Decimal("22"),
    "SK": Decimal("23"),
}

#: The countries ERPlora invoices: the EU-27 and the UK, Spain first (where the customers are).
BILLING_COUNTRIES: tuple[str, ...] = (
    "ES",
    *sorted((set(EU_VAT_RATES) | {"GB"}) - {"ES"}),
)

#: The billing countries a NEW sale goes to: Spain only for now. Selling to another country takes its VAT
#: registrations (the One-Stop Shop, the ROI) and a till that meets its fiscal rules; the engine already prices
#: every ``BILLING_COUNTRIES``, so adding one here is what reopens it.
SOLD_TO_COUNTRIES = frozenset({"ES"})

#: The Spanish territories outside VAT, sold to businesses and professionals only: a consumer there owes IGIC or
#: IPSI on an online service, charged by a supplier registered there, which ERPlora is not.
BUSINESS_ONLY_REGIONS = frozenset({"IC", "CE", "ML"})


def sells_to(country: str) -> bool:
    return (country or "").strip().upper() in SOLD_TO_COUNTRIES

#: Stripe's tax id type per billing country. Anything not listed is skipped rather than guessed: a wrong
#: type makes Stripe reject the whole tax id. Derived from the VAT table so no member state is left out
#: (a hand list of nine dropped a verified Polish VAT id).
TAX_ID_TYPES: dict[str, str] = {**dict.fromkeys(EU_VAT_RATES, "eu_vat"), "GB": "gb_vat"}

#: The first two digits of a Spanish postal code are the province, and with it the territories outside VAT.
_SPANISH_REGION_BY_POSTAL_PREFIX = {"35": "IC", "38": "IC", "51": "CE", "52": "ML"}
_SPANISH_POSTAL_CODE = re.compile(r"^\d{5}$")


def tax_id_type_for(country: str) -> str:
    """Stripe's tax id type for a billing country, or ``""`` when there is none."""
    return TAX_ID_TYPES.get((country or "").strip().upper(), "")


def spanish_region_for_postal_code(postal_code: str) -> str | None:
    """Spanish fiscal region of a postal code: ``""`` = the mainland and the Balearic Islands, ``None`` =
    not a Spanish postal code (five digits, spaces aside). Only a real code names its province: «3500» is
    Benidorm typed without its leading 0, not Las Palmas, and guessing it would sell it at 0 %."""
    code = (postal_code or "").replace(" ", "")
    if not _SPANISH_POSTAL_CODE.match(code):
        return None
    return _SPANISH_REGION_BY_POSTAL_PREFIX.get(code[:2], "")


def postal_code_is_valid(country: str, postal_code: str) -> bool:
    """A billing location the sale can be priced with: a country and a postal code of its shape (Spain:
    five digits; elsewhere, not blank — the tax does not depend on it)."""
    country = (country or "").strip().upper()
    if len(country) != 2:
        return False
    if country == "ES":
        return spanish_region_for_postal_code(postal_code) is not None
    return bool((postal_code or "").strip())
