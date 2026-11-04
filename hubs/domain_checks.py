"""What the DNS and the ALB say of a business's own domain (HUBS-F17; no ORM). Ported from ERPlora/saas
``services/custom_domains.py`` (origin/develop), for ACM and the ALB.

Two proofs, and neither is the website's home page: a business without a published page answers 404 with its domain well
connected (BASE-F110).

- ``points_at``: the customer's CNAME chain ends in the name of THIS business (``target_of``, by its id, which is never
  taken again: its slug can be, so a CNAME left behind would then prove the domain for a stranger; ADR-0502). The
  validation CNAME proves nothing here: ACM reuses it for whoever asks next from this account.
- ``probe``: the Hub, through the ALB, says that name is this business's. It dials OUR address, never what the customer's
  DNS gives, so their DNS cannot aim our servers anywhere else; the SNI, the certificate check and the ``Host`` carry the
  customer's name.

A question that could not be answered says nothing of the customer's domain: ``DnsUnavailable`` and ``Probe.UNREACHABLE``
never count as a failure, or an hour of the platform being away would take down every domain.
"""

import http.client
import json
import logging
import socket
import ssl
from enum import StrEnum
from uuid import UUID

import dns.exception
import dns.resolver
from django.conf import settings

logger = logging.getLogger(__name__)

#: What the Hub answers for a domain it knows (``base.middleware.CustomDomainMiddleware``), under ``/.well-known/``
#: because the WAF stops HTTP libraries on the browser pages.
PROBE_PATH = "/.well-known/erplora-hub"
HTTPS_PORT = 443
#: The Hub's answer is one short line.
PROBE_MAX_BYTES = 4096
PROBE_TIMEOUT_SECONDS = 5.0
#: How long one DNS question may take, retries included.
DNS_LIFETIME_SECONDS = 5.0
#: Providers chain one or two; a loop has to end.
MAX_CNAME_HOPS = 5


class DnsUnavailable(Exception):
    """A DNS question got no usable answer (a timeout, SERVFAIL, no nameserver). «The record is not there» is an answer,
    and is not this: telling a customer to fix a record that may be perfect is the mistake."""


class Zone(StrEnum):
    SUBDOMAIN = "subdomain"
    #: A zone's own name, which cannot hold a CNAME and has no fixed address on the ALB: it is not offered.
    APEX = "apex"
    #: The nearest zone is a top-level domain: nobody has registered the name.
    UNREGISTERED = "unregistered"


class Probe(StrEnum):
    SERVED = "served"
    #: The ALB answered, and not for this business: a certificate that does not verify, a Hub that does not know the
    #: host, another business behind it.
    NOT_SERVED = "not_served"
    #: The platform did not answer: it says nothing of the domain.
    UNREACHABLE = "unreachable"


def target_of(hub_id: UUID) -> str:
    """The name a business's CNAME points at, one for each business and for good."""
    return settings.CUSTOM_DOMAINS_TARGET_TEMPLATE.format(hub_id=hub_id).lower()


def zone_of(domain: str) -> Zone:
    """What ``domain`` is, read from the SOA: counting labels is wrong for ``.co.uk`` and for a delegated subzone."""
    resolver = _resolver()
    try:
        zone = dns.resolver.zone_for_name(domain, resolver=resolver, lifetime=resolver.lifetime)
    except dns.exception.DNSException as error:
        raise DnsUnavailable(f"{domain} SOA: {type(error).__name__}: {error}") from error
    name = _bare(zone.to_text())
    if "." not in name:
        return Zone.UNREGISTERED
    return Zone.APEX if name == domain else Zone.SUBDOMAIN


def points_at(domain: str, target: str) -> bool:
    """Whether the CNAME chain of ``domain`` reaches ``target``; ``DnsUnavailable`` when it could not be read."""
    name = domain
    for _ in range(MAX_CNAME_HOPS):
        records = _lookup(name, "CNAME")
        if not records:
            return False
        name = _bare(records[0])
        if name == target:
            return True
    return False


def probe(domain: str, target: str, hub_id: UUID) -> Probe:
    """What the ALB answers for ``domain``: ``target`` gives its address, and ``hub_id`` is who should be behind it."""
    try:
        addresses = _lookup(target, "A")
    except DnsUnavailable as error:
        logger.warning("hubs.custom_domain.probe target=%s unread: %s", target, error)
        return Probe.UNREACHABLE
    if not addresses:
        logger.error("hubs.custom_domain.probe target=%s resolves to no address", target)
        return Probe.UNREACHABLE
    try:
        status, body = _fetch(min(addresses), domain)
    except ssl.SSLCertVerificationError as error:
        logger.info("hubs.custom_domain.probe domain=%s certificate: %s", domain, error)
        return Probe.NOT_SERVED
    except (OSError, http.client.HTTPException) as error:
        logger.warning("hubs.custom_domain.probe domain=%s no answer: %s", domain, error)
        return Probe.UNREACHABLE
    if status >= 500:
        logger.warning("hubs.custom_domain.probe domain=%s answered %s", domain, status)
        return Probe.UNREACHABLE
    served = _hub_named_by(body) if status == 200 else None
    if served == str(hub_id):
        return Probe.SERVED
    if served:
        logger.error("hubs.custom_domain.probe domain=%s serves hub %s, not %s", domain, served, hub_id)
    return Probe.NOT_SERVED


def _hub_named_by(body: bytes) -> str | None:
    try:
        answer = json.loads(body)
    except ValueError:
        return None
    served = answer.get("hub_id") if isinstance(answer, dict) else None
    return served if isinstance(served, str) else None


def _fetch(address: str, domain: str) -> tuple[int, bytes]:
    """The status and at most ``PROBE_MAX_BYTES`` of the body (past them, nothing): a redirect is not followed."""
    pinned = _PinnedHTTPSConnection(address, domain)
    try:
        pinned.request(
            "GET",
            PROBE_PATH,
            headers={"Accept": "application/json", "Connection": "close", "User-Agent": "ERPlora-domain-check/1"},
        )
        response = pinned.getresponse()
        body = response.read(PROBE_MAX_BYTES + 1)
        return response.status, b"" if len(body) > PROBE_MAX_BYTES else body
    finally:
        pinned.close()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS for ``host`` over a TCP connection to ``address``: what «the ALB serves that name» has to mean."""

    def __init__(self, address: str, host: str) -> None:
        super().__init__(host, HTTPS_PORT, timeout=PROBE_TIMEOUT_SECONDS, context=_tls_context())
        self._address = address

    def connect(self) -> None:
        raw = _open_socket(self._address, self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _open_socket(address: str, timeout: float) -> socket.socket:
    return socket.create_connection((address, HTTPS_PORT), timeout=timeout)


def _tls_context() -> ssl.SSLContext:
    """The default CA context: a real chain, verified for the name asked for."""
    return ssl.create_default_context()


def _lookup(name: str, rdtype: str) -> list[str]:
    """What ``name`` holds for ``rdtype``, as text; a name without it is an empty answer, never a failure."""
    try:
        answer = _resolver().resolve(name, rdtype, raise_on_no_answer=False)
    except dns.resolver.NXDOMAIN:
        return []
    except dns.exception.DNSException as error:
        raise DnsUnavailable(f"{name} {rdtype}: {type(error).__name__}: {error}") from error
    if answer.rrset is None:
        return []
    return [_bare(rdata.to_text()) for rdata in answer.rrset]


def _resolver() -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.lifetime = DNS_LIFETIME_SECONDS
    return resolver


def _bare(name: str) -> str:
    return name.strip().removesuffix(".").lower()
