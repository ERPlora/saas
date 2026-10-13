"""django-cookie-consent's cookie cleaner, only where there is something to clean.

``cookie_consent.middleware.CleanCookiesMiddleware`` deletes the cookies of a group that was
declined or never accepted, and reads the cookie groups (cache, then database) on every response to
do it. A request that carries no cookie (an API client, ``/readyz``, a crawler) has nothing to
delete, so it skips that read.
"""

from __future__ import annotations

from cookie_consent.middleware import (
    CleanCookiesMiddleware as ConsentCleanCookiesMiddleware,
)


class CleanCookiesMiddleware(ConsentCleanCookiesMiddleware):
    def __call__(self, request):
        if not request.COOKIES:
            return self.get_response(request)
        return super().__call__(request)
