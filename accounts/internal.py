"""``POST /internal/auth/redeem``: hub-next spends a one-time code (PLAN-SAAS §2.1, §3.1 step 6). ``POST
/internal/support/report``: the Hub's «Report a problem» (its user menu; ACCOUNTS-F38), the panel's report for the
account of the Hub's session.

Server to server, signed with HMAC-SHA256 + timestamp (``accounts.signing``: v2 over method, path and
body when the call carries it, else the body-only v1 hub-next sends today; current or previous secret),
so no CSRF token. Body ``{"code", "hub", "audience"?}``: without ``audience`` it is a member's ``hub-session``
(``<slug>.erplora.com``); ``hub-admin`` is the staff's jump to the Hub's admin at
``hubs.erplora.com`` (ronda 13, PLAN §18), and answers a ``platform_*`` role. Errors answer the
single envelope ``{"error": {"code", "message"}}`` (PLAN §14.1). A plain Django view for phase 1;
the ``/internal`` ninja router comes with block 1.
"""

import json
import logging

import pydantic

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from live.errors import InvalidPayload, OperationError

from accounts import services
from accounts.models import AuthExchangeCode
from accounts.schemas import SupportReportIn
from accounts.signing import verify_request

AUDIENCES = (AuthExchangeCode.HUB_SESSION_AUDIENCE, AuthExchangeCode.HUB_ADMIN_AUDIENCE)

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@csrf_exempt
@never_cache
def redeem(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        response = _error(405, "method_not_allowed", "Only POST is allowed.")
        response["Allow"] = "POST"
        return response
    if not verify_request(request):
        logger.warning("internal.redeem.unauthorized")
        return _error(401, "unauthorized", "Missing, stale or invalid signature.")
    try:
        payload = json.loads(request.body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not all(isinstance(payload.get(key), str) for key in ("code", "hub")):
        return _error(400, "invalid_request", "The body must be a JSON object with the strings code and hub.")
    audience = payload.get("audience", AuthExchangeCode.HUB_SESSION_AUDIENCE)
    if audience not in AUDIENCES:
        return _error(400, "invalid_request", "The audience, if given, must be hub-session or hub-admin.")
    try:
        identity = services.redeem_code(payload["code"], payload["hub"], audience=audience)
    except services.InvalidCode:
        logger.info("internal.redeem.invalid_code hub=%s audience=%s", payload["hub"][:63], audience)
        return _error(400, "invalid_code", "The code is unknown, expired, used or for another hub.")
    return JsonResponse(
        {
            "user_id": identity.user_id,
            "email": identity.email,
            "name": identity.name,
            "locale": identity.locale,
            "role": identity.role,
        }
    )


#: What the Hub's report carries besides what the person wrote: the account of its session, the business and the
#: browser (strings; the screen, ``page``, may be missing).
REPORT_STRINGS = ("account", "hub", "hub_id", "subject", "description")


@csrf_exempt
@never_cache
def support_report(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        response = _error(405, "method_not_allowed", "Only POST is allowed.")
        response["Allow"] = "POST"
        return response
    if not verify_request(request):
        logger.warning("internal.support_report.unauthorized")
        return _error(401, "unauthorized", "Missing, stale or invalid signature.")
    try:
        payload = json.loads(request.body)
    except ValueError:
        payload = None
    if (
        not isinstance(payload, dict)
        or not all(isinstance(payload.get(key), str) for key in REPORT_STRINGS)
        or not all(isinstance(payload.get(key, ""), str | None) for key in ("page", "browser"))
    ):
        return _error(400, "invalid_request", "The body must be a JSON object with the strings " + ", ".join(REPORT_STRINGS) + ".")
    try:
        data = SupportReportIn.model_validate(
            {key: payload.get(key) for key in ("subject", "description", "page")}
        )
    except pydantic.ValidationError as exc:
        fields = {}
        for error in exc.errors():
            fields.setdefault(str(error["loc"][0]) if error["loc"] else "__all__", error["msg"].removeprefix("Value error, "))
        failure = InvalidPayload("Invalid report.", fields=fields)
        return JsonResponse(failure.envelope(), status=failure.status)
    try:
        sent = services.support_report_from_hub(
            payload["account"],
            hub=payload["hub"],
            hub_id=payload["hub_id"],
            data=data,
            browser=payload.get("browser") or "",
        )
    except OperationError as exc:
        logger.info("internal.support_report.refused code=%s hub=%s", exc.code, payload["hub"][:63])
        return JsonResponse(exc.envelope(), status=exc.status)
    return JsonResponse(sent)
