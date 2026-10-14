"""django-cookie-consent's cookie cleaner, only where there is something to clean.

``cookie_consent.middleware.CleanCookiesMiddleware`` deletes the cookies of a group that was
declined or never accepted, and reads the cookie groups (cache, then database) on every response to
do it. A request that carries no cookie (an API client, ``/readyz``, a crawler) has nothing to
delete, so it skips that read.

The cleaning is housekeeping, not the response: with the cache (the shared Valkey) down or hanging,
the response goes out uncleaned with a warning, and the next one with the cache back cleans. Only
the cache's own failures are tolerated; any other error stays a visible 500.
"""

from __future__ import annotations

import logging

from cookie_consent.middleware import (
    CleanCookiesMiddleware as ConsentCleanCookiesMiddleware,
)
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

#: What Django's ``RedisCache`` lets through when Valkey is down or hangs: redis-py's own errors
#: and the socket's (the builtin ``ConnectionError`` and ``TimeoutError`` are ``OSError``).
CACHE_ERRORS = (RedisError, OSError)


class CleanCookiesMiddleware(ConsentCleanCookiesMiddleware):
    def __call__(self, request):
        if not request.COOKIES:
            return self.get_response(request)
        return super().__call__(request)

    def process_response(self, request, response):
        try:
            return super().process_response(request, response)
        except CACHE_ERRORS:
            logger.warning(
                "Cookie cleaning skipped: the cookie groups' cache is unreachable.",
                exc_info=True,
            )
            return response
