"""The certificates the gateway presents with: ERPlora's seal and a customer's own certificate.

``load`` opens a .p12 (base64 and password) into an ``Identity``: the PEM of the certificate (with its
chain) and of the private key, which ``aeat.present`` hands to TLS, and what the gateway needs to know
about it:

- ``holder_tax_id``: ``organizationIdentifier`` first, ``serialNumber`` after, without the ETSI EN
  319 412-1 prefix (``VATES-B12345674`` → ``B12345674``, ``IDCES-12345678Z`` → ``12345678Z``);
- ``kind``, which picks the AEAT's door (``aeat.endpoint``): ``seal`` only with the eIDAS QcType eSeal
  (``0.4.0.1862.1.6.2``, ETSI EN 319 412-5) and not eSign; else ``representative`` (an entity and a
  person's DNI/NIE in the subject: a company's representative), ``personal`` (a person only) or
  ``unknown``. Concluding ``seal`` takes positive evidence: a wrong ``www10`` gets every record
  refused, so absence of evidence goes to the holder's door.

A certificate that declares an Extended Key Usage without clientAuth (nor anyExtendedKeyUsage) can
never open the AEAT's mTLS connection, so it is refused here, before anything is sent.

``current()`` is ERPlora's seal, from the two slots ``FISCAL_SEAL_{CURRENT,NEXT}_{P12_BASE64,PASSWORD}``
(``config/settings.py``; empty = an empty slot): ``CURRENT`` unless it is missing, unreadable, expired or
expires within ``ROTATION_MARGIN``, and then ``NEXT`` if it is usable; ``CURRENT`` still while it has
not expired and ``NEXT`` is not usable; ``None`` without a usable seal.

Nothing of a certificate (the .p12, its password, the PEM) reaches a message, a log or a traceback:
errors name what failed only (``from None``) and ``Identity`` keeps its key material out of ``repr``.
"""

import base64
import binascii
import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.conf import settings

logger = logging.getLogger(__name__)

Kind = Literal["seal", "representative", "personal", "unknown"]

#: ``CURRENT`` gives way to ``NEXT`` this long before it expires.
ROTATION_MARGIN = dt.timedelta(days=7)

#: The two slots of ERPlora's seal and the settings of their .p12 (base64) and password.
SLOTS = {
    "current": ("FISCAL_SEAL_CURRENT_P12_BASE64", "FISCAL_SEAL_CURRENT_PASSWORD"),
    "next": ("FISCAL_SEAL_NEXT_P12_BASE64", "FISCAL_SEAL_NEXT_PASSWORD"),
}

# eIDAS QcType eSeal and eSign (0.4.0.1862.1.6.2 and .1), DER-encoded as they appear inside the
# qcStatements extension: found by their bytes, as the gateway this one replaces did, because the
# library has no parser for qcStatements.
_QC_TYPE_ESEAL = bytes.fromhex("060704008e46010602")
_QC_TYPE_ESIGN = bytes.fromhex("060704008e46010601")
# The ETSI EN 319 412-1 semantics prefix of an identifier: type (VAT, IDC, NTR…), country, hyphen.
_ETSI_PREFIX = re.compile(r"^[A-Z]{3}[A-Z]{2}-")
# A Spanish DNI (8 digits and a letter) or NIE (X/Y/Z, 7 digits and a letter): a natural person.
_PERSON_ID = re.compile(r"^(\d{8}|[XYZ]\d{7})[A-Z]$")


class SealInvalid(Exception):
    """The .p12 cannot be used to present to the AEAT. The message names the reason only."""


@dataclass(frozen=True)
class Identity:
    """An opened certificate: what TLS needs (PEM) and what the gateway knows about it."""

    cert_pem: bytes = field(repr=False)
    key_pem: bytes = field(repr=False)
    holder_tax_id: str
    kind: Kind
    expires_at: dt.datetime

    def usable_at(self, now: dt.datetime) -> bool:
        """Whether it has not expired at ``now``."""
        return self.expires_at > now

    def describe(self) -> str:
        """``seal B27593136, expires 2027-10-15``: what it is, without any of its material."""
        return f"{self.kind} {self.holder_tax_id}, expires {self.expires_at.date().isoformat()}"


def load(p12_base64: str, password: str) -> Identity:
    """Open a .p12 given in base64 with its password; ``SealInvalid`` if it cannot present."""
    try:
        raw = base64.b64decode("".join(p12_base64.split()), validate=True)
    except binascii.Error, ValueError:
        raise SealInvalid("The certificate is not valid base64.") from None
    try:
        key, certificate, chain = pkcs12.load_key_and_certificates(
            raw, password.encode() or None
        )
    except ValueError, TypeError, UnsupportedAlgorithm:
        raise SealInvalid(
            "The certificate is not a .p12 that its password opens."
        ) from None
    if certificate is None or key is None:
        raise SealInvalid("The .p12 does not hold a certificate and its private key.")
    if _declares_eku_without_client_auth(certificate):
        raise SealInvalid(
            "The certificate does not allow client authentication, so it cannot connect to the AEAT."
        )
    organization_id = _attribute(certificate, NameOID.ORGANIZATION_IDENTIFIER)
    serial = _attribute(certificate, NameOID.SERIAL_NUMBER)
    pem = serialization.Encoding.PEM
    return Identity(
        cert_pem=b"".join(c.public_bytes(pem) for c in [certificate, *chain]),
        key_pem=key.private_bytes(
            pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
        holder_tax_id=organization_id or serial,
        kind=_kind(certificate, organization_id, serial),
        expires_at=certificate.not_valid_after_utc,
    )


def current(now: dt.datetime | None = None) -> Identity | None:
    """ERPlora's seal to present with now, or ``None`` if neither slot holds a usable one."""
    now = now or dt.datetime.now(dt.UTC)
    slots = {slot: _slot(slot) for slot in SLOTS}
    usable = {
        slot: identity
        for slot, identity in slots.items()
        if identity is not None and identity.usable_at(now)
    }
    current_seal, next_seal = usable.get("current"), usable.get("next")
    if current_seal is not None and current_seal.usable_at(now + ROTATION_MARGIN):
        return current_seal
    return next_seal or current_seal


def _slot(slot: str) -> Identity | None:
    data_setting, password_setting = SLOTS[slot]
    data = getattr(settings, data_setting, "")
    if not data:
        return None
    try:
        return load(data, getattr(settings, password_setting, ""))
    except SealInvalid as refused:
        logger.warning(
            "fiscal_gateway.seal.slot_unusable slot=%s reason=%s", slot, refused
        )
        return None


def _attribute(certificate: x509.Certificate, oid: x509.ObjectIdentifier) -> str:
    """The subject's first ``oid`` without its ETSI prefix, upper case; empty if it has none."""
    values = certificate.subject.get_attributes_for_oid(oid)
    if not values:
        return ""
    value = str(values[0].value).strip().upper()
    return _ETSI_PREFIX.sub("", value)


def _declares_eku_without_client_auth(certificate: x509.Certificate) -> bool:
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
    except x509.ExtensionNotFound:
        return False
    return not (
        ExtendedKeyUsageOID.CLIENT_AUTH in usages
        or ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE in usages
    )


def _kind(certificate: x509.Certificate, organization_id: str, serial: str) -> Kind:
    der = certificate.public_bytes(serialization.Encoding.DER)
    if _QC_TYPE_ESEAL in der and _QC_TYPE_ESIGN not in der:
        return "seal"
    person = bool(_PERSON_ID.match(serial))
    if organization_id and person:
        return "representative"
    if not organization_id and person:
        return "personal"
    return "unknown"
