"""What the DNS and the ALB say of a business's own domain (HUBS-F17; cases ported from ERPlora/saas
``test_custom_domain_own_edge.py``, origin/develop): the CNAME chain of the customer and the Hub's probe, faked at the
resolver and at the socket. No test here touches a real name."""

import io
import json
import socket
import ssl
from unittest.mock import MagicMock
from uuid import UUID

import dns.exception
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import pytest

from hubs import domain_checks
from hubs.domain_checks import DnsUnavailable, Probe, Zone

DOMAIN = "www.minegocio.es"
HUB_ID = UUID("0193a0a0-0000-7000-8000-000000000001")
OTHER_HUB_ID = UUID("0193a0a0-0000-7000-8000-000000000002")
TARGET = f"hub-{HUB_ID}.erplora.com"
OUR_ADDRESS = "203.0.113.10"
CUSTOMERS_ADDRESS = "10.0.0.5"


# --- The DNS -----------------------------------------------------------------------------------------


def test_a_cname_onto_this_businesss_name_points_at_it(dns_world):
    dns_world[(DOMAIN, "CNAME")] = [TARGET]
    assert domain_checks.points_at(DOMAIN, TARGET) is True


def test_a_chain_of_cnames_that_ends_in_this_businesss_name_points_at_it(dns_world):
    dns_world[(DOMAIN, "CNAME")] = ["shop.provider.example"]
    dns_world[("shop.provider.example", "CNAME")] = [TARGET]
    assert domain_checks.points_at(DOMAIN, TARGET) is True


def test_the_comparison_ignores_case_and_the_final_dot(dns_world):
    dns_world[(DOMAIN, "CNAME")] = [TARGET.upper() + "."]
    assert domain_checks.points_at(DOMAIN, TARGET) is True


@pytest.mark.parametrize(
    "record",
    [
        f"hub-{OTHER_HUB_ID}.erplora.com",
        "mi-negocio.erplora.com",
        "erplora.com",
        f"hub-{HUB_ID}.erplora.com.evil.example",
    ],
    ids=["another business's name", "its slug, which a new business can take", "the apex", "a name that only starts like it"],
)
def test_a_cname_onto_any_other_name_does_not_point_at_it(dns_world, record):
    dns_world[(DOMAIN, "CNAME")] = [record]
    assert domain_checks.points_at(DOMAIN, TARGET) is False


def test_no_record_does_not_point_at_it(dns_world):
    assert domain_checks.points_at(DOMAIN, TARGET) is False


def test_a_lookup_that_fails_is_not_a_missing_record(dns_world):
    dns_world[(DOMAIN, "CNAME")] = dns.exception.Timeout()
    with pytest.raises(DnsUnavailable):
        domain_checks.points_at(DOMAIN, TARGET)


def test_a_chain_is_followed_only_so_far(dns_world):
    """A loop or a chain nobody would use ends, without asking for ever."""
    dns_world[(DOMAIN, "CNAME")] = ["a.example"]
    dns_world[("a.example", "CNAME")] = ["b.example"]
    dns_world[("b.example", "CNAME")] = ["a.example"]
    assert domain_checks.points_at(DOMAIN, TARGET) is False


@pytest.mark.parametrize(
    ("zone", "kind"),
    [
        ("minegocio.es.", Zone.SUBDOMAIN),
        ("minegocio.co.uk.", Zone.SUBDOMAIN),
        ("www.minegocio.es.", Zone.APEX),
        ("es.", Zone.UNREGISTERED),
    ],
    ids=["a subdomain", "under a two-label suffix", "a zone's own name, or a delegated subzone", "nobody registered it"],
)
def test_the_zone_read_from_the_dns_says_what_a_name_is(monkeypatch, zone, kind):
    monkeypatch.setattr(dns.resolver, "zone_for_name", lambda name, **_: dns.name.from_text(zone))
    domain = "tienda.minegocio.co.uk" if "co.uk" in zone else DOMAIN
    assert domain_checks.zone_of(domain) == kind


