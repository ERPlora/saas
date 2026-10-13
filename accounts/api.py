"""Ninja routes of accounts: each route calls exactly one operation and holds no logic.

Sign-in is not here: it is allauth.headless's API at ``/_allauth/`` (and Google at its own paths).
"""

from live.ninja import bind, run_operation
from ninja import Router

from accounts import queries

router = Router(tags=["accounts"])


# Session auth (the API's default): an anonymous visitor gets the 401 envelope.
@bind(router, "accounts.hub.list", "/accounts/hubs")
async def hub_list(request):
    return await run_operation(request, queries.hub_list)
