"""What an account's own changes mean to its businesses (``accounts.signals``, connected in apps.py)."""

from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from hubs import events
from hubs.models import HubMember, HubOwnershipTransfer, SessionRevocation
from hubs.queries import membership
from hubs.services.hub_callbacks import system_ctx_for
from hubs.services.hub_push import bump_state, push_after_commit
from hubs.services.member_management import _take_out
from hubs.services.people_notices import notify_people
from hubs.services.session_revocations import revoke_after_commit


def end_account_sessions(sender, user_id: UUID, **kwargs) -> SessionRevocation:
    """``accounts.signals.sessions_ended``: the account's sessions end in every business too.

    One revocation without a business (the Hub ends them all, its admin's too), queued in the sender's
    transaction and delivered after its COMMIT; ``reconcile_hub_states`` retries it while the Hub is away.
    """
    return revoke_after_commit(user_id)


def account_leaving(sender, user_id: UUID, **kwargs) -> None:
    """``accounts.signals.account_deleting``: the account leaves every business as a removed member does.

    Its pending ownership offers, made or received, are cancelled (one pending offer per business would block
    the owner for 7 days); each membership and invitation goes through ``_take_out`` (access mirror, a newer
    snapshot pushed after the COMMIT), and the owner and admins of every business it answered are told. Its
    sessions end through ``sessions_ended``, which accounts sends next."""
    HubOwnershipTransfer.objects.filter(
        Q(from_user_id=user_id) | Q(to_user_id=user_id), status=HubOwnershipTransfer.Status.PENDING
    ).update(status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now())
    for member in HubMember.objects.select_related("hub").filter(user_id=user_id).order_by("hub_id"):
        _take_out(member)
        if member.accepted_at is not None:
            notify_people(system_ctx_for(member.hub_id), events.MEMBER_CHANGED, member.hub_id)


def account_email_changed(sender, user, **kwargs) -> None:
    """allauth's ``email_changed``: the snapshot's ``members[]`` carries the address."""
    _people_changed(user.pk)


def _people_changed(user_id: UUID) -> None:
    for hub_id in membership.answered_business_ids(user_id):
        bump_state(hub_id)
        push_after_commit(hub_id)
        notify_people(system_ctx_for(hub_id), events.MEMBER_CHANGED, hub_id)
