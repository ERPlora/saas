"""Ninja routes of fiscal: each route calls exactly one operation and holds no logic.

``GET /api/fiscal/representation?id=<business>``: the state of the business's signed authorisation, for its
owner and admins (``fiscal.representation.status``). The Hub's upload has no route here (``/internal``, signed:
``fiscal.internal``), nor have the staff's decisions (the admin's review page: ``fiscal.admin``).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from fiscal import queries
from fiscal.schemas import RepresentationStatusIn

router = Router(tags=["fiscal"])


@bind(router, "fiscal.representation.status", "/fiscal/representation")
async def representation_status(request, params: Query[RepresentationStatusIn]):
    return await run_operation(request, queries.representation_status, params)
