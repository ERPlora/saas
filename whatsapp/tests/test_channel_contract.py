"""The ``whatsapp`` key of the snapshot against the Hub's own schema of it (door 4, WHATSAPP-G03, WHATSAPP-G05).

The Hub validates that block with its ``ChannelSyncIn`` (``apps/whatsapp_inbox/schemas.py``, the version merged in
hub#127) after putting the snapshot's ``version`` in it, and a block out of contract makes it answer 422 to the
whole snapshot: the business's plan, modules and members stop reaching it too. ``HubChannelSyncIn`` below is that
schema field for field (same names, types, bounds and whitespace stripping); every block erplora.com can build,
with whatever its mirror of Meta holds, has to pass it. A change of the Hub's schema is a change of this copy.
"""

from typing import Annotated, Any, Literal

import pytest
from django.utils import timezone
from pydantic import BaseModel, Field, StringConstraints

from hubs import queries as hubs_queries
from whatsapp import queries
from whatsapp.models import PhoneNumber, Template

pytestmark = pytest.mark.django_db

# --- The Hub's schema (hub apps/whatsapp_inbox/schemas.py: E164_OR_EMPTY, _text, ChannelSyncIn, SyncTemplateIn) ---

E164_OR_EMPTY = r"^(\+[1-9]\d{6,14})?$"
TemplateCategory = Literal["UTILITY", "MARKETING", "AUTHENTICATION"]
MetaTemplateStatus = Literal["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "DELETED"]
HeaderFormat = Literal["", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"]


def _text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


class HubSyncTemplateIn(BaseModel):
    name: _text(512, 1)
    language: _text(15, 1)
    category: TemplateCategory = "UTILITY"
    status: MetaTemplateStatus = "APPROVED"
    header_format: HeaderFormat | None = None
    header: _text(200) = ""
    body: _text(4096) = ""
    body_examples: list[_text(1024)] = Field(default_factory=list, max_length=100)
    footer: _text(200) = ""
    buttons: list[dict] = Field(default_factory=list, max_length=10)
    variables: int = Field(0, ge=0, le=100)
    rejected_reason: _text(500) = ""
    meta_id: _text(64) = ""


class HubChannelSyncIn(BaseModel):
    version: int = Field(ge=0)
    status: Literal["not_connected", "connected", "reconnect_needed"]
    phone_number: Annotated[str, StringConstraints(strip_whitespace=True, pattern=E164_OR_EMPTY)] = ""
    display_name: _text(200) = ""
    monthly_limit: int = Field(0, ge=0)
    monthly_usage: int = Field(0, ge=0)
    usage_month: Annotated[str, StringConstraints(pattern=r"^(\d{4}-(0[1-9]|1[0-2]))?$")] = ""
    templates: list[HubSyncTemplateIn] | None = Field(None, max_length=1000)


def as_the_hub_reads_it(business) -> HubChannelSyncIn:
    """The snapshot's block as the Hub's ``_sync_whatsapp`` validates it: the block, with the snapshot's version."""
    snapshot = hubs_queries.hub_snapshot(business.id)
    return HubChannelSyncIn.model_validate({**snapshot["whatsapp"], "version": snapshot["version"]})


@pytest.fixture
def connected(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id="106540352242922", display_phone="+34 910 00 00 00",
        display_name="Peluquería Ana", waba_id="W", access_token="t",
    )


def test_a_business_without_a_number_passes_the_hubs_schema(whatsapp_on, business):
    block = as_the_hub_reads_it(business)

    assert (block.status, block.phone_number, block.templates) == ("not_connected", "", None)


def test_a_number_to_reconnect_passes_the_hubs_schema(connected, business):
    PhoneNumber.objects.filter(pk=connected.pk).update(needs_reconnect=True)

    assert as_the_hub_reads_it(business).status == "reconnect_needed"


def test_a_number_meta_shows_oddly_travels_empty_rather_than_refused(connected, business):
    """A number Meta shows in a way that is not E.164 (too short, a leading 0) would make the Hub refuse the
    snapshot: it travels empty, and the name still goes."""
    PhoneNumber.objects.filter(pk=connected.pk).update(display_phone="0 12", display_name="  " + "N" * 196 + "  ")

    block = as_the_hub_reads_it(business)

    assert (block.status, block.phone_number, block.display_name) == ("connected", "", "N" * 196)


def test_every_template_meta_can_hold_passes_the_hubs_schema(connected, business):
    """The mirror holds what Meta answers; whatever it is, the snapshot keeps reaching the Hub."""
    Template.objects.create(
        hub=business, name="n" * 512, language="es_ES_extra_long", category="SOMETHING_NEW", status="DELETED",
        header_format="CAROUSEL", header="h" * 5000, body="b" * 10_000, footer="f" * 5000,
        body_examples=["e" * 2000] * 150 + [7, None], buttons=[{"type": "URL"}] * 30 + ["not a button", 3],
        variables=32_000, rejected_reason="r" * 500, meta_id="9" * 64,
    )
    Template.objects.create(hub=business, name="minimal", language="en")

    block = as_the_hub_reads_it(business)

    assert sorted(template.name for template in block.templates) == ["minimal", "n" * 512]


def test_a_template_without_a_name_or_a_language_stays_out_of_the_snapshot(connected, business):
    """Meta's key of a template is its name and its language: one without either is not one the Hub can keep, and
    with it the Hub would refuse the whole snapshot (its schema asks for both)."""
    Template.objects.create(hub=business, name="   ", language="es")
    Template.objects.create(hub=business, name="sin_idioma", language="  ")
    Template.objects.create(hub=business, name="recordatorio", language="es")

    block = as_the_hub_reads_it(business)

    assert [template.name for template in block.templates] == ["recordatorio"]


def test_more_templates_than_the_hub_takes_travel_up_to_its_limit(connected, business, caplog):
    """The Hub takes up to 1000 templates in one block (Meta allows a verified account more): the first 1000 by
    name travel, and erplora.com says it left some out."""
    Template.objects.bulk_create(
        Template(hub=business, name=f"plantilla_{n:04d}", language="es") for n in range(1001)
    )

    block = as_the_hub_reads_it(business)

    assert len(block.templates) == 1000
    assert block.templates[-1].name == "plantilla_0999"
    assert "whatsapp.channel.templates_capped" in caplog.text


def test_the_month_and_the_allowance_pass_the_hubs_schema(connected, business):
    block = as_the_hub_reads_it(business)

    assert (block.usage_month, block.monthly_usage) == (timezone.now().strftime("%Y-%m"), 0)
    assert block.monthly_limit == hubs_queries.effective_plan(business.id, timezone.now()).whatsapp_messages_per_month
