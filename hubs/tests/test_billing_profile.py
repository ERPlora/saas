"""Who pays for a business: ``hubs.billing_profile.{get,update}``, apart from the business's own fiscal identity.

The owner reads and edits the payer; «use the business's data» copies what the SaaS knows of the business (its
name and country), a copy and not a sync. Only the owner, whose billing it is.

For now ERPlora invoices payers in Spain only: another country is refused under its field before anything is
saved or asked to VIES. The tax ID goes through billing's VAT door (``billing.services.validate_vat_for_profile``,
whose foreign shapes and VIES verdicts ``billing/tests/test_services.py`` holds): it is written as ERPlora invoices
it (``b-12.345.678`` is ``B12345678``) and a malformed one is the field's 422. A Spanish postal code has five
digits («3500» is not Las Palmas): its province decides the tax.
"""

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

from hubs import services
from hubs.queries import payers
from hubs.models import BillingProfile, Hub
from hubs.schemas import BillingProfileGetIn, BillingProfileIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


def read(user, hub):
    return payers.billing_profile_get(
        ctx_for(user), BillingProfileGetIn(hub_id=hub.id)
    ).model_dump()


def update(user, hub, **fields):
    return services.billing_profile_update(
        ctx_for(user), BillingProfileIn(hub_id=hub.id, **fields)
    ).model_dump()


def test_the_sign_up_leaves_a_payer_to_fill_in(business, owner):
    assert read(owner, business) == {
        "hub_id": business.id,
        "billing_name": "",
        "tax_id": "",
        "billing_address": "",
        "billing_city": "",
        "billing_postal_code": "",
        "billing_country": "ES",
        "billing_email": "owner@example.com",
        "same_as_business": False,
        "paid_by_another_account": False,
    }


def test_the_owner_fills_it_in(business, owner):
    saved = update(
        owner,
        business,
        billing_name="Gestoría López SL",
        tax_id="b 1234567-8",
        billing_address="Calle Mayor 1",
        billing_city="Madrid",
        billing_postal_code="28001",
        billing_country="ES",
        billing_email="facturas@lopez.example",
    )

    assert saved["tax_id"] == "B12345678"
    assert (saved["billing_name"], saved["billing_email"]) == (
        "Gestoría López SL",
        "facturas@lopez.example",
    )
    profile = Hub.objects.get(pk=business.pk).billing_profile
    assert (profile.billing_name, profile.tax_id, profile.billing_city) == (
        "Gestoría López SL",
        "B12345678",
        "Madrid",
    )


def test_the_business_data_is_copied_not_synced(business, owner):
    saved = update(
        owner,
        business,
        billing_name="Typed by hand",
        billing_country="PT",
        same_as_business=True,
    )

    assert (
        saved["billing_name"],
        saved["billing_country"],
        saved["same_as_business"],
    ) == ("Bar Manolo", "ES", True)
    Hub.objects.filter(pk=business.pk).update(name="Bar Manolo Renamed")
    assert read(owner, business)["billing_name"] == "Bar Manolo"


@pytest.mark.parametrize(
    "country, tax_id",
    [
        ("ES", "12345678Z"),
        ("ES", "X1234567L"),
        ("ES", "ESB12345678"),
        ("", ""),
    ],
)
def test_a_tax_id_of_a_valid_form_is_accepted(business, owner, country, tax_id):
    assert (
        update(owner, business, billing_country=country, tax_id=tax_id)["tax_id"]
        == tax_id
    )


@pytest.mark.parametrize(
    "country, typed, stored",
    [
        # Typography, not identity: billing's one spelling of a tax id.
        ("ES", "B12345678!", "B12345678"),
        ("ES", "esb-12345678", "ESB12345678"),
    ],
)
def test_the_tax_id_is_written_as_erplora_invoices_it(business, owner, country, typed, stored):
    assert update(owner, business, billing_country=country, tax_id=typed)["tax_id"] == stored


@pytest.mark.parametrize(
    "country, tax_id",
    [("ES", "123"), ("ES", "B1234567890123")],
)
def test_a_tax_id_of_another_form_is_an_invalid_field(business, owner, country, tax_id):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country=country, tax_id=tax_id)

    assert set(refused.value.fields) == {"tax_id"}
    assert refused.value.message == "Check the highlighted details."


@pytest.mark.parametrize("who", ["admin", "manager", "employee"])
def test_only_the_owner_sees_or_changes_who_pays(business, team, who):
    with pytest.raises(PermissionDenied):
        read(team[who], business)
    with pytest.raises(PermissionDenied):
        update(team[who], business, billing_name="Mine")


def test_a_stranger_does_not_learn_the_business_exists(business, team):
    with pytest.raises(NotFound):
        read(team["stranger"], business)


