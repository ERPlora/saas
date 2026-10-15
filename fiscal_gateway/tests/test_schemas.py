"""``fiscal_gateway.schemas``: the bodies of the three doors (contract 3 of the fiscal block).

The customer's certificate travels in the body of ``route=own``: its .p12 and password stay hidden in
every ``repr``/``str`` of the schema, so no log line or traceback that prints it can leak them.
"""

import pydantic
import pytest

from fiscal_gateway.schemas import PresentIn, ProbeIn

HUB = "0199e8a0-0000-7000-8000-000000000001"


def test_a_presentation_carries_the_contracts_fields():
    body = PresentIn.model_validate(
        {
            "hub": HUB,
            "nif": "B27593136",
            "environment": "testing",
            "route": "own",
            "envelope": "<x/>",
            "certificate": {"p12_base64": "QUJD", "password": "hunter2"},
        }
    )

    assert (str(body.hub), body.environment, body.route) == (HUB, "testing", "own")
    assert body.certificate.p12_base64.get_secret_value() == "QUJD"
    assert body.certificate.password.get_secret_value() == "hunter2"


def test_the_certificate_never_shows_in_a_repr():
    body = PresentIn.model_validate(
        {
            "hub": HUB,
            "nif": "B27593136",
            "environment": "testing",
            "route": "own",
            "envelope": "<x/>",
            "certificate": {"p12_base64": "QUJDREVG", "password": "hunter2"},
        }
    )

    assert "hunter2" not in repr(body) and "hunter2" not in str(body)
    assert "QUJDREVG" not in repr(body) and "QUJDREVG" not in str(body)


@pytest.mark.parametrize(
    "change",
    [
        {"environment": "staging"},
        {"route": "somebody"},
        {"nif": ""},
        {"hub": "not-a-uuid"},
        {"envelope": ""},
    ],
)
def test_what_is_outside_the_contract_is_refused(change):
    body = {
        "hub": HUB,
        "nif": "B27593136",
        "environment": "testing",
        "route": "erplora",
        "envelope": "<x/>",
    } | change

    with pytest.raises(pydantic.ValidationError):
        PresentIn.model_validate(body)


def test_a_probe_has_no_envelope():
    probe = ProbeIn.model_validate(
        {
            "hub": HUB,
            "nif": "B27593136",
            "environment": "production",
            "route": "erplora",
        }
    )

    assert probe.certificate is None
