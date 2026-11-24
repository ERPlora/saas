"""The payer of a business: where it is, its VAT number and whether VIES proved it."""

import pytest

from billing.payer import Payer


def test_nobody_on_file_is_nowhere_without_a_number():
    nobody = Payer()

    assert (nobody.country, nobody.postal_code, nobody.tax_id, nobody.tax_id_type) == ("", "", "", "")
    assert nobody.has_location is False
    assert nobody.has_eu_vat_number is False


@pytest.mark.parametrize(
    "country, postal_code, known",
    [("ES", "28001", True), ("ES", "3500", False), ("ES", "", False), ("DE", "10115", True), ("", "28001", False)],
)
def test_its_location_is_a_country_and_a_postal_code_of_its_shape(country, postal_code, known):
    assert Payer(country, postal_code).has_location is known


@pytest.mark.parametrize(
    "tax_id, tax_id_type, european",
    [("FR12345678901", "eu_vat", True), ("GB123456789", "gb_vat", False), ("FR12345678901", "", False), ("", "eu_vat", False)],
)
def test_its_vat_number_is_european_by_its_type(tax_id, tax_id_type, european):
    assert Payer("FR", "75001", tax_id, tax_id_type).has_eu_vat_number is european


def test_a_number_is_not_proved_until_a_door_says_so():
    payer = Payer("FR", "75001", "FR12345678901", "eu_vat")

    assert payer.tax_id_verified is False
    assert payer.cleared(True) == Payer("FR", "75001", "FR12345678901", "eu_vat", tax_id_verified=True)
    assert payer.cleared(False) == payer