def test_a_business_without_a_payer_gets_one_when_it_is_saved(business, owner):
    profile = Hub.objects.get(pk=business.pk).billing_profile
    Hub.objects.filter(pk=business.pk).update(billing_profile=None)
    profile.delete()

    assert read(owner, business)["billing_email"] == ""
    update(owner, business, billing_name="Manolo SL")

    assert Hub.objects.get(pk=business.pk).billing_profile.owner == owner
    assert BillingProfile.objects.count() == 1


def test_an_email_of_another_form_is_refused(business):
    with pytest.raises(Exception) as refused:
        BillingProfileIn(hub_id=business.id, billing_email="not-an-email")

    assert "billing_email" in str(refused.value)


# --- VIES and the postal code ----------------------------------------------------------------------


@pytest.fixture
def issuer(db):
    from billing.models import CompanyConfig
    from billing.tests.conftest import ISSUER

    company = CompanyConfig.objects.first() or CompanyConfig()
    for field, value in ISSUER.items():
        setattr(company, field, value)
    company.save()


def test_a_foreign_vat_number_is_never_asked_to_vies_the_country_is_refused_first(business, owner, issuer):
    from billing.models import VatCheck
    from billing.tests.vies_double import REAL_VAT, no_network

    with no_network() as network, pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

    network.assert_not_called()
    assert set(refused.value.fields) == {"billing_country"}
    assert VatCheck.objects.count() == 0


def test_a_national_number_is_not_asked_to_vies(business, owner, issuer):
    from billing.tests.vies_double import no_network

    with no_network() as network:
        update(owner, business, billing_country="ES", tax_id="ESB27593136")

    network.assert_not_called()


@pytest.mark.parametrize("postal_code", ["3500", "350011", "35A01"])
def test_a_spanish_postal_code_has_five_digits(business, owner, postal_code):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country="ES", billing_postal_code=postal_code)

    assert set(refused.value.fields) == {"billing_postal_code"}
    assert refused.value.message == "Check the highlighted details."


@pytest.mark.parametrize(
    "country, postal_code",
    [
        ("ES", "35001"),
        ("ES", " 28001 "),
        ("ES", ""),
        ("ES", "51001"),
        ("ES", "52001"),
        # Only a Spanish postal code has a shape to check: without a country yet, any is kept.
        ("", "1000-001"),
    ],
)
def test_a_postal_code_of_its_country_is_saved(business, owner, country, postal_code):
    assert update(owner, business, billing_country=country, billing_postal_code=postal_code)["billing_postal_code"] == (
        postal_code.strip()
    )


def test_the_business_country_copied_into_the_payer_also_checks_the_postal_code(business, owner):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country="PT", billing_postal_code="3500", same_as_business=True)

    assert set(refused.value.fields) == {"billing_postal_code"}


@pytest.mark.parametrize("country, postal_code", [("PT", "1000-001"), ("DE", "10115"), ("FR", "75001")])
def test_a_payer_outside_spain_is_refused_and_nothing_is_saved(business, owner, country, postal_code):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country=country, billing_postal_code=postal_code)

    assert set(refused.value.fields) == {"billing_country"}
    assert Hub.objects.get(pk=business.pk).billing_profile.billing_country == "ES"


def test_a_business_outside_spain_is_not_copied_into_the_payer(business, owner):
    """With «use the business's data» the country field is hidden, so the reason is said on top too."""
    Hub.objects.filter(pk=business.pk).update(country="PT")

    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country="ES", billing_postal_code="28001", same_as_business=True)

    assert set(refused.value.fields) == {"billing_country"}
    assert refused.value.message == refused.value.fields["billing_country"]
    assert Hub.objects.get(pk=business.pk).billing_profile.same_as_business is False


def test_a_business_in_spain_is_still_copied_into_the_payer(business, owner):
    saved = update(owner, business, billing_country="", billing_postal_code="28001", same_as_business=True)

    assert (saved["billing_country"], saved["same_as_business"]) == ("ES", True)


def test_the_assistant_is_offered_only_spain_as_the_billing_country():
    schema = BillingProfileIn.model_json_schema()["properties"]["billing_country"]
    offered = {value for option in schema["anyOf"] for value in option.get("enum", [])}

    assert offered - {""} == {"ES"}


def test_without_a_payer_country_the_tax_id_is_read_in_the_business_country(business, owner):
    """The form may leave the country for the first checkout: a number typed meanwhile is read as the
    business's country would read it (a Spanish business, a Spanish NIF)."""
    assert update(owner, business, billing_country="", tax_id="b-1234567-8")["tax_id"] == "B12345678"
