"""The shared Valkey as a cache that fails soft: Valkey down is a cache that forgets, never a 500.

Everything that reads the cache on a request (the cookie banner on every public page, allauth's
sign-in limits, the contact form's) took the site down with Valkey. ``base.cache.FailSoftRedisCache``
answers a failed call as Django's ``DummyCache`` would (a cache that keeps nothing) and warns once a
minute per process, not once per request.
"""

from unittest import mock

import pytest
import redis.exceptions
from django.core.cache.backends.dummy import DummyCache

from base import cache as fail_soft
from base.cache import FailSoftRedisCache

#: Nothing listens on port 1: every call is a real refused connection, at once.
DOWN = "redis://127.0.0.1:1"
OPTIONS = {"socket_connect_timeout": 0.5, "socket_timeout": 0.5}


@pytest.fixture(autouse=True)
def fresh_warning_clock(monkeypatch):
    """Each test starts as a process that has not warned yet."""
    monkeypatch.setattr(fail_soft, "_last_warning", None)


@pytest.fixture
def down():
    return FailSoftRedisCache(DOWN, {"OPTIONS": OPTIONS})


def with_client(client) -> FailSoftRedisCache:
    """A cache whose Redis client is ``client`` (``_cache`` is a cached property)."""
    cache = FailSoftRedisCache(DOWN, {"OPTIONS": OPTIONS})
    cache.__dict__["_cache"] = client
    return cache


# --- Valkey down: the answer of a cache that keeps nothing, no exception -------------------------


def test_get_is_a_miss(down):
    assert down.get("key") is None
    assert down.get("key", "fallback") == "fallback"


def test_get_many_is_empty(down):
    assert down.get_many(["a", "b"]) == {}


def test_has_key_is_false(down):
    assert down.has_key("key") is False


@pytest.mark.parametrize(
    "call",
    [
        lambda cache: cache.set("key", 1),
        lambda cache: cache.delete_many(["a", "b"]),
        lambda cache: cache.clear(),
    ],
    ids=["set", "delete_many", "clear"],
)
def test_a_write_does_nothing(down, call):
    assert call(down) is None


def test_set_many_stores_nothing(down):
    assert down.set_many({"a": 1, "b": 2}) == []


@pytest.mark.parametrize("method", ["touch", "delete"])
def test_touch_and_delete_find_nothing(down, method):
    assert getattr(down, method)("key") is False


def test_add_succeeds_as_on_an_empty_cache(down):
    """allauth takes its rate-limit lock with ``add`` and refuses the sign-in when it never gets it:
    «not stored» there would be a 429 on every login while Valkey is down."""
    assert down.add("key", 1) is True


@pytest.mark.parametrize("method", ["incr", "decr"])
def test_incr_finds_no_key(down, method):
    """Django's contract for a missing key, the same as the local cache: callers already handle it
    (django-ratelimit does)."""
    with pytest.raises(ValueError):
        getattr(down, method)("key")


def test_get_or_set_hands_back_the_computed_value(down):
    """What django-cookie-consent does on every page: the groups come from the database."""
    assert down.get_or_set("key", lambda: "from the database") == "from the database"


def test_each_failed_method_answers_as_the_dummy_cache(down):
    dummy = DummyCache("", {})

    for method, args in [
        ("get", ("key", "fallback")),
        ("add", ("key", 1)),
        ("set", ("key", 1)),
        ("touch", ("key",)),
        ("delete", ("key",)),
        ("get_many", (["a"],)),
        ("has_key", ("key",)),
        ("set_many", ({"a": 1},)),
        ("delete_many", (["a"],)),
        ("clear", ()),
    ]:
        assert getattr(down, method)(*args) == getattr(dummy, method)(*args), method


@pytest.mark.parametrize(
    "error",
    [
        redis.exceptions.ConnectionError("Error 111 connecting"),
        redis.exceptions.TimeoutError("Timeout reading from socket"),
        ConnectionError("Connection reset by peer"),
        TimeoutError("timed out"),
        OSError("Network is unreachable"),
    ],
    ids=["redis-connection", "redis-timeout", "connection", "timeout", "os"],
)
def test_every_failure_of_the_connection_is_a_miss(error):
    client = mock.Mock(**{"get.side_effect": error})

    assert with_client(client).get("key", "fallback") == "fallback"


def test_a_bug_that_is_not_the_connection_is_not_swallowed():
    client = mock.Mock(**{"get.side_effect": TypeError("a bug")})

    with pytest.raises(TypeError, match="a bug"):
        with_client(client).get("key")


# --- Valkey up: plain delegation -----------------------------------------------------------------


def test_with_valkey_up_every_method_is_redis_cache():
    client = mock.Mock(
        **{
            "get.return_value": "cached",
            "add.return_value": False,
            "touch.return_value": True,
            "delete.return_value": True,
            "get_many.return_value": {":1:a": 1},
            "has_key.return_value": True,
            "incr.return_value": 5,
            "clear.return_value": True,
        }
    )
    cache = with_client(client)

    assert cache.get("key") == "cached"
    client.get.assert_called_once_with(":1:key", None)
    assert cache.add("key", 1) is False
    assert cache.touch("key") is True
    assert cache.delete("key") is True
    assert cache.get_many(["a"]) == {"a": 1}
    assert cache.has_key("key") is True
    assert cache.incr("key") == 5
    assert cache.clear() is True
    assert cache.set("key", 1) is None
    client.set.assert_called_once_with(":1:key", 1, 300)
    assert cache.set_many({"a": 1}) == []
    client.set_many.assert_called_once_with({":1:a": 1}, 300)
    cache.delete_many(["a"])
    client.delete_many.assert_called_once_with([":1:a"])


# --- One warning a minute per process, not one per request ---------------------------------------


def warnings_of(caplog) -> list[str]:
    return [
        record.getMessage() for record in caplog.records if record.name == "base.cache"
    ]


def test_a_failure_says_so(down, caplog):
    with caplog.at_level("WARNING", logger="base.cache"):
        down.get("key")

    (message,) = warnings_of(caplog)
    assert "get" in message
    assert "Connection" in message or "connect" in message


def test_the_warning_is_once_a_minute_per_process(down, caplog, monkeypatch):
    clock = iter([1000.0, 1001.0, 1059.0, 1060.0, 1061.0])
    monkeypatch.setattr(fail_soft, "monotonic", lambda: next(clock))

    with caplog.at_level("WARNING", logger="base.cache"):
        for _ in range(5):
            down.get("key")

    assert len(warnings_of(caplog)) == 2
