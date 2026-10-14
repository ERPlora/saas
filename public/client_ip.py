"""The visitor's real address behind the ALB, in ``REMOTE_ADDR`` for everything downstream.

In production the only way in is the ALB, which APPENDS the address of the peer it talked to (the
visitor) at the end of ``X-Forwarded-For``: anything before it the client may have typed. daphne's
``--proxy-headers`` puts the FIRST entry in ``REMOTE_ADDR`` (forgeable), and the rate limits key on
``REMOTE_ADDR`` (allauth's sign-in, the contact form): a forged header was a fresh budget per
request, and without the header's address the whole internet would share the balancer's
(saas#2154).

``TRUSTED_PROXY_HOPS`` says how many proxies of ours sit in front: 0 locally (``REMOTE_ADDR`` is
the peer and anyone may send the header), 1 in production (the ALB). With N, the visitor is the
N-th entry from the end. A request with fewer entries did not cross them all (hub-next calling
``/internal`` on the private name, a probe) and keeps its peer; so does one whose entry is not an
address, since the limiter masks it with ``ipaddress`` and junk there is a 500.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase


def forwarded_address(header: str, hops: int) -> str | None:
    """The address ``hops`` proxies of ours saw, from ``X-Forwarded-For``; else ``None``."""
    if hops <= 0 or not header:
        return None
    entries = header.split(",")
    if len(entries) < hops:
        return None
    try:
        return str(ipaddress.ip_address(entries[-hops].strip()))
    except ValueError:
        return None


class ClientIpMiddleware:
    """Right after ``SecurityMiddleware``: before anything reads the address."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        address = forwarded_address(
            request.headers.get("X-Forwarded-For", ""), settings.TRUSTED_PROXY_HOPS
        )
        if address:
            request.META["REMOTE_ADDR"] = address
        return self.get_response(request)
