"""The payer of a sale. No ORM here: ``billing.queries.payer_of`` reads the payer of a business."""

from __future__ import annotations

from dataclasses import dataclass, replace

from billing import vat_countries


@dataclass(frozen=True)
class Payer:
    """Where the payer of a business is and its VAT number, as every door that sells reads them."""

    country: str = ""
    postal_code: str = ""
    #: Empty when there is none, or when its country has no Stripe tax id type (a wrong type makes Stripe
    #: reject the whole number, so an unknown country's id is not guessed).
    tax_id: str = ""
    tax_id_type: str = ""
    #: VIES proved the number: said by the door that read the verdict (``cleared``), never by the profile.
    tax_id_verified: bool = False

    @property
    def has_location(self) -> bool:
        """Both halves on file, the postal code of its country's shape: a country alone prices Madrid and
        Las Palmas the same, and «3500» is not Las Palmas (``vat_countries.postal_code_is_valid``)."""
        return vat_countries.postal_code_is_valid(self.country, self.postal_code)

    @property
    def has_eu_vat_number(self) -> bool:
        return self.tax_id_type == "eu_vat" and bool(self.tax_id)

    def cleared(self, verified: bool) -> Payer:
        """The same payer with what VIES says of its number."""
        return replace(self, tax_id_verified=verified)