def test_a_zone_that_cannot_be_read_is_not_a_guess(monkeypatch):
    def fails(name, **_):
        raise dns.resolver.NoNameservers()

    monkeypatch.setattr(dns.resolver, "zone_for_name", fails)
    with pytest.raises(DnsUnavailable):
        domain_checks.zone_of(DOMAIN)


class _Answer:
    def __init__(self, rrset):
        self.rrset = rrset


def _resolver_answers(monkeypatch, answer):
    def resolve(self, name, rdtype, raise_on_no_answer=True):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", resolve)


def _rdata(rdtype, text):
    return dns.rdata.from_text(dns.rdataclass.IN, rdtype, text)


def test_lookup_gives_a_cname_as_text_without_its_final_dot(monkeypatch):
    _resolver_answers(monkeypatch, _Answer([_rdata(dns.rdatatype.CNAME, "HUB.erplora.com.")]))
    assert domain_checks._lookup(DOMAIN, "CNAME") == ["hub.erplora.com"]


def test_lookup_gives_an_address_as_text(monkeypatch):
    _resolver_answers(monkeypatch, _Answer([_rdata(dns.rdatatype.A, OUR_ADDRESS)]))
    assert domain_checks._lookup(TARGET, "A") == [OUR_ADDRESS]


def test_a_name_without_that_record_is_an_empty_answer(monkeypatch):
    _resolver_answers(monkeypatch, _Answer(None))
    assert domain_checks._lookup(DOMAIN, "CNAME") == []


def test_a_name_that_does_not_exist_is_an_empty_answer(monkeypatch):
    _resolver_answers(monkeypatch, dns.resolver.NXDOMAIN())
    assert domain_checks._lookup(DOMAIN, "CNAME") == []


@pytest.mark.parametrize("failure", [dns.resolver.LifetimeTimeout(timeout=1, errors=[]), dns.resolver.NoNameservers()])
def test_a_timeout_or_a_servfail_is_a_lookup_that_failed(monkeypatch, failure):
    _resolver_answers(monkeypatch, failure)
    with pytest.raises(DnsUnavailable):
        domain_checks._lookup(DOMAIN, "CNAME")


def test_the_resolver_gives_up_quickly():
    assert domain_checks._resolver().lifetime <= 5


# --- The probe ---------------------------------------------------------------------------------------


def _http(status=200, body=b"", headers=None):
    head = [f"HTTP/1.1 {status} X", f"Content-Length: {len(body)}", "Content-Type: application/json"]
    head += [f"{name}: {value}" for name, value in (headers or {}).items()]
    return ("\r\n".join(head) + "\r\n\r\n").encode() + body


def _hub_answers(hub_id=HUB_ID):
    return _http(body=json.dumps({"hub_id": str(hub_id)}).encode())


class _FakeTls:
    def __init__(self, response):
        self.response = response
        self.sent = b""

    def sendall(self, data):
        self.sent += data

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.response)

    def settimeout(self, _timeout):
        pass

    def close(self):
        pass


class _Edge:
    """The ALB, faked at the socket: which address was dialled, which SNI was asked for and what it answers."""

    def __init__(self, answer=b"", *, connect_error=None, tls_error=None):
        self.answer, self.connect_error, self.tls_error = answer, connect_error, tls_error
        self.dialled: list[str] = []
        self.sni: list[str] = []
        self.tls: _FakeTls | None = None

    def open_socket(self, address, timeout):
        self.dialled.append(address)
        if self.connect_error is not None:
            raise self.connect_error
        return MagicMock(name=f"tcp-{address}")

    def tls_context(self):
        edge = self

        class _Context:
            def wrap_socket(self, sock, server_hostname):
                edge.sni.append(server_hostname)
                if edge.tls_error is not None:
                    raise edge.tls_error
                edge.tls = _FakeTls(edge.answer)
                return edge.tls

        return _Context()


@pytest.fixture
def edge(monkeypatch, dns_world):
    """Our name resolves to the ALB, and the customer's to anywhere else."""
    dns_world[(TARGET, "A")] = [OUR_ADDRESS]
    dns_world[(DOMAIN, "A")] = [CUSTOMERS_ADDRESS]

    def build(*args, **kwargs):
        built = _Edge(*args, **kwargs)
        monkeypatch.setattr(domain_checks, "_open_socket", built.open_socket)
        monkeypatch.setattr(domain_checks, "_tls_context", built.tls_context)
        return built

    return build


