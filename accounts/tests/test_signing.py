"""HMAC-SHA256 + timestamp of the internal calls (PLAN-SAAS §2): hex HMAC of ``f"{ts}.{body}"``."""

import hashlib
import hmac

import pytest

from accounts.signing import sign, verify

SECRET = "test-internal-secret"
BODY = b'{"code": "abc", "hub": "a"}'
NOW = 1_800_000_000


def _expected(timestamp, body=BODY, secret=SECRET):
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def test_sign_is_the_hex_hmac_sha256_of_timestamp_dot_body():
    assert sign(BODY, NOW, SECRET) == _expected(NOW)


def test_a_fresh_correct_signature_verifies():
    assert verify(BODY, str(NOW), _expected(NOW), secret=SECRET, now=NOW) is True


@pytest.mark.parametrize("skew", [-300, 300])
def test_up_to_five_minutes_of_clock_skew_is_accepted(skew):
    timestamp = NOW + skew

    assert verify(BODY, str(timestamp), _expected(timestamp), secret=SECRET, now=NOW) is True


@pytest.mark.parametrize("skew", [-301, 301])
def test_a_timestamp_more_than_five_minutes_away_is_refused(skew):
    timestamp = NOW + skew

    assert verify(BODY, str(timestamp), _expected(timestamp), secret=SECRET, now=NOW) is False


def test_another_body_is_refused():
    assert verify(b'{"code": "abd", "hub": "a"}', str(NOW), _expected(NOW), secret=SECRET, now=NOW) is False


def test_another_secret_is_refused():
    signature = _expected(NOW, secret="someone-else")

    assert verify(BODY, str(NOW), signature, secret=SECRET, now=NOW) is False


@pytest.mark.parametrize(
    ("timestamp", "signature"),
    [(None, "x"), ("", "x"), (str(NOW), None), (str(NOW), ""), ("soon", "x"), ("1.5e9", "x")],
)
def test_missing_or_malformed_headers_are_refused(timestamp, signature):
    signature = _expected(NOW) if signature == "x" else signature

    assert verify(BODY, timestamp, signature, secret=SECRET, now=NOW) is False


def test_nothing_verifies_without_a_secret():
    assert verify(BODY, str(NOW), _expected(NOW, secret=""), secret="", now=NOW) is False


@pytest.mark.parametrize(("timestamp", "signature"), [(str(NOW), "ñ" * 64), ("١٨٠٠٠٠٠٠٠٠", "x")])
def test_non_ascii_headers_are_refused_without_raising(timestamp, signature):
    signature = _expected(NOW) if signature == "x" else signature

    assert verify(BODY, timestamp, signature, secret=SECRET, now=NOW) is False
