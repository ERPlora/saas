"""Account → Security → Two-factor authentication: the trusted browsers."""

import logging

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from accounts import events
from accounts.queries import account_lookup
from accounts.schemas import BrowserTrustOut, BrowserTrustRevokeIn

logger = logging.getLogger("accounts.services")


def forget_trusted_browsers(user) -> dict[int, int]:
    """End the trust of every browser of ``user``: their next sign-in asks for the app's code again.

    allauth keeps no record of the browsers an account trusted: each one carries a signed fingerprint of the
    account's password and of every authenticator's id, type and seed (``allauth.mfa.internal.flows.trust``), so
    the only way to end them is to move one of those. The authenticators get new ids with the same type, data and
    dates: the app keeps its secret and the recovery codes written down keep working, and nobody sets anything up
    again. Returns the new id of each old one.
    """
    from allauth.mfa.models import Authenticator

    rows = list(Authenticator.objects.select_for_update().filter(user=user).order_by("pk"))
    if not rows:
        return {}
    Authenticator.objects.filter(pk__in=[row.pk for row in rows]).delete()
    fresh = Authenticator.objects.bulk_create(
        Authenticator(user=user, type=row.type, data=row.data, created_at=row.created_at, last_used_at=row.last_used_at)
        for row in rows
    )
    logger.info("accounts.browser_trust_revoked user=%s authenticators=%s", user.pk, len(rows))
    return {row.pk: new.pk for row, new in zip(rows, fresh, strict=True)}


def _follow_new_authenticator_ids(request, renamed: dict[int, int]) -> None:
    """The codes this session gave name the authenticators by id (allauth's records, ``mfa.mfa_completed``): they
    follow the new ids, so this browser keeps what it proved. The other sessions' records name ids that are gone:
    a browser that signed in on its trust gives the code again to jump to a business."""
    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY

    session = getattr(request, "session", None)
    if session is None or not renamed:
        return
    records = session.get(AUTHENTICATION_METHODS_SESSION_KEY, [])
    if any(record.get("method") == "mfa" and record.get("id") in renamed for record in records):
        session[AUTHENTICATION_METHODS_SESSION_KEY] = [
            {**record, "id": renamed[record["id"]]}
            if record.get("method") == "mfa" and record.get("id") in renamed
            else record
            for record in records
        ]


@operation(
    "accounts.browser_trust.revoke",
    kind="command",
    permission="accounts.manage",
    input=BrowserTrustRevokeIn,
    output=BrowserTrustOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Stops trusting every browser for two-factor authentication, this one included.",
        asks={
            "en": (
                "stop trusting my browsers",
                "ask me for the 2FA code everywhere again",
                "forget the trusted devices",
            ),
            "es": (
                "deja de confiar en mis navegadores",
                "que me vuelva a pedir el código de verificación en todos lados",
                "olvida los navegadores de confianza",
            ),
        },
    ),
)
def browser_trust_revoke(ctx: OperationContext, data: BrowserTrustRevokeIn) -> dict:
    """«Stop trusting all browsers» (Security → Two-factor authentication): as Google's and Microsoft's
    «Revoke all trusted devices». This browser too: the answer says it is no longer trusted."""
    user = account_lookup.account_of(ctx)
    renamed = forget_trusted_browsers(user)
    record_event(ctx, events.BROWSER_TRUST_REVOKED)
    # Last, once nothing is left to write: a try a cut rolls back must leave the session naming the ids the database
    # keeps, so the try after it renames from them (``repeatable``).
    _follow_new_authenticator_ids(ctx.request, renamed)
    return {"trusted_until": None}
