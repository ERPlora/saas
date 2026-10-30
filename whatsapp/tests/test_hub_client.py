"""FIX-SAAS-WHATSAPP-GATEWAY-DOORS · erplora.com's calls to the Hub's doors 1 and 2 (WORKBOOK of the Hub
``whatsapp_inbox``, «Contrato con el SaaS»), against the real-HTTP double of the Hub, which verifies the signature
as the Hub does."""

import logging

import pytest

from base.tests.conftest import names_the_file
from whatsapp import hub_client


def test_door_1_posts_the_message_signed(hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"id": "x", "conversation_id": "y", "created": True})

    answer = hub_client.post_inbound({"hub": "bar-manolo", "wa_message_id": "wamid.A"})

    assert (answer.status, answer.body["created"]) == (200, True)
    (call,) = hub_double.calls_to("POST", "/internal/whatsapp/inbound")
    assert call.signed_v2 and call.body == {"hub": "bar-manolo", "wa_message_id": "wamid.A"}


def test_door_2_posts_the_status_signed(hub_double):
    hub_double.answer("POST", r"^/internal/whatsapp/status$", 200, {"updated": True, "status": "read"})

    answer = hub_client.post_status({"hub": "bar-manolo", "wa_message_id": "wamid.A", "status": "read"})

    assert answer.status == 200
    assert hub_double.calls_to("POST", "/internal/whatsapp/status")[0].signed


def test_a_refusal_is_an_answer_not_an_error(hub_double):
    """A Hub of ``main`` without the doors answers 404: the caller decides it is retried."""
    answer = hub_client.post_inbound({"hub": "bar-manolo"})

    assert answer.status == 404
    assert answer.body["error"]["code"] == "not_found"


def test_no_hub_is_unreachable(offline_hub):
    with pytest.raises(hub_client.Unreachable):
        hub_client.post_inbound({"hub": "bar-manolo"})


def test_unreadable_trusted_certificates_are_unreachable_naming_the_file(hub_double, unreadable_ca, caplog):
    """FIX-SAAS-WHATSAPP-HTTP-CALLS-CRASH-WHEN-SSL-CERT-FILE-MISSING · WHATSAPP-F07: ``httpx`` loads the server's
    trusted certificates as it makes the client, also for the Hub's ``http://``. Unreadable, the call never leaves
    and ends in its own ``Unreachable``, naming the setting and its file, in an ERROR line too (never a bare
    ``FileNotFoundError`` or ``ssl.SSLError``)."""
    with caplog.at_level(logging.ERROR), pytest.raises(hub_client.Unreachable) as raised:
        hub_client.post_status({"hub": "bar-manolo", "wa_message_id": "wamid.A", "status": "read"})

    assert names_the_file(str(raised.value), unreadable_ca)
    assert hub_double.calls_to("POST", "/internal/whatsapp/status") == []
    assert any(
        record.levelno == logging.ERROR and names_the_file(record.getMessage(), unreadable_ca)
        for record in caplog.records
    )
