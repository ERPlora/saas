"""The daily renewal of Meta's permission: exchange → record → the owner's mail."""

import logging
from datetime import timedelta

from django.utils import timezone

from whatsapp import emails, meta, queries
from whatsapp.schemas import AlertedIn, RenewalDueIn, RenewalIn
from whatsapp.services import phone_numbers, platform_actor

logger = logging.getLogger("whatsapp.gateway")

#: A number with less than this left and still not renewed after the round is an error in the log.
ALARM = timedelta(days=7)


def renew_tokens() -> dict[str, int]:
    """Renew every permission due. With none due the round is empty and asks for nothing; with one due,
    ``NotConfigured`` (Meta's app not set) before Meta is asked or anything is written."""
    ctx = platform_actor.platform_context()
    due = queries.renewal_due(ctx, RenewalDueIn()).numbers
    counts = {"due": len(due), "renewed": 0, "needs_reconnect": 0, "unverified": 0, "alerted": 0, "failed": 0}
    if due:
        meta.app_credentials()
    running_out = 0
    for number in due:
        try:
            outcome, token, expires_at = _renew(number.token.get_secret_value())
            out = phone_numbers.number_renewal(
                ctx, RenewalIn(number_id=number.id, outcome=outcome, token=token, expires_at=expires_at)
            )
        except Exception:  # noqa: BLE001 - one number's surprise never stops the others; tomorrow tries again
            logger.exception("whatsapp.token.renewal_crashed number_id=%s", number.id)
            counts["failed"] += 1
            outcome, out = "failed", None
        else:
            counts["needs_reconnect" if out.needs_reconnect else outcome] += 1
            if out.alert is not None and emails.send_reconnect(**out.alert.model_dump()):
                phone_numbers.number_alerted(ctx, AlertedIn(number_id=number.id))
                counts["alerted"] += 1
        if outcome != "renewed" and number.expires_at <= timezone.now() + ALARM:
            running_out += 1
    if running_out:
        logger.error("whatsapp.token.running_out numbers=%s days_left_under=%s", running_out, ALARM.days)
    return counts


def _renew(token: str) -> tuple[str, str | None, object]:
    """Meta's exchange of ``token``: ``("renewed", fresh, deadline)``, ``("refused", …)`` when Meta said no, or
    ``("unverified", …)`` without a verdict (not reached, throttled, an answer without a token)."""
    try:
        answer = meta.exchange_token(token)
    except meta.MetaRefused as refused:
        logger.warning("whatsapp.token.refused meta_status=%s meta_code=%s", refused.status, refused.code)
        return ("unverified" if refused.rate_limited else "refused"), None, None
    except meta.MetaUnreachable:
        return "unverified", None, None
    fresh = str(answer.get("access_token") or "")
    if not fresh:
        logger.warning("whatsapp.token.no_token_in_answer")
        return "unverified", None, None
    try:
        expires_at = meta.token_expiry(fresh)
    except (meta.MetaRefused, meta.MetaUnreachable):
        seconds = answer.get("expires_in")
        expires_at = timezone.now() + timedelta(seconds=int(seconds)) if isinstance(seconds, int) and seconds > 0 else None
    return "renewed", fresh, expires_at
