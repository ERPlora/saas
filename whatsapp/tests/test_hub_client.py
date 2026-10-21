"""FIX-SAAS-WHATSAPP-GATEWAY-DOORS · erplora.com's calls to the Hub's doors 1 and 2 (WORKBOOK of the Hub
``whatsapp_inbox``, «Contrato con el SaaS»), against the real-HTTP double of the Hub, which verifies the signature
as the Hub does."""

import pytest

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
