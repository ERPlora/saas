"""«Report a problem», from the panel and from the Hub's user menu."""

import logging

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import OperationError
from live.operations import INTERNAL, operation

from accounts import emails
from accounts.queries import account_hubs, account_lookup
from accounts.schemas import SupportReportIn, SupportReportOut
from accounts.services.attempt_limits import too_many_attempts

logger = logging.getLogger("accounts.services")


#: Characters of the browser a report keeps: a user agent is one line, rarely over 300.
REPORT_BROWSER_MAX = 300


def _one_line(value: str) -> str:
    """``value`` on one line: a mail header carries one, and a break typed in it would add another (``Bcc:``)."""
    return " ".join(value.split())


#: Where a report comes from, in its mail: the panel's page or the Hub's user menu.
REPORT_FROM_PANEL = "Panel"
REPORT_FROM_HUB = "Hub"


@operation(
    "accounts.support.report",
    kind="command",
    permission="accounts.manage",
    input=SupportReportIn,
    output=SupportReportOut,
    ai=INTERNAL,  # dialog
)
def support_report(ctx: OperationContext, data: SupportReportIn) -> dict:
    """«Report a problem»: mail the support mailbox what the person wrote, with the
    account, its businesses, the page it came from and its browser, «Reply-To» the account (:func:`send_support_report`)."""
    browser = ctx.request.headers.get("User-Agent", "") if ctx.request is not None else ""
    return send_support_report(account_lookup.account_of(ctx), data, browser=browser, source=REPORT_FROM_PANEL)


class UnknownAccount(OperationError):
    status = 404
    code = "accounts.unknown_account"


class NotAMember(OperationError):
    status = 403
    code = "accounts.not_a_member"


def support_report_from_hub(account: str, *, hub: str, hub_id: str, data: SupportReportIn, browser: str) -> dict:
    """The Hub's «Report a problem» (its user menu, ``POST /internal/support/report``): the panel's report for the
    ``account`` of the Hub's session, from the business ``hub`` (its slug and id). An account that does not exist or
    is off is :class:`UnknownAccount`; one that is no member of that business, :class:`NotAMember`: no mail."""
    user = account_lookup.active_account(account)
    if user is None:
        raise UnknownAccount(gettext("That account does not exist."))
    if hub not in account_hubs.hub_roles_of(user):
        raise NotAMember(gettext("That account is not a member of that business."))
    return send_support_report(user, data, browser=browser, source=REPORT_FROM_HUB, business=f"{hub} ({hub_id})")


def send_support_report(user, data: SupportReportIn, *, browser: str, source: str, business: str | None = None) -> dict:
    """Mail the support mailbox ``user``'s report, «Reply-To» the account, with what goes with it: the account, its
    businesses, where it comes from (``source``, and the ``business`` of the Hub it was sent from), the page and the
    browser. One path for the panel and the Hub. Limited per account (``SUPPORT_REPORT_RATELIMIT``, as the contact
    form per address, whichever sends it); nothing is kept and no issue is opened."""
    from django_ratelimit.core import is_ratelimited

    if is_ratelimited(
        None,
        group="accounts.support.report",
        key=lambda group, request: f"user:{user.pk}",
        rate=settings.SUPPORT_REPORT_RATELIMIT,
        increment=True,
    ):
        raise too_many_attempts()
    context = [
        ("Account", f"{user.email} ({user.pk})"),
        ("Language", user.language),
        (
            "Businesses",
            ", ".join(f"{slug} ({role})" for slug, role in account_hubs.hub_roles_of(user).items()) or "none",
        ),
        ("From", source),
        *([("Business", _one_line(business))] if business else []),
        ("Page", _one_line(data.page or "") or "unknown"),
        ("Browser", _one_line(browser)[:REPORT_BROWSER_MAX] or "unknown"),
        ("Sent", timezone.now().isoformat(timespec="seconds")),
    ]
    if not emails.send_support_report(user, subject=_one_line(data.subject), description=data.description, context=context):
        raise OperationError(
            gettext("We could not send your report. Write to us directly at %(email)s.") % {"email": settings.SUPPORT_EMAIL},
            code="accounts.report_not_sent",
            status=503,
        )
    logger.info("accounts.support_report_sent user=%s from=%s", user.pk, source)
    return {"reply_to": user.email}
