"""A retired business-type code still names the row that replaced it."""

from hubs.retired_codes import current_business_type_code


def test_the_folded_peluqueria_code_maps_to_hair_salon():
    assert current_business_type_code("peluqueria") == "hair_salon"


def test_a_live_code_is_returned_unchanged():
    assert current_business_type_code("bar") == "bar"
