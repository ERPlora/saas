"""«Peluquería» is offered once, not twice (saas#2099).

Ported from ERPlora/saas ``public/catalog/tests/test_one_hair_salon.py`` (origin/develop).
Production served two business types with the same visible name, ``hair_salon`` and a legacy
``peluqueria``; the sign-up dropdown lists them by name, so a new customer could not tell which one
to pick.

Kept: the admin door refuses a second row with a visible name another row already has. Changed:
the tests of migration ``catalog.0009``, which folded the legacy row in production, are dropped
(saas-next starts from an empty database that never had it); the retired code still resolves
through ``hubs.retired_codes`` (``test_retired_codes.py``), and the ``/industries/<code>/``
redirect belongs to the public web (``public/``), which ports that page.
"""

import pytest
from django.core.exceptions import ValidationError

from hubs.models import BusinessType, Sector

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def hair_salon():
    sector = Sector.objects.create(code="personal_services", name_es="Servicios personales", name_en="Personal services")
    return BusinessType.objects.create(
        code="hair_salon", name_es="Peluquería", name_en="Hair Salon", sector=sector, display_order=4
    )


class TestTheAdminCannotTypeTheDuplicateBackIn:
    @pytest.mark.parametrize("field", ["name_es", "name_en"])
    def test_a_second_row_with_a_visible_name_already_taken_is_refused(self, hair_salon, field):
        twin = BusinessType(code="peluqueria", name_es="Barbería", name_en="Barber shop")
        setattr(twin, field, getattr(hair_salon, field))

        with pytest.raises(ValidationError) as refused:
            twin.full_clean()

        assert field in refused.value.error_dict

    def test_the_comparison_ignores_case(self, hair_salon):
        twin = BusinessType(code="peluqueria", name_es="PELUQUERÍA", name_en="Barber shop")

        with pytest.raises(ValidationError) as refused:
            twin.full_clean()

        assert "name_es" in refused.value.error_dict

    def test_saving_the_row_itself_again_is_not_a_duplicate(self, hair_salon):
        hair_salon.full_clean()

    def test_blank_names_are_not_compared(self, hair_salon):
        """An untranslated column is empty on many rows; two empties are not two «Peluquería»."""
        BusinessType.objects.create(code="barber", name_en="Barber shop", name_es="")
        other = BusinessType(code="nail_salon", name_en="Nail salon", name_es="")

        other.full_clean()

    def test_the_refusal_is_written_in_the_admins_language(self, hair_salon):
        from django.utils import translation

        twin = BusinessType(code="peluqueria", name_es="Peluquería", name_en="Barber shop")
        with pytest.raises(ValidationError) as refused:
            twin.full_clean()

        # The message is lazy: the admin renders it in the language of its request.
        with translation.override("es"):
            assert refused.value.message_dict["name_es"] == ["Ya hay otro tipo de negocio que se llama «Peluquería»."]
