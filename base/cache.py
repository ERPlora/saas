"""The shared Valkey as a cache that fails soft: Valkey down is a cache that forgets, never a 500.

The cache is only a cache (PLAN §16: no sessions, no PIN in it), yet a request reads it on every
public page (django-cookie-consent's groups, through the banner), on every sign-in (allauth's
limits) and on the contact form (django-ratelimit). With Django's ``RedisCache`` alone, Valkey down
was the site down.

``FailSoftRedisCache`` is ``RedisCache`` that answers a call failing on the connection
(``RedisError``, or the socket's ``OSError``) as Django's ``DummyCache`` would: a cache that keeps
nothing. ``get`` is the default, a write does nothing, ``touch``/``delete``/``has_key`` find
nothing, ``incr`` raises ``ValueError`` as for any missing key, and ``add`` succeeds, as on an empty
cache: allauth takes its limits' lock with ``add`` and refuses the sign-in when it never gets it.
So the limits let requests through while Valkey is down (``RATELIMIT_FAIL_OPEN`` in the settings);
the WAF keeps limiting sign-in, sign-up and passwords per IP. Any other error is a bug and raises.

One warning a minute per process says it is happening, not one per request.
"""

from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Any

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

#: What a Valkey that is down or hangs raises: redis-py's errors and the socket's (the builtin
#: ``ConnectionError`` and ``TimeoutError`` are ``OSError``).
CONNECTION_ERRORS = (RedisError, OSError)
#: Seconds between two warnings of this process while Valkey stays down.
WARNING_INTERVAL = 60.0

_warning_lock = threading.Lock()
#: ``monotonic()`` of this process's last warning; ``None`` before the first.
_last_warning: float | None = None


def _warn(method: str, error: Exception) -> None:
    global _last_warning
    now = monotonic()
    with _warning_lock:
        if _last_warning is not None and now - _last_warning < WARNING_INTERVAL:
            return
        _last_warning = now
    logger.warning(
        "Cache unreachable, %s answered as an empty cache (next warning in %d s at most): %r",
        method,
        WARNING_INTERVAL,
        error,
    )


class FailSoftRedisCache(RedisCache):
    def __init__(self, server, params):
        super().__init__(server, params)
        self._forgetful = DummyCache(server, params)

    def _soft(self, method: str, call, *args) -> Any:
        try:
            return call(*args)
        except CONNECTION_ERRORS as error:
            _warn(method, error)
            return getattr(self._forgetful, method)(*args)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._soft("add", super().add, key, value, timeout, version)

    def get(self, key, default=None, version=None):
        return self._soft("get", super().get, key, default, version)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._soft("set", super().set, key, value, timeout, version)

    def touch(self, key, timeout=DEFAULT_TIMEOUT, version=None):
        return self._soft("touch", super().touch, key, timeout, version)

    def delete(self, key, version=None):
        return self._soft("delete", super().delete, key, version)

    def get_many(self, keys, version=None):
        return self._soft("get_many", super().get_many, keys, version)

    def has_key(self, key, version=None):
        return self._soft("has_key", super().has_key, key, version)

    def incr(self, key, delta=1, version=None):
        return self._soft("incr", super().incr, key, delta, version)

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None):
        return self._soft("set_many", super().set_many, data, timeout, version)

    def delete_many(self, keys, version=None):
        return self._soft("delete_many", super().delete_many, keys, version)

    def clear(self):
        return self._soft("clear", super().clear)
