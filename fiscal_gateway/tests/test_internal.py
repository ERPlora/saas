"""``POST /internal/verifactu/submit|query|probe``: the Hub hands the gateway an envelope to present (FISCAL-F02).

Server to server, signed as every ``/internal`` call (``accounts.signing``: v1 or v2, five minutes, the
current or the previous secret), so no CSRF token. The body is ``{"hub", "nif", "environment", "route",
"envelope", "certificate"?}``: ``route=erplora``
presents with ERPlora's seal, ``route=own`` with the customer's certificate, which comes in the call
and is never kept nor logged. The AEAT's answer goes back as it came; the refusals answer the single
envelope ``{"error": {"code", "message"}}``. Only the AEAT's preproduction is ever reached, through
``respx``.

The gateway presents for a business it knows only (``hub_unknown``), and through ERPlora's seal in
production only for the taxpayer of the business's approved authorisation (``fiscal.RepresentationGrant``).
In the AEAT's testing environment nobody is represented, so no authorisation is asked for there. The one
exception is the platform's hub
(``PLATFORM_HUB_SLUG``, no business of the SaaS): ERPlora's own records, in its own name, for the seal's
holder only; ERPlora's own NIF is that hub's alone in both environments.
"""

import logging

import pytest

from fiscal.tests.conftest import make_grant
from fiscal_gateway.tests.conftest import HUB, HUB_SLUG, PLATFORM, make_p12
from fiscal_gateway.tests.internal_calls import (
    ANSWER,
    CUSTOMER,
    CUSTOMER_SENT,
    ISSUER,
    PRE_HOLDER,
    PRE_SEAL,
    call,
    error_of,
    log_text,
    own,
    payload,
    probe_body,
)
from hubs.models import Hub

pytestmark = pytest.mark.usefixtures("_known_business", "_secrets")


# Representation: through ERPlora's seal, only for whom ERPlora may present


def customer(**changes):
    """The business ``HUB`` presenting its customer's records through ERPlora's seal."""
    return payload(
        **{"hub": HUB, "nif": CUSTOMER, "envelope": CUSTOMER_SENT, **changes}
    )


@pytest.mark.parametrize("hub", ["bar-paco", "0199e8a0-0000-7000-8000-0000000000ff"])
@pytest.mark.parametrize("route", ["erplora", "own"])
def test_a_business_the_saas_does_not_know_is_404_before_the_aeat(
    client, respx_mock, erplora_seal, own_p12, hub, route
):
    body = payload(hub=hub) if route == "erplora" else own(own_p12, hub=hub)

    response = call(client, "submit", body)

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


