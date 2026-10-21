"""WHATSAPP-G04, WHATSAPP-G09 · What erplora.com keeps of a business's WhatsApp, and what it never keeps in clear.

Ported from the old ``WhatsAppPhoneMapping`` (``../ERPlora/saas`` ``apps/whatsapp_inbox/models.py``): one row
per number, its owner business, Meta's ids and the business token and PIN encrypted (saas#1906: nobody reads
them in clear, not even in the database).
"""

import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from whatsapp.models import Delivery, PhoneNumber, Send, Template, Usage


def number(hub, **fields) -> PhoneNumber:
    defaults = {
        "phone_number_id": "106540352242922",
        "display_phone": "+34 910 00 00 00",
        "waba_id": "102290129340398",
        "access_token": "EAAG-business-token",
        "registration_pin": "123456",
    }
    return PhoneNumber.objects.create(hub=hub, **{**defaults, **fields})


def raw_column(row, column: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {row._meta.db_table} WHERE id = %s", [row.pk])
        return cursor.fetchone()[0]


@pytest.mark.django_db
class TestPhoneNumber:
    def test_the_token_and_the_pin_never_reach_the_database_in_clear(self, whatsapp_on, business):
        row = number(business)

        stored_token = raw_column(row, "access_token")
        stored_pin = raw_column(row, "registration_pin")
        assert "EAAG" not in stored_token and stored_token.startswith("gAAAA")
        assert "123456" not in stored_pin

        fresh = PhoneNumber.objects.get(pk=row.pk)
        assert (fresh.access_token, fresh.registration_pin) == ("EAAG-business-token", "123456")

    def test_its_key_is_a_uuid7(self, whatsapp_on, business):
        assert number(business).pk.version == 7

    def test_a_number_has_one_owner_in_the_whole_platform(self, whatsapp_on, business, other_business):
        number(business)
        with pytest.raises(IntegrityError), transaction.atomic():
            number(other_business, is_active=False)

    def test_a_business_has_one_active_number(self, whatsapp_on, business):
        number(business)
        number(business, phone_number_id="2", is_active=False)

        with pytest.raises(IntegrityError), transaction.atomic():
            number(business, phone_number_id="3")

    def test_it_prints_without_its_secrets(self, whatsapp_on, business):
        text = str(number(business))

        assert "EAAG" not in text and "123456" not in text


@pytest.mark.django_db
def test_a_template_is_unique_per_business_name_and_language(whatsapp_on, business):
    Template.objects.create(hub=business, name="recordatorio", language="es")
    Template.objects.create(hub=business, name="recordatorio", language="en")

    with pytest.raises(IntegrityError), transaction.atomic():
        Template.objects.create(hub=business, name="recordatorio", language="es")


@pytest.mark.django_db
def test_a_send_key_is_unique_per_business(whatsapp_on, business, other_business):
    key = str(uuid.uuid7())
    Send.objects.create(hub=business, idempotency_key=key, month="2026-10")
    # The same key of another business is another message.
    Send.objects.create(hub=other_business, idempotency_key=key, month="2026-10")

    with pytest.raises(IntegrityError), transaction.atomic():
        Send.objects.create(hub=business, idempotency_key=key, month="2026-10")


@pytest.mark.django_db
def test_one_counter_per_business_and_month(whatsapp_on, business):
    Usage.objects.create(hub=business, month="2026-10")

    with pytest.raises(IntegrityError), transaction.atomic():
        Usage.objects.create(hub=business, month="2026-10")


@pytest.mark.django_db
def test_a_message_is_parked_once_per_business(whatsapp_on, business):
    Delivery.objects.create(hub=business, kind=Delivery.Kind.MESSAGE, wa_message_id="wamid.A")
    # Its status is another delivery.
    Delivery.objects.create(hub=business, kind=Delivery.Kind.STATUS, wa_message_id="wamid.A")

    with pytest.raises(IntegrityError), transaction.atomic():
        Delivery.objects.create(hub=business, kind=Delivery.Kind.MESSAGE, wa_message_id="wamid.A")
