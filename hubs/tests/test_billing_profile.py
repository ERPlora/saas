"""Who pays for a business: ``hubs.billing_profile.{get,update}`` (PLAN-SAAS §3.1, the two identities).

Ported from ERPlora/saas ``hubs/main/tests/test_billing_profile.py`` and ``test_billing_profile_model.py``
(origin/develop), the part that is not Stripe (the customer and the checkout are lot L2): the owner
reads and edits the payer; «use the business's data» copies what the SaaS knows of the business (its
name and country), a copy and not a sync. Only the owner: billing is the owner's (round 17 §2.7).

Lot L2-B wires billing's VAT door into it (``billing.services.validate_vat_for_profile``, L2-A): the tax ID
is written as ERPlora invoices it (``b-12.345.678`` is ``B12345678``, a foreign one typed bare gets its
prefix) and asked to VIES, whose verdict is logged; a malformed one is the field's 422, but a number VIES
does not confirm is kept as identification (it simply buys no reverse charge). A Spanish postal code has
five digits («3500» is not Las Palmas): its province decides the tax (saas#1972).
"""

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

from hubs import queries, services
from hubs.models import BillingProfile, Hub
from hubs.schemas import BillingProfileGetIn, BillingProfileIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


def read(user, hub):
    return queries.billing_profile_get(
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
        ("PT", "PT123456789"),
        ("FR", "FRXX123456789"),
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
        # Typography, not identity (saas#1740): billing's one spelling of a tax id.
        ("ES", "B12345678!", "B12345678"),
        # Two digits are a VAT number's shape (a Romanian CUI may be that short): VIES decides it exists.
        ("PT", "PT12", "PT12"),
        # Typed bare in another member state: the prefix VIES files it under.
        ("DE", "812871812", "DE812871812"),
    ],
)
def test_the_tax_id_is_written_as_erplora_invoices_it(business, owner, country, typed, stored):
    assert update(owner, business, billing_country=country, tax_id=typed)["tax_id"] == stored


@pytest.mark.parametrize(
    "country, tax_id",
    [("ES", "123"), ("ES", "B1234567890123"), ("PT", "XX123456789"), ("DE", "DE1")],
)
def test_a_tax_id_of_another_form_is_an_invalid_field(business, owner, country, tax_id):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country=country, tax_id=tax_id)

    assert set(refused.value.fields) == {"tax_id"}


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


# --- VIES and the postal code (lot L2-B) --------------------------------------------------------------


@pytest.fixture
def issuer(db):
    from billing.models import CompanyConfig
    from billing.tests.conftest import ISSUER

    company = CompanyConfig.objects.first() or CompanyConfig()
    for field, value in ISSUER.items():
        setattr(company, field, value)
    company.save()


def test_a_foreign_vat_number_is_asked_to_vies_and_the_answer_logged(business, owner, issuer):
    from billing.models import VatCheck
    from billing.tests.vies_double import REAL_VAT, VALID, vies_says

    with vies_says(**VALID):
        saved = update(owner, business, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

    assert saved["tax_id"] == REAL_VAT
    assert VatCheck.objects.get(vat_number=REAL_VAT).status == VatCheck.VERIFIED


def test_a_number_vies_does_not_know_is_kept_as_identification(business, owner, issuer):
    from billing.models import VatCheck
    from billing.tests.vies_double import FAKE_VAT, NOT_REGISTERED, vies_says

    with vies_says(**NOT_REGISTERED):
        saved = update(owner, business, billing_country="DE", billing_postal_code="10115", tax_id=FAKE_VAT)

    assert saved["tax_id"] == FAKE_VAT
    assert VatCheck.objects.get(vat_number=FAKE_VAT).status == VatCheck.INVALID


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


@pytest.mark.parametrize(
    "country, postal_code", [("ES", "35001"), ("ES", " 28001 "), ("ES", ""), ("PT", "1000-001"), ("DE", "10115")]
)
def test_a_postal_code_of_its_country_is_saved(business, owner, country, postal_code):
    assert update(owner, business, billing_country=country, billing_postal_code=postal_code)["billing_postal_code"] == (
        postal_code.strip()
    )


def test_the_business_country_copied_into_the_payer_also_checks_the_postal_code(business, owner):
    with pytest.raises(InvalidPayload) as refused:
        update(owner, business, billing_country="PT", billing_postal_code="3500", same_as_business=True)

    assert set(refused.value.fields) == {"billing_postal_code"}


def test_without_a_payer_country_the_tax_id_is_read_in_the_business_country(business, owner):
    """The form may leave the country for the first checkout: a number typed meanwhile is read as the
    business's country would read it (a Spanish business, a Spanish NIF)."""
    assert update(owner, business, billing_country="", tax_id="b-1234567-8")["tax_id"] == "B12345678"