def test_the_probe_is_served_when_the_alb_answers_for_this_business(edge):
    assert_edge = edge(_hub_answers())
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.SERVED
    assert assert_edge.dialled == [OUR_ADDRESS]


def test_the_probe_dials_our_address_never_the_one_the_customers_dns_gives(edge):
    """Their DNS must not be able to aim our servers anywhere else (saas#2160 of the old product)."""
    the_edge = edge(_hub_answers())
    domain_checks.probe(DOMAIN, TARGET, HUB_ID)
    assert CUSTOMERS_ADDRESS not in the_edge.dialled


def test_the_probe_asks_for_the_customers_name_by_sni_and_host_on_the_hubs_door(edge):
    the_edge = edge(_hub_answers())
    domain_checks.probe(DOMAIN, TARGET, HUB_ID)
    assert the_edge.sni == [DOMAIN]
    sent = the_edge.tls.sent.decode()
    assert sent.startswith("GET /.well-known/erplora-hub HTTP/1.1\r\n")
    assert f"Host: {DOMAIN}\r\n" in sent


@pytest.mark.parametrize(
    "answer",
    [
        _hub_answers(OTHER_HUB_ID),
        _http(status=400, body=b"Bad Request"),
        _http(status=404),
        _http(status=301, headers={"Location": "https://elsewhere.example/"}),
        _http(body=b"not json"),
        _http(body=b"[1, 2]"),
        _http(body=b"{}"),
        _http(body=b'{"hub_id": ""}'),
        _http(body=b'{"hub_id": 7}'),
        _http(body=b"x" * (domain_checks.PROBE_MAX_BYTES + 1)),
    ],
    ids=[
        "another business behind the name",
        "the Hub does not know the host",
        "nothing there",
        "a redirect, never followed",
        "not JSON",
        "not an object",
        "no id",
        "an empty id",
        "an id that is no text",
        "over the cap",
    ],
)
def test_an_answer_that_is_not_this_business_is_not_served(edge, answer):
    edge(answer)
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.NOT_SERVED


def test_a_certificate_that_does_not_verify_for_that_name_is_not_served(edge):
    edge(tls_error=ssl.SSLCertVerificationError("hostname mismatch"))
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.NOT_SERVED


def test_the_certificate_is_verified_against_the_customers_name():
    context = domain_checks._tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_the_platform_failing_says_nothing_of_the_domain(edge, status):
    """A Hub or an ALB that is down for three hours must not take every customer's domain with it."""
    edge(_http(status=status))
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.UNREACHABLE


@pytest.mark.parametrize(
    "failure",
    [ConnectionRefusedError(), TimeoutError(), socket.gaierror(), OSError("no route")],
    ids=["refused", "timed out", "no name", "no route"],
)
def test_no_connection_says_nothing_of_the_domain(edge, failure):
    edge(connect_error=failure)
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.UNREACHABLE


def test_a_tls_error_other_than_the_certificate_says_nothing_of_the_domain(edge):
    edge(tls_error=ssl.SSLError("handshake failure"))
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.UNREACHABLE


def test_our_own_name_not_resolving_says_nothing_of_the_domain(edge, dns_world):
    the_edge = edge(_hub_answers())
    dns_world[(TARGET, "A")] = []
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.UNREACHABLE
    assert the_edge.dialled == []


def test_our_own_name_that_cannot_be_read_says_nothing_of_the_domain(edge, dns_world):
    the_edge = edge(_hub_answers())
    dns_world[(TARGET, "A")] = dns.exception.Timeout()
    assert domain_checks.probe(DOMAIN, TARGET, HUB_ID) == Probe.UNREACHABLE
    assert the_edge.dialled == []


def test_the_name_a_business_is_told_to_point_at_comes_from_the_template(settings):
    settings.CUSTOM_DOMAINS_TARGET_TEMPLATE = "hub-{hub_id}.erplora.com"
    assert domain_checks.target_of(HUB_ID) == f"hub-{HUB_ID}.erplora.com"
