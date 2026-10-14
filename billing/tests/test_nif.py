"""Spanish tax id shape: one spelling of a tax id, and is the taxpayer a company or a person? (saas#1725)

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_nif.py`` (origin/develop, 8 tests).
``normalise_nif`` is the single spelling of every tax id billing reads (VAT numbers included,
``billing.vies.normalise``). The Anexo I of the Convenio 17 has two opening blocks —a natural person or
«La Entidad»— and the first character of the NIF decides which one; the Hub implements
``is_legal_person_nif`` with the same letters.

Adapted: the old test that compared the helper with ``RepresentationGrant`` (not in the SaaS any more:
the representation is the Hub's) compares it with the payer's door in ``hubs``
(``hubs.services.validate_tax_id``), the other place a Spanish NIF is spelled.
"""

import pytest

from billing.nif import is_legal_person_nif, normalise_nif


class TestNormaliseNif:
    def test_it_upper_cases_and_strips_separators(self):
        assert normalise_nif(" b-1234 5678 ") == "B12345678"

    def test_an_empty_value_stays_empty(self):
        assert normalise_nif("") == ""
        assert normalise_nif(None) == ""

    def test_it_strips_dots_the_way_every_other_door_does(self):
        """``b-12.345.678`` is the taxpayer ``B12345678`` (saas#1740)."""
        assert normalise_nif("b-12.345.678") == "B12345678"
        assert normalise_nif("12.345.678-Z") == "12345678Z"

    def test_only_ascii_letters_and_digits_are_identity(self):
        """``º`` and digits of other scripts are letters and digits to ``str.isalnum``, not to the AEAT."""
        assert normalise_nif("Bº 1234567٨") == "B1234567"

    def test_it_spells_a_spanish_nif_as_the_payers_door_stores_it(self):
        """A helper that disagreed with what the payer's form stores would look up ghosts."""
        from hubs.services import validate_tax_id

        for raw in (" b-1234 5678 ", "x-1234567l", "12345678z", "b-12.345.678"):
            assert normalise_nif(raw) == validate_tax_id("ES", raw)


class TestIsLegalPersonNif:
    @pytest.mark.parametrize("letter", list("ABCDEFGHJNPQRSUVW"))
    def test_every_company_letter_is_a_legal_person(self, letter):
        assert is_legal_person_nif(f"{letter}12345678") is True

    @pytest.mark.parametrize(
        "nif", ["12345678Z", "X1234567L", "Y1234567X", "Z1234567R", "K1234567L"]
    )
    def test_a_natural_person_is_not_a_legal_person(self, nif):
        """DNI (digits), NIE (X/Y/Z) and the residual K/L/M are people, not entities."""
        assert is_legal_person_nif(nif) is False

    def test_it_normalises_before_deciding(self):
        assert is_legal_person_nif(" b-1234 5678 ") is True

    def test_an_empty_nif_is_not_a_legal_person(self):
        """Unknown is not «company»: demanding a proof of representation from a blank NIF would refuse
        the upload for a reason the customer cannot act on."""
        assert is_legal_person_nif("") is False
        assert is_legal_person_nif(None) is False
