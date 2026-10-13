"""Who pays for a business: ``hubs.billing_profile.{get,update}`` (PLAN-SAAS §3.1, the two identities).

Ported from ERPlora/saas ``hubs/main/tests/test_billing_profile.py`` and ``test_billing_profile_model.py``
(origin/develop), the part that is not Stripe (the customer and the checkout are lot L2): the owner
reads and edits the payer; «use the business's data» copies what the SaaS knows of the business (its
name and country), a copy and not a sync; the tax ID is checked for its form only (VIES is lot L2-A).
Only the owner: billing is the owner's (round 17 §2.7).
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
    "country, tax_id",
    [("ES", "123"), ("ES", "B1234567890123"), ("PT", "PT12"), ("ES", "B12345678!")],
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
