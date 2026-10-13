"""Read operations of the public web.

``public.app.release``: which version of the installable app we publish (``GET
/api/v1/app/release/``, PLAN-SAAS §6). No permission: the installed app asks through its hub's
runtime, anonymously, so that a hub in demo, not yet enrolled or just woken up can still tell its
till (a 401 would read as «nothing new», hub#400). It does not touch the ORM: the version is the
manifest the hub's release writes next to the installers, read by ``public.appdist``.
"""

import time
from typing import Any

from live.context import OperationContext
from live.operations import operation

from public import appdist
from public.schemas import AppReleaseIn, AppReleaseOut


@operation(
    "public.app.release",
    kind="query",
    permission=None,
    input=AppReleaseIn,
    output=AppReleaseOut,
)
def app_release(ctx: OperationContext, data: AppReleaseIn) -> dict[str, Any]:
    """``{"version": str | None}``: ``None`` whenever the bucket could not tell, never a guess."""
    bucket = int(time.time() // appdist.RELEASE_CACHE_TTL)
    return {"version": appdist.published_release(bucket)}
