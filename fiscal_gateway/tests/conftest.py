"""Fixtures of the fiscal gateway's tests: throwaway certificates and the AEAT envelopes of the Hub.

``make_p12`` is the helper of the Hub's ``apps/verifactu/tests/test_certificates.py`` (plan
2026-10-15-bloque-fiscal-hub, task 1), extended with ``eseal`` (the eIDAS QcType of an entity seal)
and with ``org_id=None`` / ``serial=None`` leaving the attribute out. Every certificate is
self-signed and generated in the test: never a real one.

The XML fixtures are copied byte for byte from ``hub-next/apps/verifactu/tests/fixtures/``: an
envelope the Hub sent to the AEAT's preproduction and the AEAT's answers to a submission and to a
query.

``business`` is the business ``HUB`` (slug ``HUB_SLUG``) as the SaaS knows it: the gateway presents
for businesses it knows only.
"""

import base64
import datetime as dt
import uuid
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "secret"
#: The business the Hub presents for: its registry UUID (lowercase) and its slug.
HUB = "0199e8a0-0000-7000-8000-000000000001"
HUB_SLUG = "bar-manolo"

# qcStatements (RFC 3739, 1.3.6.1.5.5.7.1.3) holding one QCStatement: id-etsi-qcs-QcType
# (0.4.0.1862.1.6) with id-etsi-qct-eseal (0.4.0.1862.1.6.2), DER-encoded (ETSI EN 319 412-5).
QC_STATEMENTS = ObjectIdentifier("1.3.6.1.5.5.7.1.3")
QC_TYPE_ESEAL = bytes.fromhex(
    "3015" "3013" "060604008e460106" "3009" "060704008e46010602"
)


def make_p12(
    *,
    org_id: str | None = "VATES-B12345674",
    serial: str | None = "12345678Z",
    client_auth: bool | None = True,
    days: int = 365,
    eseal: bool = False,
    password: str = PASSWORD,
    key_size: int = 2048,
) -> bytes:
    """A self-signed .p12 whose subject carries ``org_id`` and ``serial`` (``None`` leaves them out).

    ``client_auth``: ``True`` declares an EKU with clientAuth, ``False`` one without it, ``None`` no
    EKU at all. ``days``: until it expires (negative = already expired). ``key_size``: of its RSA
    key (below 2048, TLS refuses it)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    attributes = [x509.NameAttribute(NameOID.COMMON_NAME, "ACME SL")]
    if org_id:
        attributes.append(x509.NameAttribute(NameOID.ORGANIZATION_IDENTIFIER, org_id))
    if serial:
        attributes.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, serial))
    name = x509.Name(attributes)
    now = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=30))
        .not_valid_after(now + dt.timedelta(days=days))
    )
    if client_auth is not None:
        usages = (
            [ExtendedKeyUsageOID.CLIENT_AUTH]
            if client_auth
            else [ExtendedKeyUsageOID.EMAIL_PROTECTION]
        )
        builder = builder.add_extension(x509.ExtendedKeyUsage(usages), critical=False)
    if eseal:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(QC_STATEMENTS, QC_TYPE_ESEAL), critical=False
        )
    cert = builder.sign(key, hashes.SHA256())
    return pkcs12.serialize_key_and_certificates(
        b"test",
        key,
        cert,
        None,
        serialization.BestAvailableEncryption(password.encode()),
    )


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def no_seal(settings):
    """Both seal slots empty, whatever the developer's .env holds."""
    settings.FISCAL_SEAL_CURRENT_P12_BASE64 = ""
    settings.FISCAL_SEAL_CURRENT_PASSWORD = ""
    settings.FISCAL_SEAL_NEXT_P12_BASE64 = ""
    settings.FISCAL_SEAL_NEXT_PASSWORD = ""
    return settings


@pytest.fixture
def business(db):
    """The business ``HUB`` (slug ``HUB_SLUG``), as the SaaS knows it."""
    from hubs.models import Hub

    return Hub.objects.create(
        id=uuid.UUID(HUB), slug=HUB_SLUG, name="Bar Manolo", country="ES"
    )
