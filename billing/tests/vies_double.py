"""A double of VIES for the tests: recorded answers of the Commission's REST ``check-vat-number``.

Only the network is faked (``billing.vies.requests.post``), never a verdict: every test goes through
the code that reads the answer and decides. The bodies are the shape the REST endpoint returns when
the request identifies the requester (``requesterMemberStateCode`` + ``requesterNumber``); the
``requestIdentifier`` is the consultation number that proves the answer.
"""

from unittest.mock import Mock, patch

import requests

POST = "billing.vies.requests.post"

REAL_VAT = "DE812871812"  # Hetzner's: exists in VIES
FAKE_VAT = (
    "DE999999999"  # well formed, nonexistent: the one Stripe lets through by its format
)

#: VIES answering «valid», with the proof (recorded shape, 2026-08-25).
VALID = {
    "countryCode": "DE",
    "vatNumber": "812871812",
    "requestDate": "2026-08-25+02:00",
    "valid": True,
    "requestIdentifier": "WAPIAAAAXjHIQOZ",
    "userError": "VALID",
    "name": "Hetzner Online GmbH",
    "address": "Industriestr. 25\n91710 Gunzenhausen",
    "traderName": "---",
    "traderStreet": "---",
}
#: VIES answering «not registered».
NOT_REGISTERED = {
    "countryCode": "DE",
    "vatNumber": "999999999",
    "requestDate": "2026-08-25+02:00",
    "valid": False,
    "requestIdentifier": "WAPIAAAAXinvalid",
    "userError": "INVALID",
    "name": "---",
    "address": "---",
}
#: The member state's register is down: not «no», «could not answer».
MEMBER_STATE_DOWN = {
    "countryCode": "DE",
    "vatNumber": "812871812",
    "requestDate": "2026-08-25+02:00",
    "valid": False,
    "requestIdentifier": "",
    "userError": "MS_UNAVAILABLE",
}


def reply(status_code: int = 200, **body) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    return response


def vies_says(**body):
    """VIES answers ``body`` (a field may be overridden: ``vies_says(**VALID, name="ACME")``)."""
    status_code = body.pop("status_code", 200)
    return patch(POST, return_value=reply(status_code, **body))


def vies_answers(base: dict, **overrides):
    return vies_says(**{**base, **overrides})


def vies_is_down(error: Exception | None = None):
    return patch(POST, side_effect=error or requests.ConnectionError("VIES timed out"))


def no_network():
    """Patch the network to see that nobody asked."""
    return patch(POST)
