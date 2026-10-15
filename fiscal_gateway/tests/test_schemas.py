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


@pytest.mark.parametrize("hub", ["demo", "erplora", "a", "my-hub-2", HUB])
def test_the_hub_is_its_slug_or_its_uuid(hub):
    # Phase 1: the Hub sends the slug of its host; the registry's UUID comes in phase 2.
    body = PresentIn.model_validate(
        {
            "hub": hub,
            "nif": "B27593136",
            "environment": "testing",
            "route": "erplora",
            "envelope": "<x/>",
        }
    )

    assert body.hub == hub


@pytest.mark.parametrize(
    "hub",
    ["", "Demo", "a" * 65, "x y", "-demo", "demo.", HUB.upper(), 7, None],
)
def test_a_hub_that_is_neither_a_slug_nor_a_uuid_is_refused(hub):
    with pytest.raises(pydantic.ValidationError) as refused:
        ProbeIn.model_validate(
            {
                "hub": hub,
                "nif": "B27593136",
                "environment": "testing",
                "route": "erplora",
            }
        )

    assert [error["loc"] for error in refused.value.errors()] == [("hub",)]


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
