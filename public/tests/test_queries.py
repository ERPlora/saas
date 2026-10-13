"""Reads of the public web as operations: ``public.app.release`` (PLAN-SAAS §6).

``GET /api/v1/app/release/`` (port of ``apps/public/appdist`` ``release``, origin/develop c5ca8ca) is
now a ninja route bound to this query, so the route, the API keys and any later caller run the same
function. The version comes from ``public.appdist.published_release`` (the bucket read and its
cache); the query neither touches the ORM nor needs a permission: the installed app asks before any
account exists.
"""

from unittest.mock import patch

import pytest
from live.context import OperationContext, Scope
from live.operations import get

from public import queries
from public.schemas import AppReleaseIn

pytestmark = pytest.mark.django_db


def visitor():
    return OperationContext(scope=Scope("user", "anonymous"), actor=None, language="en")


def test_the_operation_is_a_query_open_to_anyone():
    operation = get("public.app.release")

    assert operation.kind == "query"
    assert operation.permission is None
    assert operation is queries.app_release


def test_it_answers_the_published_version():
    with patch("public.appdist.published_release", return_value="1.4.0"):
        result = queries.app_release(visitor(), AppReleaseIn())

    assert result.version == "1.4.0"


def test_it_answers_null_when_the_version_is_unknown():
    with patch("public.appdist.published_release", return_value=None):
        result = queries.app_release(visitor(), AppReleaseIn())

    assert result.version is None


def test_it_asks_for_the_current_time_bucket(monkeypatch):
    """The bucket is ``time() // RELEASE_CACHE_TTL``: the cache key that expires the reading."""
    from public import appdist

    monkeypatch.setattr(queries.time, "time", lambda: appdist.RELEASE_CACHE_TTL * 7 + 5)
    with patch("public.appdist.published_release", return_value=None) as release:
        queries.app_release(visitor(), AppReleaseIn())

    release.assert_called_once_with(7)
