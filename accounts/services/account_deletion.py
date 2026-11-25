"""Account → Profile → «Delete account», and what deleting an account does, whoever deletes it."""

import logging

from django.contrib.auth import get_user_model, logout
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from accounts import events, signals
from accounts.queries import account_lookup
from accounts.schemas import ProfileDeletedOut, ProfileDeleteIn
from accounts.services.account_businesses import businesses_holding
from accounts.services.reauthentication import require_recent_authentication

logger = logging.getLogger("accounts.services")


class HoldsBusinesses(Conflict):
    """409 that names the businesses holding the account (``businesses: [{id, name, is_platform}]``), so the panel links
    each one: ``accounts.owns_businesses`` (it owns them) or ``accounts.pays_businesses`` (it pays for them
    after a hand-over: deleting it would leave Stripe charging a card nobody can stop)."""

    def __init__(self, message: str, *, code: str, businesses: list[dict]) -> None:
        super().__init__(message, code=code)
        self.businesses = businesses

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["businesses"] = self.businesses
        return envelope


def _owned_refusal(businesses: list[dict]) -> str:
    """What the owner of ``businesses`` is told: transfer or delete them, but ERPlora's own, which nobody deletes."""
    told = []
    if not all(business["is_platform"] for business in businesses):
        told.append(gettext("You own businesses: transfer or delete them before deleting your account."))
    if any(business["is_platform"] for business in businesses):
        told.append(gettext("You own ERPlora's business: transfer it before deleting your account."))
    return " ".join(told)


def forget_in_outbox(user) -> int:
    """GDPR: the outbox rows whose actor is ``user`` keep its id instead of its email.

    ``live.outbox.record_event`` writes ``str(ctx.actor)``, an account's email, as the actor. The proper fix is
    the actor's id in ``live`` itself; until then, a deleted account's events
    keep no trace of its address. Called in the deletion's transaction, after its own event is recorded.
    """
    from live.models import OutboxEvent

    actor = str(user)[: OutboxEvent._meta.get_field("actor").max_length]
    return OutboxEvent.objects.filter(actor=actor).update(actor=str(user.pk))


def forget_deleted_actor(sender, instance, **kwargs) -> None:
    """``post_delete`` of an account: the audit entries it authored stop pointing at it and keep its
    email (``actor_email``) until ``cleanup_old_logs`` prunes them.

    An entry's author is ``SET_NULL``, but only for the entries there when the deletion was collected: what goes with
    the account, and the account itself, is logged afterwards while the request may still act as it (the admin's
    «Delete» of one's own account), and its commit would fail. Connected after auditlog's own receiver, so the
    account's own entry is covered too. The audit trail is a security record kept 90 days, not erased with the
    account (the outbox, kept for good, keeps the id instead, ``forget_in_outbox``)."""
    from auditlog.models import LogEntry

    LogEntry.objects.filter(actor_id=instance.pk).update(actor=None)


def end_every_session(user) -> int:
    """End every session of ``user`` in the SaaS (``allauth.usersessions``); how many there were."""
    from allauth.usersessions.models import UserSession

    sessions = list(UserSession.objects.filter(user=user))
    for session in sessions:
        session.end()
    return len(sessions)


@operation(
    "accounts.profile.delete",
    kind="command",
    permission="accounts.manage",
    input=ProfileDeleteIn,
    output=ProfileDeletedOut,
    ai=INTERNAL,  # reauthentication
)
def profile_delete(ctx: OperationContext, data: ProfileDeleteIn) -> dict:
    """Delete the signed-in account (GDPR, art. 17; Google Play asks for it in the apps too).

    In this order: no owned business and none it pays for (409, before any password is asked), a recent sign-in
    (401), then, in
    one transaction, every business is asked to end its sessions (``signals``), every session of the SaaS
    ends (the caller's too: the answer signs it out) and the account goes, with what hangs from it.
    """
    user = account_lookup.account_of(ctx)
    owned, paid = businesses_holding(ctx)
    if owned:
        raise HoldsBusinesses(
            _owned_refusal(owned),
            code="accounts.owns_businesses",
            businesses=owned,
        )
    if paid:
        raise HoldsBusinesses(
            gettext(
                "You pay for businesses of other people: ask their owner to enter their own payment details before "
                "deleting your account."
            ),
            code="accounts.pays_businesses",
            businesses=paid,
        )
    require_recent_authentication(ctx)
    _erase_account(ctx, user, request=ctx.request)
    logger.info("accounts.account_deleted user=%s", user.pk)
    return {"deleted": True}


def _erase_account(ctx: OperationContext, user, *, request=None) -> None:
    """What deleting an account does, whoever deletes it: every business is asked to forget it and
    to end its sessions (``signals``), its event goes to its channel, the outbox keeps its id instead of its email, every
    session of the SaaS ends (``request``'s too, signed out) and the account goes with what hangs from it. ERPlora's
    invoices stay: their link to the account is ``SET_NULL`` and they keep their recipient as issued."""
    signals.account_deleting.send(sender=get_user_model(), user_id=user.pk)
    signals.sessions_ended.send(sender=get_user_model(), user_id=user.pk)
    record_event(ctx, events.PROFILE_DELETED)
    forget_in_outbox(user)
    if request is not None:
        logout(request)
    end_every_session(user)
    user.delete()
