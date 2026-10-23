"""ACCOUNTS-G78: ``/csp-report/``, the browsers' reports of a blocked script, has its brake per address.

Anyone may post there (no session, no CSRF: a browser sends it on its own) and each report is a log line of up to 8 KB
(``live.csp.csp_report``): unbraked, one address could fill the log, and the log costs. The old SaaS kept 60 an hour per
address (SAAS-F05), counted by the address the load balancer saw (``public.client_ip``), never by anything the request
says about itself (saas#2531). Past it the report is answered 429 and not logged; another address keeps its own budget.
"""

import json
import logging

import pytest
from django.core.cache import cache

REPORT = json.dumps({"csp-report": {"violated-directive": "script-src", "blocked-uri": "https://evil.example/x.js"}})


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


def post(client, address: str, **extra):
    return client.post("/csp-report/", REPORT, content_type="application/csp-report", REMOTE_ADDR=address, **extra)


def test_the_limit_is_60_an_hour_per_address(settings):
    assert settings.CSP_REPORT_RATELIMIT == "60/h"


def test_past_the_limit_a_report_is_refused_and_not_logged(client, settings, caplog):
    settings.CSP_REPORT_RATELIMIT = "3/h"

    statuses = [post(client, "203.0.113.7").status_code for _ in range(3)]
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="live.csp"):
        refused = post(client, "203.0.113.7")

    assert statuses == [204, 204, 204]
    assert refused.status_code == 429
    assert "csp.violation" not in caplog.text


def test_another_address_keeps_its_own_budget(client, settings, caplog):
    settings.CSP_REPORT_RATELIMIT = "1/h"
    post(client, "203.0.113.7")
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="live.csp"):
        response = post(client, "198.51.100.4")

    assert response.status_code == 204
    assert "csp.violation" in caplog.text


def test_a_typed_forwarded_address_buys_no_new_budget(client, settings):
    settings.CSP_REPORT_RATELIMIT = "1/h"
    post(client, "203.0.113.7", HTTP_X_FORWARDED_FOR="10.0.0.1")

    response = post(client, "203.0.113.7", HTTP_X_FORWARDED_FOR="10.0.0.2")

    assert response.status_code == 429


def test_only_a_post_is_a_report(client):
    assert client.get("/csp-report/").status_code == 405
