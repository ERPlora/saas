"""The visitor's real address behind the ALB, in ``REMOTE_ADDR`` for everything downstream.

In production the only way in is the ALB, which APPENDS the address of the peer it talked to (the
visitor) at the end of ``X-Forwarded-For``: anything before it the client may have typed. daphne's
``--proxy-headers`` takes the FIRST entry (forgeable), and the rate limits key on ``REMOTE_ADDR``
(allauth's sign-in and the contact form): a forged header was a fresh budget per request, a missing
rewrite one budget for the whole internet (saas#2154). ``TRUSTED_PROXY_HOPS`` says how many proxies
of ours are in front: 0 locally, 1 in production (the ALB).
"""

import pytest
from allauth.account.adapter import get_adapter as get_account_adapter
from django.conf import settings
from django.http import HttpResponse
from django.test import override_settings

from public.client_ip import ClientIpMiddleware

PEER = "10.0.1.23"


def remote_addr(rf, hops: int, forwarded: str | None = None) -> str:
    """``REMOTE_ADDR`` as the view sees it, after the middleware, with ``hops`` proxies trusted."""
    headers = {} if forwarded is None else {"HTTP_X_FORWARDED_FOR": forwarded}
    request = rf.get("/", REMOTE_ADDR=PEER, **headers)
    seen = {}

    def view(request):
        seen["address"] = request.META["REMOTE_ADDR"]
        return HttpResponse()

    with override_settings(TRUSTED_PROXY_HOPS=hops):
        ClientIpMiddleware(view)(request)
    return seen["address"]


def test_behind_the_alb_the_visitor_is_the_last_hop(rf):
    assert remote_addr(rf, 1, "203.0.113.7") == "203.0.113.7"


def test_what_the_client_prepends_is_ignored(rf):
    """``X-Forwarded-For: 198.51.100.1`` typed by the client: the ALB appends the real one."""
    assert remote_addr(rf, 1, "198.51.100.1, 10.0.0.1, 203.0.113.7") == "203.0.113.7"


def test_the_spaces_around_a_hop_do_not_matter(rf):
    assert remote_addr(rf, 1, "198.51.100.1 ,  203.0.113.7 ") == "203.0.113.7"


def test_an_ipv6_visitor_is_kept(rf):
    assert remote_addr(rf, 1, "2001:db8::1") == "2001:db8::1"


def test_with_two_proxies_the_visitor_is_the_second_hop_from_the_end(rf):
    assert remote_addr(rf, 2, "198.51.100.1, 203.0.113.7, 10.0.0.5") == "203.0.113.7"


def test_locally_the_header_is_not_trusted(rf):
    """Without a proxy in front (runserver, the tests) anyone may send the header."""
    assert remote_addr(rf, 0, "203.0.113.7") == PEER


def test_a_request_without_the_header_keeps_its_peer(rf):
    """hub-next calling ``/internal`` on the private name, a probe: no ALB, no header."""
    assert remote_addr(rf, 1) == PEER
    assert remote_addr(rf, 1, "") == PEER


def test_a_request_that_did_not_cross_every_proxy_keeps_its_peer(rf):
    assert remote_addr(rf, 2, "203.0.113.7") == PEER


@pytest.mark.parametrize("forwarded", ["not-an-ip", "203.0.113.7, unknown", "1.2.3"])
def test_only_a_real_address_replaces_the_peer(rf, forwarded):
    """The limiter masks the address with ``ipaddress``: junk there is a 500 on a public door."""
    assert remote_addr(rf, 1, forwarded) == PEER


def test_it_runs_right_after_the_security_middleware():
    """Before anything reads the address: the sessions, allauth and the views."""
    middleware = settings.MIDDLEWARE

    assert (
        middleware.index("public.client_ip.ClientIpMiddleware")
        == middleware.index("django.middleware.security.SecurityMiddleware") + 1
    )


def test_allauth_reads_the_visitor_too(rf):
    """allauth's sign-in limits key on ``REMOTE_ADDR`` while ``ALLAUTH_TRUSTED_PROXY_COUNT`` is 0;
    set as well, it would count the ALB twice."""
    request = rf.get(
        "/", REMOTE_ADDR=PEER, HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7"
    )
    seen = {}

    def view(request):
        seen["ip"] = get_account_adapter(request).get_client_ip(request)
        return HttpResponse()

    with override_settings(TRUSTED_PROXY_HOPS=1):
        ClientIpMiddleware(view)(request)

    assert seen["ip"] == "203.0.113.7"
    assert getattr(settings, "ALLAUTH_TRUSTED_PROXY_COUNT", 0) == 0
    assert getattr(settings, "ALLAUTH_TRUSTED_CLIENT_IP_HEADER", None) is None
