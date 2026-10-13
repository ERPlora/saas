"""Ninja routes of the public web: each route calls exactly one operation and holds no logic.

``GET /api/v1/app/release/`` keeps the address and the answer of the old view (``appdist_api``):
the installed app's runtime asks it, anonymously (``auth=None``).
"""

from live.ninja import bind, run_operation
from ninja import Router

from public import queries

router = Router(tags=["public"])


@bind(router, "public.app.release", "/v1/app/release/", auth=None)
async def app_release(request):
    return await run_operation(request, queries.app_release)