def test_a_purged_business_is_unknown(client, respx_mock, erplora_seal, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    response = call(client, "submit", payload(hub=HUB))

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


@pytest.mark.parametrize("door", ["submit", "query"])
def test_without_an_authorisation_erplora_does_not_present_for_a_customer(
    client, respx_mock, erplora_seal, door
):
    response = call(client, door, customer(environment="production"))

    assert error_of(response) == (409, "representation_not_approved")
    assert response.json()["error"]["message"]
    assert not respx_mock.calls


@pytest.mark.parametrize("status", ["submitted", "returned", "revoked"])
def test_an_authorisation_not_in_force_is_not_enough(
    client, respx_mock, erplora_seal, business, status
):
    make_grant(business, status=status, taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", customer(environment="production"))

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_an_approval_of_another_business_is_not_enough(
    client, respx_mock, erplora_seal
):
    other = Hub.objects.create(slug="bar-paco", name="Bar Paco", country="ES")
    make_grant(other, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", customer(environment="production"))

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_an_approval_for_another_taxpayer_is_a_nif_mismatch(
    client, respx_mock, erplora_seal, business, caplog
):
    make_grant(business, status="approved", taxpayer_tax_id="B99999999")

    with caplog.at_level(logging.DEBUG):
        response = call(client, "submit", customer(environment="production"))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls
    # Nothing of the authorisation reaches the answer nor a log.
    logged = log_text(caplog)
    assert "B99999999" not in response.content.decode()
    assert "B99999999" not in logged


@pytest.mark.parametrize("hub", [HUB_SLUG, HUB])
@pytest.mark.parametrize("door", ["submit", "query"])
def test_an_approved_authorisation_lets_erplora_present_for_its_taxpayer(
    client, respx_mock, erplora_seal, business, hub, door
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, door, customer(hub=hub, nif=CUSTOMER.lower()))

    assert response.status_code == 200
    assert route.calls.last.request.content == CUSTOMER_SENT.encode("utf-8")


def test_the_platform_hub_presents_erploras_own_records_without_an_authorisation(
    client, respx_mock, erplora_seal
):
    """ERPLORA CLOUD SL files in its own name, with its own seal, from a hub that is no business of the
    SaaS."""
    assert not Hub.objects.filter(slug=PLATFORM).exists()
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, "submit", payload(nif=ISSUER.lower()))

    assert response.status_code == 200
    assert route.called


def test_the_platform_hub_presents_for_erplora_only(client, respx_mock, erplora_seal):
    response = call(client, "submit", customer(hub=PLATFORM))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_a_business_declaring_erploras_nif_needs_an_authorisation_too(
    client, respx_mock, erplora_seal
):
    """Only the platform's hub presents in ERPlora's name: a customer's hub never gets the seal for it."""
    response = call(client, "submit", payload(hub=HUB, environment="production"))

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_no_authorisation_covers_erploras_own_nif_for_a_business(
    client, respx_mock, erplora_seal, business
):
    """Even an approved one naming ERPlora as the taxpayer: in production too, ERPlora's own NIF is the platform's
    hub's alone."""
    make_grant(business, status="approved", taxpayer_tax_id=ISSUER)

    response = call(client, "submit", payload(hub=HUB, environment="production"))

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_a_business_declaring_erploras_nif_with_an_authorisation_of_its_own_is_a_mismatch(
    client, respx_mock, erplora_seal, business
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", payload(hub=HUB_SLUG, environment="production"))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_the_platform_hub_is_the_configured_one(
    client, settings, respx_mock, erplora_seal
):
    settings.PLATFORM_HUB_SLUG = "hubs"
    respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    assert error_of(call(client, "submit", payload())) == (404, "hub_unknown")
    assert call(client, "submit", payload(hub="hubs")).status_code == 200


def test_the_platform_hub_has_no_exception_with_a_certificate_of_its_own(
    client, respx_mock, own_p12
):
    response = call(client, "submit", own(own_p12, hub=PLATFORM))

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


def test_the_own_route_needs_no_authorisation(client, respx_mock):
    p12 = make_p12(org_id=f"VATES-{CUSTOMER}", serial="IDCES-12345678Z")
    respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(p12, nif=CUSTOMER, envelope=CUSTOMER_SENT))

    assert response.status_code == 200


def test_probe_through_erplora_without_an_authorisation_is_not_ready(
    client, respx_mock, erplora_seal
):
    response = call(client, "probe", probe_body(customer(environment="production")))

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "authorisation" in response.json()["detail"]
    assert not respx_mock.calls


def test_probe_through_erplora_with_an_approved_authorisation_is_ready(
    client, erplora_seal, business
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "probe", probe_body(customer(environment="production")))

    assert response.json()["ready"] is True


# In the AEAT's testing environment nobody is represented: no authorisation is asked for there


@pytest.mark.parametrize("door", ["submit", "query"])
def test_in_testing_erplora_presents_for_a_customer_without_an_authorisation(
    client, respx_mock, erplora_seal, door
):
    """FISCAL-F02: a new business tries VeriFactu before its Anexo I is signed and approved, and its records reach
    the AEAT's testing environment through ERPlora's seal, as its Hub sends them."""
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, door, customer())

    assert response.status_code == 200
    assert route.calls.last.request.content == CUSTOMER_SENT.encode("utf-8")


