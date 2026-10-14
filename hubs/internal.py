"""``POST /internal/hubs/{id}/ready``: hub-next reports a business's database ready (PLAN-SAAS §3.1 step 3;
round 17 §2.14: the provisioning callback takes this route).

Server to server, signed as ``/internal/auth/redeem`` (``accounts.signing.verify_request``: HMAC-SHA256 +
timestamp, current or previous secret), so no CSRF token. The body is ``{"id": "<the hub of the path>"}``:
v1, which hub-next signs today, covers the body only, so an empty body or one naming another hub is
refused (v2 also signs the path; the check stays until v1 is dropped). It runs
``hubs.business.mark_ready`` as the platform, in the owner's channel. Errors answer the single envelope
``{"error": {"code", "message"}}`` (PLAN §14.1). A plain Django view, like the redeem, until the
``/internal`` ninja API (``config/internal_api.py``, lot L0-F) takes both.
"""

import json
import logging
from uuid import UUID

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from live.errors import OperationError

from accounts.signing import verify_request
from hubs import services
from hubs.schemas import MarkReadyIn

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@csrf_exempt
@never_cache
def ready(request: HttpRequest, hub_id: UUID) -> JsonResponse:
    if request.method != "POST":
        response = _error(405, "method_not_allowed", "Only POST is allowed.")
        response["Allow"] = "POST"
        return response
    if not verify_request(request):
        logger.warning("internal.hub_ready.unauthorized hub=%s", hub_id)
        return _error(401, "unauthorized", "Missing, stale or invalid signature.")
    try:
        payload = json.loads(request.body)
    except ValueError:
        payload = None
    # The signature covers the body only: the body names the hub, and it must be the one of the path.
    if not isinstance(payload, dict) or payload.get("id") != str(hub_id):
        return _error(400, "invalid_request", "The body must be {\"id\": the hub of the path}.")
    try:
        result = services.business_mark_ready(
            services.system_ctx_for(hub_id), MarkReadyIn(id=hub_id)
        )
    except OperationError as refused:
        return JsonResponse(refused.envelope(), status=refused.status)
    logger.info("internal.hub_ready hub=%s status=%s", hub_id, result.status)
    return JsonResponse(result.model_dump(mode="json"))
