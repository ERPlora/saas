"""The tries an account may make, counted once per request, and the refusal past them."""

from django.utils.translation import gettext
from live.errors import OperationError


#: Where a request keeps the tries it counted, by limit: the window's seconds left then, and whether it was past it.
_COUNTED_TRIES = "_accounts_counted_tries"


def _spent(request, rate: str, group: str, key: str) -> bool:
    """Whether ``key`` has spent ``rate`` with this try (django-ratelimit, over the cache): once per request.

    The try counts as it checks, so two at once never pass the limit together. A cut that rolls a try back runs it
    again (``repeatable``), and no rollback undoes a count in the cache: the try after it keeps the answer the request
    already got, and its place under the limit, unless the limit's window turned meanwhile, when it counts in the new
    one. A window turns when its seconds left grow, which holds while the window is longer than the wait of a request
    (``LIVE["database_cut"]``)."""
    from django_ratelimit.core import get_usage

    def usage(increment: bool) -> dict | None:
        return get_usage(None, group=group, key=lambda group, request: key, rate=rate, increment=increment)

    counted = vars(request).setdefault(_COUNTED_TRIES, {}) if request is not None else {}
    limit = (group, key, rate)
    if limit in counted:
        seconds_left, past_it = counted[limit]
        current = usage(increment=False)
        if current is not None and current["time_left"] <= seconds_left:
            return past_it
    current = usage(increment=True)
    if current is None:
        return False
    counted[limit] = (current["time_left"], current["should_limit"])
    return current["should_limit"]


def too_many_attempts() -> OperationError:
    return OperationError(
        gettext("Too many attempts. Please try again in a few minutes."), code="accounts.too_many_attempts", status=429
    )
