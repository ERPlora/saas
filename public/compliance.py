"""``/compliance/``: where ERPlora meets each country's invoicing rules (PUBLIC-F09).

The old page read ``CountryCompliance``, rows a person flipped to «Covered» in the admin, seeded with
mandates «pending human legal review» (SAAS_PUBLIC-F62); the port left it out (spec §11.1). It comes back
as a fixed list in the code, released with the apps it describes, as Odoo lists its fiscal localizations and
Business Central its countries:

* the countries are the ones a business can be created in, ``hubs.schemas.COUNTRIES`` (one list: a market
  added there without a name here fails ``test_compliance.py``);
* for each, the fiscal systems the apps connect to TODAY: Spain's VeriFactu (the ``verifactu`` app of the
  Hub), and nothing else. The Spanish regions with their own system (the Basque Country's TicketBAI,
  Navarre) are said to be out, and no foreign mandate is named: nobody here has checked one, and a page
  that quotes a law it does not meet is the old page's mistake.
"""

from __future__ import annotations

import unicodedata

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from hubs.schemas import COUNTRIES

#: Where the customers are: first on the page, whatever the reading language.
HOME_MARKET = "ES"

#: The name of each country a business can be created in (ISO 3166-1 alpha-2).
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

#: The fiscal systems the apps connect to, by country: what each does and what it leaves out.
FISCAL_SYSTEMS = {
    "ES": (
        {
            "name": "VeriFactu",
            "does": _(
                "Every invoice and receipt is recorded in an unalterable chain, carries its QR code and is "
                "sent to the AEAT (the Spanish Tax Agency) as you sell."
            ),
            "out": _(
                "The Basque Country (TicketBAI) and Navarre have their own invoicing systems, which ERPlora "
                "does not connect to yet."
            ),
        },
    ),
}


def collation_key(name: str) -> str:
    """Alphabetical in any language: «Österreich» next to «Oman», «España» next to «Estonia»."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()


def countries() -> list[dict]:
    """Every market, the home one first and the rest by name in the active language, with its systems."""
    rows = [
        {"code": code, "name": COUNTRY_NAMES[code], "systems": FISCAL_SYSTEMS.get(code, ())}
        for code in COUNTRIES
    ]
    return sorted(
        rows, key=lambda row: (row["code"] != HOME_MARKET, collation_key(str(row["name"])))
    )


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    rows = countries()
    connected = [row for row in rows if row["systems"]]
    others = [row for row in rows if not row["systems"]]
    return render(
        request,
        "public/compliance/index.html",
        {
            "connected": connected,
            "others": others,
            "market_count": len(rows),
            "connected_count": len(connected),
            "others_count": len(others),
        },
    )
