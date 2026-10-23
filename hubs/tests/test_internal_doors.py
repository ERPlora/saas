"""HUBS-F35 (HUBS-G62, HUBS-G99): every door under ``/internal`` hears only the Hub's signed call, whichever app
serves it.

The old SaaS opened its machine doors with four credentials (a machine key, a business secret in ``X-Hub-Token``, a
short pass or a person's session) and told an inactive business apart before checking any (SAAS_DASHBOARD-F50). Here
there is one: the HMAC-SHA256 of the shared secret (the current one or, during a rotation, the previous one) with a
timestamp of the last five minutes (``accounts.signing``). A session, even the staff's, opens nothing; nor does a call
signed with another secret or too long ago. The business is the one the path names, never a header (PLAN-SAAS §2).

The doors are read from the URL resolver, so one added tomorrow without the check fails here.
"""

import json
import re
import time
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import URLPattern, URLResolver, get_resolver

from accounts.signing import signed_headers

pytestmark = pytest.mark.django_db

SECRET = "internal-doors-secret"
METHODS = ("GET", "POST", "PUT", "DELETE")
#: An unsigned call is refused (401) or not on that method (405); nothing else, ever.
REFUSED = {401, 405}
_CONVERTER = re.compile(r"<(?:(?P<kind>[a-z]+):)?(?P<name>\w+)>")
_SAMPLES = {"uuid": str(uuid.uuid7()), "int": "1", "path": "x", "slug": "x", "str": "x", None: "x"}


def _routes(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route


def internal_doors() -> list[str]:
    """Every route under ``internal/``, with its converters filled: ``/internal/hubs/<uuid>/ready``."""
    doors = {
        "/" + _CONVERTER.sub(lambda match: _SAMPLES.get(match.group("kind"), "x"), route).lstrip("^").rstrip("$")
        for route in _routes(get_resolver().url_patterns)
        if route.lstrip("^").startswith("internal/")
    }
    return sorted(doors)


DOORS = internal_doors()


@pytest.fixture(autouse=True)
def shared_secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""


def call(client, method, path, *, headers=None, body=b"{}"):
    return client.generic(method, path, body, content_type="application/json", headers=headers or {})


def test_the_doors_are_found():
    """The walk sees the doors of every app that serves one (a resolver change must not empty this module)."""
    assert {"/internal/auth/redeem", "/internal/verifactu/submit", "/internal/whatsapp/send"} <= set(DOORS)
    assert any(door.endswith("/ready") for door in DOORS)
    assert len(DOORS) >= 14


@pytest.mark.parametrize("door", DOORS)
def test_an_unsigned_call_is_refused(client, door):
    answers = {method: call(client, method, door) for method in METHODS}

    assert {status.status_code for status in answers.values()} <= REFUSED, door
    unauthorized = [answer for answer in answers.values() if answer.status_code == 401]
    assert unauthorized, f"{door} never says 401 without a signature"
    assert all(answer.json()["error"]["code"] == "unauthorized" for answer in unauthorized)


@pytest.mark.parametrize("door", DOORS)
def test_a_staff_session_opens_nothing(client, door):
    client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))

    assert {call(client, method, door).status_code for method in METHODS} <= REFUSED, door


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize(
    ("secret", "age"),
    [("another-secret", 0), (SECRET, 10 * 60)],
    ids=["another secret", "ten minutes old"],
)
def test_a_call_signed_badly_or_too_long_ago_is_refused(client, door, secret, age):
    body = json.dumps({"id": str(uuid.uuid7())}).encode()
    for method in METHODS:
        headers = signed_headers(method, door, body, int(time.time()) - age, secret)

        assert call(client, method, door, headers=headers, body=body).status_code in REFUSED, (door, method)
