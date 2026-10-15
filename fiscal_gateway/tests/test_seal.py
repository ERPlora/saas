"""``fiscal_gateway.seal``: open a .p12 (ERPlora's seal or a customer's own certificate) and pick the seal.

The holder is read from ``organizationIdentifier`` first and ``serialNumber`` after, without its ETSI
prefix (``VATES-``, ``IDCES-``). The kind decides the AEAT's door: only the eIDAS QcType eSeal makes a
``seal``; a company's representative and a natural person are told apart by the subject; anything else
is ``unknown``. A certificate that declares an EKU without clientAuth cannot open the AEAT's mTLS
connection and is refused. ``current()`` prefers the ``CURRENT`` slot and moves to ``NEXT`` when
``CURRENT`` is missing or expires within seven days.
"""

import datetime as dt
import logging

import pytest

from fiscal_gateway import seal
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from fiscal_gateway.tests.conftest import PASSWORD, b64, leaks, make_p12


def test_load_reads_the_holder_from_organization_identifier_first():
    identity = seal.load(b64(make_p12()), PASSWORD)

    assert identity.holder_tax_id == "B12345674"
    assert identity.kind == "representative"
    assert identity.expires_at > dt.datetime.now(dt.UTC) + dt.timedelta(days=360)
    assert identity.cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
    assert identity.key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")


def test_load_falls_back_to_serial_number():
    identity = seal.load(b64(make_p12(org_id=None, serial="IDCES-12345678Z")), PASSWORD)

    assert identity.holder_tax_id == "12345678Z"
    assert identity.kind == "personal"


def test_only_the_eseal_qc_type_makes_a_seal():
    identity = seal.load(
        b64(make_p12(org_id="VATES-B27593136", serial=None, eseal=True)), PASSWORD
    )

    assert (identity.holder_tax_id, identity.kind) == ("B27593136", "seal")


def test_an_entity_without_qc_type_nor_a_person_is_unknown():
    identity = seal.load(b64(make_p12(serial=None)), PASSWORD)

    assert (identity.holder_tax_id, identity.kind) == ("B12345674", "unknown")


def test_a_declared_eku_without_client_auth_is_refused():
    with pytest.raises(seal.SealInvalid):
        seal.load(b64(make_p12(client_auth=False)), PASSWORD)


def test_a_certificate_without_eku_is_accepted():
    assert (
        seal.load(b64(make_p12(client_auth=None)), PASSWORD).holder_tax_id
        == "B12345674"
    )


def test_a_wrong_password_is_refused_without_echoing_it():
    with pytest.raises(seal.SealInvalid) as refused:
        seal.load(b64(make_p12()), "nope")

    assert "nope" not in str(refused.value)
    assert refused.value.__cause__ is None and refused.value.__suppress_context__


def test_what_is_not_base64_is_refused():
    with pytest.raises(seal.SealInvalid):
        seal.load("not a p12!", PASSWORD)


def _without_key() -> bytes:
    certificate = pkcs12.load_key_and_certificates(make_p12(), PASSWORD.encode())[1]
    return pkcs12.serialize_key_and_certificates(
        b"test", None, certificate, None, serialization.NoEncryption()
    )


@pytest.mark.parametrize(
    ("p12_base64", "password"),
    [
        pytest.param("not a p12!", PASSWORD, id="not-base64"),
        pytest.param(b64(b"-----BEGIN PRIVATE KEY-----"), PASSWORD, id="not-a-p12"),
        pytest.param(b64(make_p12()), "nope", id="wrong-password"),
        pytest.param(b64(_without_key()), "", id="no-key"),
        pytest.param(b64(make_p12(client_auth=False)), PASSWORD, id="no-client-auth"),
    ],
)
def test_a_refusal_carries_no_file_key_or_openssl_text(p12_base64, password):
    with pytest.raises(seal.SealInvalid) as refused:
        seal.load(p12_base64, password)

    assert leaks(str(refused.value)) == []


def test_the_identity_never_shows_its_key_material():
    identity = seal.load(b64(make_p12()), PASSWORD)

    assert "PRIVATE KEY" not in repr(identity)
    assert "BEGIN CERTIFICATE" not in repr(identity)


def _slots(settings, *, current=None, next_=None):
    settings.FISCAL_SEAL_CURRENT_P12_BASE64 = b64(current) if current else ""
    settings.FISCAL_SEAL_CURRENT_PASSWORD = PASSWORD if current else ""
    settings.FISCAL_SEAL_NEXT_P12_BASE64 = b64(next_) if next_ else ""
    settings.FISCAL_SEAL_NEXT_PASSWORD = PASSWORD if next_ else ""


def _days_left(identity) -> int:
    return (identity.expires_at - dt.datetime.now(dt.UTC)).days


def test_current_prefers_the_current_slot(settings):
    _slots(
        settings,
        current=make_p12(days=300, eseal=True),
        next_=make_p12(days=700, eseal=True),
    )

    assert 298 <= _days_left(seal.current()) <= 300


def test_current_moves_to_next_when_current_expires_within_seven_days(settings):
    _slots(
        settings,
        current=make_p12(days=3, eseal=True),
        next_=make_p12(days=700, eseal=True),
    )

    assert _days_left(seal.current()) >= 698


def test_current_moves_to_next_when_the_current_slot_is_empty(settings):
    _slots(settings, next_=make_p12(days=700, eseal=True))

    assert _days_left(seal.current()) >= 698


def test_current_keeps_a_seal_about_to_expire_when_next_is_empty(settings):
    _slots(settings, current=make_p12(days=3, eseal=True))

    assert _days_left(seal.current()) in (2, 3)


def test_an_expired_seal_is_no_seal(settings):
    _slots(settings, current=make_p12(days=-1, eseal=True))

    assert seal.current() is None


def test_both_slots_empty_is_none(no_seal):
    assert seal.current() is None


def test_an_unreadable_slot_is_skipped_and_logged_by_name_only(settings, caplog):
    _slots(settings, current=make_p12(eseal=True), next_=make_p12(days=700, eseal=True))
    settings.FISCAL_SEAL_CURRENT_PASSWORD = "the-wrong-password"

    with caplog.at_level(logging.WARNING, logger="fiscal_gateway"):
        chosen = seal.current()

    assert _days_left(chosen) >= 698
    assert "current" in caplog.text
    assert "the-wrong-password" not in caplog.text
    assert settings.FISCAL_SEAL_CURRENT_P12_BASE64[:40] not in caplog.text
