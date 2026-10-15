"""Spanish tax id shape: one spelling of a tax id, and is the taxpayer a company or a person? (saas#1725)

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_nif.py`` (origin/develop, 8 tests).
``normalise_nif`` is the single spelling of every tax id billing reads (VAT numbers included,
``billing.vies.normalise``). The Anexo I of the Convenio 17 has two opening blocks —a natural person or
«La Entidad»— and the first character of the NIF decides which one; the Hub implements
``is_legal_person_nif`` with the same letters.

Adapted: the old test that compared the helper with ``RepresentationGrant`` (not in the SaaS any more:
the representation is the Hub's) compares it with the payer's door (``hubs.billing_profile.update``, which
spells a tax id with ``billing.services.vat_number_for`` since lot L2-B).
"""

import pytest

from billing.nif import is_legal_person_nif, is_spanish_tax_id, normalise_nif


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

    @pytest.mark.django_db
    def test_it_spells_a_spanish_nif_as_the_payers_door_stores_it(self):
        """A helper that disagreed with what the payer's form stores would look up ghosts."""
        from billing.services import vat_number_for

        for raw in (" b-1234 5678 ", "x-1234567l", "12345678z", "b-12.345.678"):
            assert normalise_nif(raw) == vat_number_for("ES", raw)


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


class TestIsSpanishTaxId:
    """The shape of a Spanish tax id (the taxpayer of an Anexo I, plan 2026-10-15): nine characters as the
    AEAT spells them, never the control digit (the AEAT validates it; refusing one it accepts would be ours)."""

    @pytest.mark.parametrize(
        "nif",
        [
            "12345678Z",  # DNI
            "X1234567L",  # NIE
            "Y1234567X",
            "Z1234567R",
            "K1234567L",  # the residual natural persons
            "B12345678",  # a company, control digit
            "Q2826000H",  # an entity, control letter
            " b-12.345.678 ",  # typography is not identity
        ],
    )
    def test_the_shapes_the_aeat_gives_are_spanish_tax_ids(self, nif):
        assert is_spanish_tax_id(nif) is True

    @pytest.mark.parametrize(
        "nif",
        [
            "",
            None,
            "1234567Z",  # a digit short
            "123456789",  # a DNI without its letter
            "I1234567A",  # no letter of the AEAT
            "B1234567K",  # an entity's control is a digit or A-J
            "X12345678",  # a NIE ends in a letter
            "ESB12345678",  # a VAT number, not a NIF
        ],
    )
    def test_anything_else_is_not(self, nif):
        assert is_spanish_tax_id(nif) is False

    def test_the_control_digit_is_never_checked(self):
        """``12345678A`` has the wrong letter (Z is right): the shape is all this reads."""
        assert is_spanish_tax_id("12345678A") is True
