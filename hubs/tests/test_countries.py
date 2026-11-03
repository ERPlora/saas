"""HUBS-F01, HUBS-F15, ASSISTANT-F25 and PUBLIC-F09 · A country is said by its name, never its code (saas#217).

The card «Run this action?» says a value of a closed list by the label its app's models give it
(``live.assistant.choice_label``), one way for every app: the country of a business and of its payer are named by the
``choices`` of their fields (``hubs.countries``), in the language of the person who reads the card; ``/compliance/``
reads the same names.
"""

import gettext

import pytest
from django.conf import settings
from django.utils import translation
from live.operations import get as get_operation

from base import assistant
from billing.vat import BILLING_COUNTRIES
from hubs.countries import COUNTRY_NAMES, PAYER_COUNTRY_NAMES
from hubs.models import BillingProfile, Hub
from hubs.schemas import COUNTRIES
from hubs.tests.conftest import create_business, ctx_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def account(make_user, plans):
    return make_user("owner@example.com")


def shown(account, operation: str, arguments: dict, language: str) -> dict:
    """The datum about a country on the card of ``operation``."""
    card = assistant.card(get_operation(operation), arguments, ctx_for(account, language))
    return next(one for one in card["fields"] if one["name"].endswith("country"))


@pytest.mark.parametrize(
    ("code", "language", "name"),
    [("ES", "es", "España"), ("ES", "en", "Spain"), ("DE", "es", "Alemania"), ("NL", "es", "Países Bajos")],
)
def test_the_card_of_a_new_business_names_its_country(account, code, language, name):
    datum = shown(account, "hubs.business.create", {"name": "Bar Lena", "country": code}, language)

    assert (datum["kind"], datum["value"]) == ("text", name)


def test_the_card_of_a_change_names_the_new_country(account):
    hub = create_business(account, name="Bar Lena")

    datum = shown(account, "hubs.business.update", {"id": str(hub.id), "country": "FR"}, "es")

    assert datum["value"] == "Francia"


def test_the_card_of_a_payer_names_its_country(account):
    hub = create_business(account, name="Bar Lena")

    datum = shown(account, "hubs.billing_profile.update", {"hub_id": str(hub.id), "billing_country": "HU"}, "es")

    assert datum["value"] == "Hungría"


def test_a_payer_without_a_country_stays_empty_on_the_card(account):
    hub = create_business(account, name="Bar Lena")

    datum = shown(account, "hubs.billing_profile.update", {"hub_id": str(hub.id), "billing_country": ""}, "es")

    assert (datum["kind"], datum["value"]) == ("empty", "")


def test_every_market_a_business_may_be_in_has_its_name():
    assert set(COUNTRY_NAMES) == COUNTRIES
    assert {code for code, _name in Hub._meta.get_field("country").flatchoices} == COUNTRIES


def test_every_country_erplora_invoices_has_its_name():
    """The UK too: no business is created there, but a payer on file may be (``billing.vat.BILLING_COUNTRIES``)."""
    choices = BillingProfile._meta.get_field("billing_country").flatchoices

    assert {code for code, _name in choices} == set(BILLING_COUNTRIES)


def test_every_country_has_its_spanish_name():
    """The catalog of ``hubs``, compiled: a ``.po`` edited without ``msgfmt`` fails too."""
    compiled = settings.BASE_DIR / "hubs" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
    with compiled.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)._catalog
    with translation.override("en"):
        names = [str(name) for name in PAYER_COUNTRY_NAMES.values()]

    assert [name for name in names if not catalog.get(name)] == []


def test_the_admin_names_a_payer_of_the_uk():
    """Its list says the country by ``choices``: a value out of them would read «-» for the staff."""
    with translation.override("es"):
        assert BillingProfile(billing_country="GB").get_billing_country_display() == "Reino Unido"
