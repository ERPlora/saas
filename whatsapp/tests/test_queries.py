"""The reads of whatsapp: which business a door names (its slug in phase 1, its UUID in phase 2)."""

import pytest

from hubs.models import Hub
from whatsapp import queries

pytestmark = pytest.mark.django_db


def test_a_business_is_named_by_its_slug_or_its_uuid(business):
    assert queries.known_hub("bar-manolo") == business
    assert queries.known_hub(str(business.id)) == business


def test_32_hex_digits_are_a_slug_not_an_id(business):
    assert queries.known_hub(business.id.hex) is None


def test_an_unknown_business_is_none(business):
    assert queries.known_hub("nobody") is None


@pytest.mark.parametrize("status", [Hub.Status.DELETING, Hub.Status.DELETED])
def test_a_business_that_left_sends_nothing(business, status):
    Hub.objects.filter(pk=business.pk).update(status=status)

    assert queries.known_hub("bar-manolo") is None


def test_a_business_being_deleted_can_still_be_forgotten(business):
    """RGPD: what the Hub asks to forget is forgotten while the business is within its retention."""
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

    assert queries.known_hub("bar-manolo", live=False) == business
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)
    assert queries.known_hub("bar-manolo", live=False) is None


# --- WHATSAPP-G03, WHATSAPP-G05 · the channel the Hub learns in its snapshot (door 4) --------------------------


@pytest.fixture
def connected(whatsapp_on, business):
    from whatsapp.models import PhoneNumber

    return PhoneNumber.objects.create(
        hub=business, phone_number_id="106540352242922", display_phone="+34 910 00 00 00",
        display_name="Peluquería Ana", waba_id="W", access_token="t",
    )


def this_month():
    from django.utils import timezone

    return timezone.now().strftime("%Y-%m")


def test_a_business_without_a_number_is_not_connected_and_knows_its_allowance(whatsapp_on, business):
    business.refresh_from_db()

    assert queries.channel_block(business.id) == {
        "version": business.state_version,
        "status": "not_connected",
        "phone_number": "",
        "display_name": "",
        "monthly_limit": 30,
        "monthly_usage": 0,
        "usage_month": this_month(),
        # Without an account at Meta nothing is known of its templates: the Hub keeps its own.
        "templates": None,
    }


def test_a_connected_number_is_its_e164_number_and_name(connected, business):
    block = queries.channel_block(business.id)

    assert (block["status"], block["phone_number"], block["display_name"]) == ("connected", "+34910000000", "Peluquería Ana")
    assert block["templates"] == []


def test_a_number_to_reconnect_says_so(connected, business):
    from whatsapp.models import PhoneNumber

    PhoneNumber.objects.filter(pk=connected.pk).update(needs_reconnect=True)

    assert queries.channel_block(business.id)["status"] == "reconnect_needed"


def test_a_disconnected_number_is_not_connected(connected, business):
    from whatsapp.models import PhoneNumber

    PhoneNumber.objects.filter(pk=connected.pk).update(is_active=False)

    block = queries.channel_block(business.id)
    assert (block["status"], block["phone_number"], block["templates"]) == ("not_connected", "", None)


def test_the_usage_is_this_months_and_the_limit_the_plans(connected, business):
    from hubs.models import Plan, Subscription
    from whatsapp.models import Usage

    Usage.objects.create(hub=business, month="2000-01", used=99)
    Usage.objects.create(hub=business, month=this_month(), used=12)
    Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))

    block = queries.channel_block(business.id)

    assert (block["monthly_limit"], block["monthly_usage"]) == (150, 12)


def test_the_templates_are_the_mirror_in_the_hubs_shape(connected, business):
    from whatsapp.models import Template

    Template.objects.create(
        hub=business, name="recordatorio", language="es", category="UTILITY", status="APPROVED", meta_id="123",
        header_format="TEXT", header="Tu cita", body="Hola {{1}}, te esperamos el {{2}}.", body_examples=["Ana", "viernes"],
        buttons=[{"type": "QUICK_REPLY", "text": "Sí"}], variables=2,
    )
    Template.objects.create(hub=business, name="aviso", language="es", category="SOMETHING_NEW", status="REJECTED",
                            rejected_reason="INVALID_FORMAT")

    first, second = queries.channel_block(business.id)["templates"]

    assert second == {
        "name": "recordatorio", "language": "es", "category": "UTILITY", "status": "APPROVED",
        "header_format": "TEXT", "header": "Tu cita", "body": "Hola {{1}}, te esperamos el {{2}}.",
        "body_examples": ["Ana", "viernes"], "footer": "", "buttons": [{"type": "QUICK_REPLY", "text": "Sí"}],
        "variables": 2, "rejected_reason": "", "meta_id": "123",
    }
    # A category the Hub does not know would refuse the whole snapshot: it travels as one it knows.
    assert (first["name"], first["category"], first["rejected_reason"]) == ("aviso", "UTILITY", "INVALID_FORMAT")


def test_the_snapshot_carries_the_channel_at_its_version(connected, business):
    from hubs import queries as hubs_queries

    snapshot = hubs_queries.hub_snapshot(business.id)

    assert snapshot["whatsapp"] == {**queries.channel_block(business.id), "version": snapshot["version"]}
    assert snapshot["whatsapp"]["status"] == "connected"


def test_the_channel_of_business_b_says_nothing_of_a(connected, business, other_business):
    """Tenancy: B's block never carries A's number, usage or templates."""
    assert queries.channel_block(other_business.id)["status"] == "not_connected"
