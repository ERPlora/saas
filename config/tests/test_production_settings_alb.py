from django.conf import settings
from django.test import RequestFactory

from config.tests.production_settings import AWS_ENV, development, production


# HTTPS behind the ALB: it terminates TLS, redirects plain HTTP to HTTPS and forwards the request
# to daphne with X-Forwarded-Proto. Same values as the Hub.

PRODUCTION_SECURITY = (
    "(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.SECURE_PROXY_SSL_HEADER,"
    " s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD)"
)


def test_production_cookies_are_secure_and_browsers_are_told_to_stay_on_https():
    assert production(PRODUCTION_SECURITY) == (
        True,
        True,
        # The ALB redirects; Django must not, or the Hub's /internal calls over plain HTTP break.
        False,
        ("HTTP_X_FORWARDED_PROTO", "https"),
        31536000,
        # Every subdomain and the preload list commit the whole domain and are slow to undo: opt-in.
        False,
        False,
    )


def test_hsts_for_subdomains_and_preload_are_opt_in():
    assert production(
        "(s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD)",
        SECURE_HSTS_SECONDS="63072000",
        SECURE_HSTS_INCLUDE_SUBDOMAINS="True",
        SECURE_HSTS_PRELOAD="True",
    ) == (63072000, True, True)


def test_development_stays_on_plain_http():
    assert development(
        "(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS)"
    ) == (False, False, False, 0)


def test_a_request_the_alb_received_over_https_is_secure():
    """CSRF's origin check, the secure cookies and absolute URLs rely on it (the same in every mode)."""
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="https").is_secure()
    assert not RequestFactory().get("/").is_secure()


# The visitor's address: the ALB appends it to X-Forwarded-For (public/client_ip.py).


def test_production_trusts_the_alb_as_its_one_proxy():
    assert production("s.TRUSTED_PROXY_HOPS", **AWS_ENV) == 1


def test_development_trusts_no_proxy():
    """runserver has nobody in front: a forged X-Forwarded-For must not choose the address."""
    assert development("s.TRUSTED_PROXY_HOPS") == 0
    assert settings.TRUSTED_PROXY_HOPS == 0


def test_the_proxy_hops_come_from_the_environment():
    assert production("s.TRUSTED_PROXY_HOPS", TRUSTED_PROXY_HOPS="2") == 2
    assert development("s.TRUSTED_PROXY_HOPS", TRUSTED_PROXY_HOPS="1") == 1