@pytest.mark.parametrize(
    ("status", "taxpayer"),
    [
        ("submitted", CUSTOMER),
        ("returned", CUSTOMER),
        ("revoked", CUSTOMER),
        ("approved", "B99999999"),
    ],
)
def test_in_testing_the_authorisation_is_not_read(
    client, respx_mock, erplora_seal, business, status, taxpayer
):
    """Under review, returned, withdrawn or for another taxpayer: none of it stops a testing presentation, as
    none of it lets a production one through."""
    make_grant(business, status=status, taxpayer_tax_id=taxpayer)
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, "submit", customer())

    assert response.status_code == 200
    assert route.called


def test_in_testing_a_business_never_presents_in_erploras_name(
    client, respx_mock, erplora_seal
):
    """ERPlora's own NIF is the platform's hub's alone in testing too: with no authorisation asked for
    there, a business declaring it would file in ERPlora's own name."""
    response = call(client, "submit", payload(hub=HUB, nif=ISSUER.lower()))

    assert error_of(response) == (409, "nif_mismatch")
    assert response.json()["error"]["message"]
    assert not respx_mock.calls


def test_probe_through_erplora_in_testing_is_ready_without_an_authorisation(
    client, respx_mock, erplora_seal
):
    response = call(client, "probe", probe_body(customer()))

    assert response.json() == {"ready": True, "detail": erplora_seal.describe()}
    assert not respx_mock.calls


def test_probe_of_a_business_declaring_erploras_nif_in_testing_is_not_ready(
    client, erplora_seal
):
    response = call(client, "probe", probe_body(payload(hub=HUB)))

    assert response.json()["ready"] is False


def test_probe_of_a_business_the_saas_does_not_know_is_not_ready(client, erplora_seal):
    response = call(client, "probe", probe_body(payload(hub="bar-paco")))

    assert response.status_code == 200
    assert response.json()["ready"] is False



# A demo (saas#306): no row in the SaaS, always in the AEAT's testing environment

#: A demo hub of the Hub's own (``demo-<8 hex>``): the SaaS keeps no row of it (``public/demo.py``).
DEMO = "demo-901113f0"


@pytest.mark.parametrize("door", ["submit", "query"])
def test_in_testing_a_demo_presents_through_erplora_without_a_row_in_the_saas(
    client, respx_mock, erplora_seal, door
):
    """FISCAL-F02, VERIFACTU-F15: a demo is pinned to the AEAT's testing environment and shows the whole cycle; the
    SaaS has no row of it, and in testing none is needed (no authorisation is read there)."""
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, door, customer(hub=DEMO))

    assert response.status_code == 200
    assert route.calls.last.request.content == CUSTOMER_SENT.encode("utf-8")


def test_in_testing_a_demo_presents_with_its_own_certificate_too(
    client, respx_mock, own_p12
):
    route = respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(own_p12, hub=DEMO))

    assert response.status_code == 200
    assert route.called


@pytest.mark.parametrize("route", ["erplora", "own"])
def test_a_demo_never_presents_to_production(
    client, respx_mock, erplora_seal, own_p12, route
):
    """Production needs a business the SaaS knows (and, through ERPlora, its approved authorisation): a demo is
    none, even from the prod deployment."""
    body = (
        customer(hub=DEMO, environment="production")
        if route == "erplora"
        else own(own_p12, hub=DEMO, environment="production")
    )

    response = call(client, "submit", body)

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


def test_in_testing_a_demo_never_presents_in_erploras_name(
    client, respx_mock, erplora_seal
):
    response = call(client, "submit", payload(hub=DEMO))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_probe_of_a_demo_in_testing_is_ready(client, respx_mock, erplora_seal):
    response = call(client, "probe", probe_body(customer(hub=DEMO)))

    assert response.json() == {"ready": True, "detail": erplora_seal.describe()}
    assert not respx_mock.calls


def test_probe_of_a_demo_for_production_is_not_ready(client, erplora_seal):
    response = call(
        client, "probe", probe_body(customer(hub=DEMO, environment="production"))
    )

    assert response.json()["ready"] is False


def test_a_name_that_only_looks_like_a_demo_is_still_unknown(
    client, respx_mock, erplora_seal
):
    """Only the demos' namespace (``live.slugs.is_demo_slug``: ``demo-…``) is let through without a row."""
    response = call(client, "submit", customer(hub="demos-901113f0"))

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls
