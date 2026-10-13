"""Ninja routes of apps: each route calls exactly one operation and holds no logic.

The public catalog (spec §5.1 and §8.2), for the panel's SPA: open to anonymous visitors
(``auth=None``), with the input in the query string. No path parameters: the app's ``id`` travels
in the input, because a route takes one parameter, the operation's input (as demo's).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps import queries
from apps.schemas import AppByIdIn, AppListIn

router = Router(tags=["apps"])


@bind(router, "apps.app.list", "/apps", auth=None)
async def app_list(request, params: Query[AppListIn]):
    return await run_operation(request, queries.app_list, params)


@bind(router, "apps.app.get", "/apps/get", auth=None)
async def app_get(request, params: Query[AppByIdIn]):
    return await run_operation(request, queries.app_get, params)


@bind(router, "apps.app.doc", "/apps/doc", auth=None)
async def app_doc(request, params: Query[AppByIdIn]):
    return await run_operation(request, queries.app_doc, params)


@bind(router, "apps.app.sitemap", "/apps/sitemap", auth=None)
async def app_sitemap(request):
    return await run_operation(request, queries.app_sitemap)
