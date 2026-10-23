"""``/csp-report/`` with its brake per address (ACCOUNTS-G78): the browsers' reports of a blocked script.

``live.csp.csp_report`` logs each report (up to 8 KB) and answers 204. Anyone may post there, with no session nor CSRF
(a browser sends the report on its own), so an address past ``CSP_REPORT_RATELIMIT`` (60 an hour, the old SaaS's) is
answered 429 and its report is not logged: the log never fills from one address. The address is the one the load
balancer saw (``public.client_ip`` put it in ``REMOTE_ADDR``), never one the request typed (saas#2531). With the cache
down the brake lets reports through (``RATELIMIT_FAIL_OPEN``).
"""

import ipaddress

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.core import is_ratelimited
from live.csp import csp_report as log_csp_report


def _address(group, request: HttpRequest) -> str:
    """``REMOTE_ADDR`` when it is an address; one shared budget for anything else (never a 500)."""
    try:
        return str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return "unknown"


@csrf_exempt
@require_POST
def csp_report(request: HttpRequest) -> HttpResponse:
    if is_ratelimited(
        request, group="base.csp_report", key=_address, rate=settings.CSP_REPORT_RATELIMIT, increment=True
    ):
        return HttpResponse(status=429)
    return log_csp_report(request)
