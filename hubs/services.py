"""Write operations of hubs, and the push of what the SaaS knows to the Hub service.

One operation = one transaction (``@operation``), with its event in the outbox. Who may write is
decided by the account's ``HubMember`` role (``queries.access``, round 17 §2.7). Every change the Hub
must learn is written in the same transaction (``Hub.pending_hub_call``, ``Hub.state_version``) and
pushed after the COMMIT (``sync_hub``, which never runs inside a transaction); when the Hub is away it
stays owed and ``manage.py reconcile_hub_states`` retries it (plan 2026-10-13 §3, the push to the Hub).

Until the jump to a hub moves to ``hubs`` (plan, L1-A step 2), ``accounts.services.issue_code`` and
``redeem_code`` check an account's access in ``accounts.HubMembership``: ``sync_access`` keeps those rows
equal to the answered members of each business, in the same transaction.
"""

import logging
import re
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import operation
from live.outbox import record_event
from live.slugs import (
    HUB_SLUG_MAX_LENGTH,
    INVALID_FORMAT,
    PUNYCODE,
    RESERVED,
    TOO_LONG,
    TOO_SHORT,
    hub_slug_min_length,
    validate_hub_slug,
)

from accounts import services as account_services
from accounts.queries import hub_start_url
from accounts.models import HubMembership
from hubs import emails, events, hub_client, queries
from hubs.queries import expired_deletions
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import (
    BillingProfile,
    Hub,
    HubMember,
    HubOwnershipTransfer,
    Subscription,
    SubscriptionItem,
)
from hubs.schemas import (
    BillingProfileIn,
    BillingProfileOut,
    BusinessCreateIn,
    BusinessDeleteIn,
    BusinessDetailOut,
    BusinessOpenIn,
    BusinessOpenOut,
    BusinessRowOut,
    BusinessUpdateIn,
    ByIdIn,
    HubErrorIn,
    HubStatusOut,
    MarkReadyIn,
    MemberInviteIn,
    MemberRoleIn,
    MemberRowOut,
    OwnershipTransferIn,
    OwnershipTransferOut,
    RemovedOut,
)

logger = logging.getLogger(__name__)

Role = HubMember.Role
Call = Hub.HubCall

#: The time zone a business starts with, by country (the capital's); the owner may change it.
TIME_ZONES = {
    "AT": "Europe/Vienna",
    "BE": "Europe/Brussels",
    "BG": "Europe/Sofia",
    "HR": "Europe/Zagreb",
    "CY": "Asia/Nicosia",
    "CZ": "Europe/Prague",
    "DK": "Europe/Copenhagen",
    "EE": "Europe/Tallinn",
    "FI": "Europe/Helsinki",
    "FR": "Europe/Paris",
    "DE": "Europe/Berlin",
    "GR": "Europe/Athens",
    "HU": "Europe/Budapest",
    "IE": "Europe/Dublin",
    "IT": "Europe/Rome",
    "LV": "Europe/Riga",
    "LT": "Europe/Vilnius",
    "LU": "Europe/Luxembourg",
    "MT": "Europe/Malta",
    "NL": "Europe/Amsterdam",
    "PL": "Europe/Warsaw",
    "PT": "Europe/Lisbon",
    "RO": "Europe/Bucharest",
    "SK": "Europe/Bratislava",
    "SI": "Europe/Ljubljana",
    "ES": "Europe/Madrid",
    "SE": "Europe/Stockholm",
}
#: A derived address tried this many times when two sign-ups race for it.
SLUG_ATTEMPTS = 20


def business_deleted() -> Conflict:
    return Conflict(_("This business was deleted."), code="hubs.business_deleted")


class SeatLimitReached(Conflict):
    """409 ``hubs.seat_limit``: the plan has no seat for one more person (saas#2022).

    Its envelope also says how many people the plan covers (``limit``) and how many seats are taken
    (``used``, as ``hubs.member.list`` counts them), so the panel offers the plan change with the
    numbers instead of parsing the message.
    """

    def __init__(self, message: str, *, limit: int, used: int) -> None:
        super().__init__(message, code="hubs.seat_limit")
        self.limit = limit
        self.used = used

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(limit=self.limit, used=self.used)
        return envelope


# --- Creating a business --------------------------------------------------------------------------


@operation(
    "hubs.business.create",
    kind="command",
    permission="hubs.manage",
    input=BusinessCreateIn,
    output=BusinessDetailOut,
)
def business_create(ctx: OperationContext, data: BusinessCreateIn) -> dict:
    """The sign-up (PLAN-SAAS §3.1 step 2, round 17 §2.3): in one transaction the payer, the business, its
    owner and its Free subscription (with the Starter trial, ADR-0474); after the COMMIT, the Hub.

    One free business per account (``FREE_HUBS_PER_ACCOUNT``, ADR-0154); a name never blocks it.
    """
    user = queries.account_of(ctx)
    plan = queries.free_plan()
    if plan is None:
        raise OperationError(
            _("Businesses cannot be created right now. Try again in a few minutes."),
            code="hubs.free_plan_missing",
            status=503,
        )
    if user.is_staff:
        raise Conflict(
            _("This address belongs to ERPlora's staff and cannot join a business."), code="hubs.platform_account"
        )
    check_free_quota(user)
    now = timezone.now()
    profile = BillingProfile.objects.create(
        owner=user, billing_email=user.email, billing_country=data.country
    )
    hub = _create_hub(
        data, user, profile, queries.business_type_for(data.business_type), now
    )
    owner = HubMember.objects.create(
        hub=hub, user=user, role=Role.OWNER, joined_at=now, accepted_at=now
    )
    _subscribe_to_free(hub, plan, now)
    sync_access(hub)
    record_event(ctx, events.BUSINESS_CREATED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    return queries.business_detail(owner)


def check_free_quota(user, excluding: UUID | None = None) -> None:
    """One more Free business fits ``user``'s quota (``FREE_HUBS_PER_ACCOUNT``, ADR-0154).

    The account's row is locked first: two requests of one account (two tabs, a double click) are
    serialised here, so the second counts the business the first is creating.
    """
    get_user_model().objects.select_for_update().filter(pk=user.pk).first()
    if queries.free_hubs_owned(user, excluding=excluding) >= getattr(settings, "FREE_HUBS_PER_ACCOUNT", 1):
        raise Conflict(
            _("You already have a free business. Change its plan to create another one."),
            code="hubs.free_hub_limit",
        )


def _create_hub(
    data: BusinessCreateIn, user, profile: BillingProfile, business_type, now
) -> Hub:
    fields = {
        "name": data.name,
        "country": data.country,
        "timezone": TIME_ZONES.get(data.country, "Europe/Madrid"),
        "language": user.language,
        "business_type": business_type,
        "billing_profile": profile,
        "status": Hub.Status.PREPARING,
        "provision_requested_at": now,
        "pending_hub_call": Call.PUT,
    }
    if data.slug is not None:
        slug = _chosen_slug(data.slug)
        try:
            with transaction.atomic():
                return Hub.objects.create(slug=slug, **fields)
        except IntegrityError:
            raise _slug_taken() from None
    for _attempt in range(SLUG_ATTEMPTS):
        try:
            with transaction.atomic():
                return Hub.objects.create(slug=queries.free_slug(data.name), **fields)
        except IntegrityError:
            continue  # another sign-up took it between the read and the write: the next one is free
    raise _slug_taken()


#: Why a chosen address is refused, by the code of ``live.slugs.validate_hub_slug``.
SLUG_PROBLEMS = {
    INVALID_FORMAT: gettext_lazy(
        "Use only lowercase letters, digits and hyphens, without a hyphen at the start or the end."
    ),
    TOO_SHORT: gettext_lazy("Use at least %(min)d characters."),
    TOO_LONG: gettext_lazy("Use at most %(max)d characters."),
    PUNYCODE: gettext_lazy("The address cannot start with “xn--”."),
}


def _chosen_slug(slug: str) -> str:
    try:
        validate_hub_slug(slug)
    except ValueError as refused:
        code = str(refused)
        if code == RESERVED:
            raise Conflict(_("This address is reserved. Choose another one."), code="hubs.slug_reserved") from None
        message = str(SLUG_PROBLEMS.get(code, SLUG_PROBLEMS[INVALID_FORMAT])) % {
            "min": hub_slug_min_length(),
            "max": HUB_SLUG_MAX_LENGTH,
        }
        raise InvalidPayload(_("Invalid payload"), fields={"slug": message}) from None
    if slug == account_services.PLATFORM_HOST_SLUG:
        raise Conflict(_("This address is reserved. Choose another one."), code="hubs.slug_reserved")
    if queries.slug_taken(slug):
        raise _slug_taken()
    return slug


def _slug_taken() -> Conflict:
    return Conflict(
        _("This address is taken. Choose another one."), code="hubs.slug_taken"
    )


def _subscribe_to_free(hub: Hub, plan, now) -> Subscription:
    trial = queries.trial_plan()
    if trial is None:
        return Subscription.objects.create(
            hub=hub,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
        )
    return Subscription.objects.create(
        hub=hub,
        plan=plan,
        trial_plan=trial,
        status=Subscription.Status.TRIALING,
        current_period_start=now,
        trial_start=now,
        trial_end=now + timedelta(days=trial.trial_period_days),
    )


# --- Settings, deletion and recovery --------------------------------------------------------------


@operation(
    "hubs.business.update",
    kind="command",
    permission="hubs.manage",
    input=BusinessUpdateIn,
    output=BusinessDetailOut,
)
def business_update(ctx: OperationContext, data: BusinessUpdateIn) -> dict:
    """Name, country, language and time zone (the Settings tab): the owner and the administrators. The
    country is read-only once the business is ready (``queries.country_locked``): a change is the 409
    ``hubs.country_locked``; sending the same one again is no change."""
    member = queries.access(queries.account_of(ctx), data.id, Role.ADMIN, lock=True)
    hub = member.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
    changes = {
        field: value for field, value in sent.items() if getattr(hub, field) != value
    }
    if "country" in changes and queries.country_locked(hub):
        raise Conflict(
            _("The country cannot change once the business is ready: its invoices belong to one country."),
            code="hubs.country_locked",
        )
    if changes:
        for field, value in changes.items():
            setattr(hub, field, value)
        hub.pending_hub_call = hub.pending_hub_call or Call.PUT
        hub.registry_version = F("registry_version") + 1
        hub.save(update_fields=[*changes, "pending_hub_call", "registry_version", "updated_at"])
        record_event(ctx, events.BUSINESS_UPDATED, {"id": str(hub.id)})
        push_after_commit(hub.id)
    return queries.business_detail(member)


@operation(
    "hubs.business.delete",
    kind="command",
    permission="hubs.manage",
    input=BusinessDeleteIn,
    output=BusinessDetailOut,
)
def business_delete(ctx: OperationContext, data: BusinessDeleteIn) -> dict:
    """The owner deletes the business (PLAN-SAAS §3.4, round 17 §2.11): it stops opening at once, the
    Hub keeps it 90 days, and the plan goes back to Free on the spot (it comes back on Free)."""
    member = queries.access(queries.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.confirm_name.strip().casefold() != hub.name.strip().casefold():
        raise InvalidPayload(
            _("Invalid payload"),
            fields={"confirm_name": _("Type the name of the business to delete it.")},
        )
    hub.status = Hub.Status.DELETING
    hub.deletion_requested_at = timezone.now()
    hub.pending_hub_call = Call.DELETE
    hub.save(
        update_fields=[
            "status",
            "deletion_requested_at",
            "pending_hub_call",
            "updated_at",
        ]
    )
    _back_to_free(hub)
    SubscriptionItem.objects.filter(subscription__hub=hub, source=SubscriptionItem.Source.PLAN).delete()
    HubOwnershipTransfer.objects.filter(
        hub=hub, status=HubOwnershipTransfer.Status.PENDING
    ).update(status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now())
    sync_access(hub)
    record_event(ctx, events.BUSINESS_DELETED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    transaction.on_commit(
        partial(
            emails.send_deletion,
            hub,
            member.user,
            base_url=emails.base_url(ctx.request),
        ),
        robust=True,
    )
    return queries.business_detail(member)


def _back_to_free(hub: Hub) -> None:
    plan = queries.free_plan()
    if plan is None:
        return
    Subscription.objects.filter(hub=hub).update(
        plan=plan,
        trial_plan=None,
        trial_end=None,
        status=Subscription.Status.ACTIVE,
        cancel_at_period_end=False,
        updated_at=timezone.now(),
    )


@operation(
    "hubs.business.restore",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=BusinessDetailOut,
)
def business_restore(ctx: OperationContext, data: ByIdIn) -> dict:
    """The owner recovers a deleted business within its 90 days (round 17 §2.11), on Free."""
    member = queries.access(queries.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    if hub.status != Hub.Status.DELETING:
        raise Conflict(
            _("This business is not deleted."), code="hubs.business_not_deleted"
        )
    if hub.purge_after <= timezone.now():
        raise Conflict(
            _("This business was erased for good and cannot be recovered."),
            code="hubs.business_purged",
        )
    check_free_quota(member.user, excluding=hub.id)  # it comes back on Free
    hub.status = Hub.Status.ACTIVE if hub.ready_at else Hub.Status.PREPARING
    hub.deletion_requested_at = None
    # A deletion the Hub never got leaves nothing to restore there: only the (idempotent) registry.
    hub.pending_hub_call = Call.PUT if hub.pending_hub_call == Call.DELETE else Call.RESTORE
    hub.state_version = F("state_version") + 1
    hub.save(
        update_fields=[
            "status",
            "deletion_requested_at",
            "pending_hub_call",
            "state_version",
            "updated_at",
        ]
    )
    hub.refresh_from_db()
    sync_access(hub)
    record_event(ctx, events.BUSINESS_RESTORED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    return queries.business_detail(member)


# --- Entering -------------------------------------------------------------------------------------

#: Why a business does not open, by status (round 17 §2.2: a business with a payment pending still opens).
NOT_OPENING = {
    Hub.Status.PREPARING: ("hubs.business_preparing", gettext_lazy("This business is still being prepared.")),
    Hub.Status.SUSPENDED: (
        "hubs.business_suspended",
        gettext_lazy("This business is suspended until its payment is settled."),
    ),
    Hub.Status.DELETING: ("hubs.business_deleted", gettext_lazy("This business was deleted.")),
}


@operation(
    "hubs.business.open",
    kind="command",
    permission="hubs.manage",
    input=BusinessOpenIn,
    output=BusinessOpenOut,
)
def business_open(ctx: OperationContext, data: BusinessOpenIn) -> dict:
    """«Open» (PLAN-SAAS §3.1 step 5), for every role: the Hub's start of the jump, ``url``.

    No code is minted here any more: the Hub binds the jump to the browser with a ``state`` of its own,
    so it starts at its ``/auth/login?next=``, which bounces to ``/hub-login/``; that door mints the
    code (and asks for the second factor of an account that has one). This checks the member and the
    business, and remembers it as the last opened (the launcher lists it first).
    """
    member = queries.access(queries.account_of(ctx), data.id)
    hub = member.hub
    if hub.status in NOT_OPENING:
        code, message = NOT_OPENING[hub.status]
        raise Conflict(str(message), code=code)
    HubMember.objects.filter(pk=member.pk).update(last_opened_at=timezone.now())
    record_event(ctx, events.BUSINESS_OPENED, {"id": str(hub.id)})
    return {"url": hub_start_url(hub.slug, data.next)}


# --- The Hub's callback ---------------------------------------------------------------------------


def system_ctx_for(hub_id: UUID) -> OperationContext:
    """The platform acting on a business, in its owner's channel (its live lists re-run, plan §3)."""
    owner = queries.owner_id(hub_id)
    return system_context(Scope("user", str(owner) if owner else "system"))


@operation(
    "hubs.business.mark_ready",
    kind="command",
    permission="hubs.manage",
    input=MarkReadyIn,
    output=HubStatusOut,
)
def business_mark_ready(ctx: OperationContext, data: MarkReadyIn) -> dict:
    """The Hub's ``POST /internal/hubs/{id}/ready``: the business's database is ready (§3.1 step 3).

    Only the platform calls it (``hubs.internal``). A business being prepared becomes active; one that
    was suspended or deleted meanwhile keeps its status. Idempotent.
    """
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the Hub reports a business ready."), code="internal_command"
        )
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise queries.not_found()
    changed = []
    if hub.ready_at is None:
        hub.ready_at = timezone.now()
        changed.append("ready_at")
    if hub.status == Hub.Status.PREPARING:
        hub.status = Hub.Status.ACTIVE
        changed.append("status")
    if changed:
        hub.save(update_fields=[*changed, "updated_at"])
        record_event(ctx, events.BUSINESS_READY, {"id": str(hub.id)})
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


@operation(
    "hubs.business.record_hub_error",
    kind="command",
    permission="hubs.manage",
    input=HubErrorIn,
    output=HubStatusOut,
)
def business_record_hub_error(ctx: OperationContext, data: HubErrorIn) -> dict:
    """The Hub's last refusal of a call about the business (its error code), or ``None`` once a call
    succeeds; only the push writes it (``sync_outcome``, after a COMMIT or in ``saas-cron``).

    A command, so the change has its event: on the owner's channel (``system_ctx_for``, as the Hub's
    ``ready``) the list and the page of the business re-run at once, and «Preparing» turns into «Error»
    (and back) without waiting for the 300 s safety re-run. The same answer again records nothing.
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform records the Hub's answers."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise queries.not_found()
    code = data.hub_error or ""
    if hub.last_hub_error != code:
        hub.last_hub_error = code
        hub.hub_error_at = timezone.now() if code else None
        hub.save(update_fields=["last_hub_error", "hub_error_at", "updated_at"])
        record_event(ctx, events.BUSINESS_HUB_ERROR_CHANGED, {"id": str(hub.id), "hub_error": code or None})
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


# --- Members and invitations ----------------------------------------------------------------------


def _member_not_found() -> NotFound:
    return NotFound(_("This member does not exist or you have no access to it."))


def _managed(ctx: OperationContext, member_id: UUID, role: str | None = None) -> tuple[HubMember, HubMember]:
    """``(actor, target)`` for a write on the member ``member_id``, both locked after their hub's row.

    The actor must be an admin or the owner of the target's business (404 otherwise, 403 below
    admin), never act on itself nor on a peer or a superior, and never hand out its own rank or more.
    """
    user = queries.account_of(ctx)
    hub_id = HubMember.objects.filter(pk=member_id).values_list("hub_id", flat=True).first()
    if hub_id is None:
        raise _member_not_found()
    actor = queries.access(user, hub_id, Role.ADMIN, lock=True)
    if actor.hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    target = (
        HubMember.objects.select_for_update(of=("self",))
        .select_related("hub", "user", "invited_by")
        .filter(pk=member_id)
        .first()
    )
    if target is None:
        raise _member_not_found()
    if target.user_id == actor.user_id:
        raise PermissionDenied(_("You cannot change your own membership."))
    if not queries.manages(actor, target):
        raise PermissionDenied(_("You cannot manage a member whose role is equal to or above yours."))
    if role is not None and role not in queries.assignable_roles(actor.role):
        raise PermissionDenied(_("You cannot hand out a role equal to or above yours."))
    return actor, target


def _check_seat(hub: Hub, now) -> None:
    """The plan covers one more person (saas#2022), checked where the seat is spent: inviting (a live
    invitation holds its seat), and renewing an invitation that had expired."""
    seats = queries.seats_of(hub, now)
    if seats["limit"] is not None and seats["used"] >= seats["limit"]:
        raise SeatLimitReached(
            _("This plan covers %(cap)s people and they are all taken.") % {"cap": seats["limit"]},
            limit=seats["limit"],
            used=seats["used"],
        )


def _check_seat_to_enter(hub: Hub, now) -> None:
    """The plan still has a seat beside the people already inside: an invitation sent while nothing
    capped it (the Starter trial) and answered once the plan covers fewer people is first come, first
    served. Within the cap it always passes, because the invitation already holds its seat."""
    limit = queries.seat_limit_of(hub, now)
    if limit is not None and queries.people_inside(hub) >= limit:
        raise SeatLimitReached(
            _("This business has no seat left on its plan. Ask whoever invited you to free one or to change the plan."),
            limit=limit,
            used=queries.seats_of(hub, now)["used"],
        )


def _renew(member: HubMember, inviter, now) -> None:
    member.invited_by = inviter
    member.invited_at = now
    member.invitation_expires_at = now + HubMember.INVITATION_WINDOW
    member.save(update_fields=["invited_by", "invited_at", "invitation_expires_at"])


def _mail_invitation(ctx: OperationContext, member: HubMember) -> None:
    new_account = member.user.last_login is None and not member.user.has_usable_password()
    transaction.on_commit(
        partial(emails.send_invitation, member, base_url=emails.base_url(ctx.request), new_account=new_account),
        robust=True,
    )


@operation("hubs.member.invite", kind="command", permission="hubs.manage", input=MemberInviteIn, output=MemberRowOut)
def member_invite(ctx: OperationContext, data: MemberInviteIn) -> dict:
    """Invite somebody to the business with a role below one's own (round 17 §2.8).

    The invitation is a member without an answer, valid for 7 days; an address without an account gets
    one to claim (no password: Google or «Forgot your password?»). The plan must have a seat for one
    more person. It reaches the Hub only once answered. An expired invitation is renewed.
    """
    actor = queries.access(queries.account_of(ctx), data.hub_id, Role.ADMIN, lock=True)
    hub = actor.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.role not in queries.assignable_roles(actor.role):
        raise PermissionDenied(_("You cannot hand out a role equal to or above yours."))
    now = timezone.now()
    member = HubMember.objects.select_for_update().select_related("user").filter(hub=hub, user__email__iexact=data.email).first()
    if member is not None:
        member.hub = hub
        if not member.is_pending:
            raise Conflict(_("%(email)s is already on this business.") % {"email": data.email}, code="hubs.already_member")
        if not member.is_expired(now):
            raise Conflict(
                _("%(email)s already has an invitation waiting. Resend it instead.") % {"email": data.email},
                code="hubs.already_invited",
            )
        if not queries.manages(actor, member):
            raise PermissionDenied(_("You cannot manage a member whose role is equal to or above yours."))
        _check_seat(hub, now)
        member.role = data.role
        member.invitation_message = data.message
        member.save(update_fields=["role", "invitation_message"])
        _renew(member, actor.user, now)
    else:
        _check_seat(hub, now)
        user = get_user_model().objects.filter(email__iexact=data.email).first()
        if user is not None and user.is_staff:
            raise Conflict(
                _("This address belongs to ERPlora's staff and cannot join a business."), code="hubs.platform_account"
            )
        if user is None:
            user = get_user_model().objects.create_user(email=data.email, password=None, language=hub.language)
        member = HubMember.objects.create(
            hub=hub,
            user=user,
            role=data.role,
            invited_by=actor.user,
            invitation_message=data.message,
            invited_at=now,
            invitation_expires_at=now + HubMember.INVITATION_WINDOW,
            joined_at=now,
        )
    record_event(ctx, events.MEMBER_INVITED, {"id": str(member.id), "hub_id": str(hub.id)})
    _mail_invitation(ctx, member)
    return queries.member_row(actor, member, now)


@operation("hubs.member.change_role", kind="command", permission="hubs.manage", input=MemberRoleIn, output=MemberRowOut)
def member_change_role(ctx: OperationContext, data: MemberRoleIn) -> dict:
    """Give a member (or an invitation) another role below one's own; never the owner's."""
    actor, target = _managed(ctx, data.id, data.role)
    if target.role != data.role:
        target.role = data.role
        target.save(update_fields=["role"])
        if not target.is_pending:
            sync_access(target.hub)
            bump_state(target.hub_id)
            push_after_commit(target.hub_id)
        record_event(ctx, events.MEMBER_ROLE_CHANGED, {"id": str(target.id), "hub_id": str(target.hub_id)})
    return queries.member_row(actor, target, timezone.now())


@operation("hubs.member.remove", kind="command", permission="hubs.manage", input=ByIdIn, output=RemovedOut)
def member_remove(ctx: OperationContext, data: ByIdIn) -> dict:
    """Take somebody out of this business only (their other businesses and account stay): their
    access ends, the Hub learns it in the next snapshot and ends their sessions there."""
    _actor, target = _managed(ctx, data.id)
    if target.is_pending:
        raise Conflict(_("This person has not answered yet: cancel the invitation."), code="hubs.member_pending")
    hub = target.hub
    HubOwnershipTransfer.objects.filter(hub=hub, to_user=target.user, status=HubOwnershipTransfer.Status.PENDING).update(
        status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now()
    )
    target.delete()
    sync_access(hub)
    bump_state(hub.id)
    record_event(ctx, events.MEMBER_REMOVED, {"id": str(data.id), "hub_id": str(hub.id)})
    push_after_commit(hub.id)
    revoke_after_commit(target.user_id, hub.id)
    return {"id": data.id}


def _pending_only(target: HubMember) -> None:
    if not target.is_pending:
        raise Conflict(_("This person already answered the invitation."), code="hubs.member_not_pending")


@operation("hubs.member.resend", kind="command", permission="hubs.manage", input=ByIdIn, output=MemberRowOut)
def member_resend(ctx: OperationContext, data: ByIdIn) -> dict:
    """Send the invitation again: it gets 7 more days."""
    actor, target = _managed(ctx, data.id)
    _pending_only(target)
    now = timezone.now()
    if target.is_expired(now):
        _check_seat(target.hub, now)
    _renew(target, actor.user, now)
    record_event(ctx, events.MEMBER_INVITATION_RESENT, {"id": str(target.id), "hub_id": str(target.hub_id)})
    _mail_invitation(ctx, target)
    return queries.member_row(actor, target, now)


@operation("hubs.member.cancel", kind="command", permission="hubs.manage", input=ByIdIn, output=RemovedOut)
def member_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """Withdraw an invitation nobody answered: the row goes."""
    _actor, target = _managed(ctx, data.id)
    _pending_only(target)
    target.delete()
    record_event(ctx, events.MEMBER_INVITATION_CANCELLED, {"id": str(data.id), "hub_id": str(target.hub_id)})
    return {"id": data.id}


def _my_invitation(ctx: OperationContext, member_id: UUID) -> HubMember:
    """The account's own unanswered invitation ``member_id``, locked after its hub; 404 otherwise.

    The security boundary of answering: nothing that is not the caller's own pending row can be
    reached, so no poked id, replay or foreign invitation grants anything (test_invitation_accept).
    """
    user = queries.account_of(ctx)
    hub_id = (
        HubMember.objects.filter(pk=member_id, user=user, accepted_at__isnull=True).values_list("hub_id", flat=True).first()
    )
    hub = Hub.objects.select_for_update().filter(pk=hub_id).first() if hub_id else None
    member = (
        HubMember.objects.select_for_update().filter(pk=member_id, user=user, accepted_at__isnull=True).first()
        if hub is not None and hub.status not in (Hub.Status.DELETING, Hub.Status.DELETED)
        else None
    )
    if member is None:
        raise NotFound(_("This invitation does not exist or is no longer yours to answer."))
    member.hub = hub
    return member


@operation("hubs.invitation.accept", kind="command", permission="hubs.manage", input=ByIdIn, output=BusinessRowOut)
def invitation_accept(ctx: OperationContext, data: ByIdIn) -> dict:
    """Accept an invitation within its 7 days: the account enters with the role it says, if the plan
    still has a seat beside the people already inside (``_check_seat_to_enter``)."""
    member = _my_invitation(ctx, data.id)
    now = timezone.now()
    if member.is_expired(now):
        raise Conflict(
            _("This invitation expired. Ask whoever invited you to send it again."), code="hubs.invitation_expired"
        )
    _check_seat_to_enter(member.hub, now)
    member.accepted_at = now
    member.save(update_fields=["accepted_at"])
    sync_access(member.hub)
    bump_state(member.hub_id)
    record_event(ctx, events.INVITATION_ACCEPTED, {"id": str(member.id), "hub_id": str(member.hub_id)})
    push_after_commit(member.hub_id)
    return queries.business_row(member, now)


@operation("hubs.invitation.decline", kind="command", permission="hubs.manage", input=ByIdIn, output=RemovedOut)
def invitation_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """Decline an invitation: the row goes (round 17 §2.8)."""
    member = _my_invitation(ctx, data.id)
    member.delete()
    record_event(ctx, events.INVITATION_DECLINED, {"id": str(data.id), "hub_id": str(member.hub_id)})
    return {"id": data.id}


# --- Ownership ------------------------------------------------------------------------------------

Transfer = HubOwnershipTransfer.Status


def _transfer_out(transfer: HubOwnershipTransfer) -> dict:
    return {
        "id": transfer.id,
        "hub": {"id": transfer.hub.id, "slug": transfer.hub.slug, "name": transfer.hub.name},
        "from_email": transfer.from_email,
        "to_email": transfer.to_email,
        "status": transfer.status,
        "expires_at": transfer.expires_at,
        "resolved_at": transfer.resolved_at,
    }


def _expire_stale(hub: Hub, now) -> None:
    """Move an offer past its window off ``pending``: the one-pending constraint counts rows, not clocks."""
    HubOwnershipTransfer.objects.filter(hub=hub, status=Transfer.PENDING, expires_at__lte=now).update(
        status=Transfer.EXPIRED, resolved_at=now
    )


@operation(
    "hubs.ownership.transfer", kind="command", permission="hubs.manage", input=OwnershipTransferIn, output=OwnershipTransferOut
)
def ownership_transfer(ctx: OperationContext, data: OwnershipTransferIn) -> dict:
    """The owner offers the business to somebody already on it, who answers within 7 days (saas#1670).

    The payer does not move with it; the outgoing owner stays as admin.
    """
    actor = queries.access(queries.account_of(ctx), data.hub_id, Role.OWNER, lock=True)
    hub = actor.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    target = HubMember.objects.select_related("user").filter(pk=data.member_id, hub=hub, accepted_at__isnull=False).first()
    if target is None:
        raise Conflict(
            _("Invite this person to the business first: it can only go to somebody already on it."),
            code="hubs.transfer_target_not_member",
        )
    if target.user_id == actor.user_id:
        raise Conflict(_("You already own this business."), code="hubs.transfer_to_self")
    now = timezone.now()
    _expire_stale(hub, now)
    if HubOwnershipTransfer.objects.filter(hub=hub, status=Transfer.PENDING).exists():
        raise Conflict(
            _("There is already a transfer of this business waiting for an answer."), code="hubs.transfer_pending"
        )
    transfer = HubOwnershipTransfer.objects.create(
        hub=hub,
        from_user=actor.user,
        to_user=target.user,
        from_email=actor.user.email,
        to_email=target.user.email,
        expires_at=now + HubOwnershipTransfer.WINDOW,
    )
    record_event(ctx, events.OWNERSHIP_REQUESTED, {"id": str(transfer.id), "hub_id": str(hub.id)})
    transaction.on_commit(
        partial(emails.send_ownership_offer, transfer, base_url=emails.base_url(ctx.request)), robust=True
    )
    return _transfer_out(transfer)


def _answer(ctx: OperationContext, transfer_id: UUID, party: str) -> HubOwnershipTransfer:
    """The offer ``transfer_id`` of which the account is the ``party`` (``to_user`` or ``from_user``),
    locked after its hub, still open for an answer. Anybody else gets 404.

    An offer past its window is refused as expired; the refusal writes nothing (one operation, one
    transaction), so the row moves off ``pending`` when the next offer of the business is made, and
    every read already hides it by its clock.
    """
    user = queries.account_of(ctx)
    hub_id = HubOwnershipTransfer.objects.filter(pk=transfer_id, **{party: user}).values_list("hub_id", flat=True).first()
    if hub_id is None:
        raise NotFound(_("This transfer does not exist or is not yours to answer."))
    Hub.objects.select_for_update().filter(pk=hub_id).first()
    transfer = (
        HubOwnershipTransfer.objects.select_for_update(of=("self",))
        .select_related("hub", "from_user", "to_user")
        .get(pk=transfer_id)
    )
    if transfer.status != Transfer.PENDING:
        raise Conflict(_("This transfer was already answered."), code="hubs.transfer_answered")
    if transfer.is_expired:
        raise Conflict(_("This transfer expired. Ask the owner to send it again."), code="hubs.transfer_expired")
    return transfer


@operation("hubs.ownership.accept", kind="command", permission="hubs.manage", input=ByIdIn, output=OwnershipTransferOut)
def ownership_accept(ctx: OperationContext, data: ByIdIn) -> dict:
    """The named recipient takes the business: the two roles swap in one transaction (exactly one owner
    before and after) and nobody leaves it."""
    transfer = _answer(ctx, data.id, "to_user")
    if Subscription.objects.filter(hub=transfer.hub, plan__price_monthly=0).exists():
        check_free_quota(transfer.to_user, excluding=transfer.hub_id)  # it becomes theirs, Free
    incoming = HubMember.objects.select_for_update().filter(hub=transfer.hub, user=transfer.to_user, accepted_at__isnull=False).first()
    outgoing = (
        HubMember.objects.select_for_update()
        .filter(hub=transfer.hub, user_id=transfer.from_user_id, role=Role.OWNER)
        .first()
    )
    if incoming is None:
        raise Conflict(_("You are no longer on this business."), code="hubs.transfer_answered")
    if outgoing is None:
        raise Conflict(
            _("This business already changed hands: ask its current owner to transfer it."), code="hubs.transfer_stale"
        )
    now = timezone.now()
    outgoing.role = Role.ADMIN
    outgoing.save(update_fields=["role"])
    incoming.role = Role.OWNER
    incoming.save(update_fields=["role"])
    transfer.status = Transfer.ACCEPTED
    transfer.resolved_at = now
    transfer.save(update_fields=["status", "resolved_at"])
    sync_access(transfer.hub)
    bump_state(transfer.hub_id)
    record_event(ctx, events.OWNERSHIP_ACCEPTED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    push_after_commit(transfer.hub_id)
    transaction.on_commit(
        partial(emails.send_ownership_accepted, transfer, base_url=emails.base_url(ctx.request)), robust=True
    )
    return _transfer_out(transfer)


def _resolve(transfer: HubOwnershipTransfer, status: str) -> None:
    transfer.status = status
    transfer.resolved_at = timezone.now()
    transfer.save(update_fields=["status", "resolved_at"])


@operation("hubs.ownership.decline", kind="command", permission="hubs.manage", input=ByIdIn, output=OwnershipTransferOut)
def ownership_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """The named recipient says no: nothing about the business changes."""
    transfer = _answer(ctx, data.id, "to_user")
    _resolve(transfer, Transfer.DECLINED)
    record_event(ctx, events.OWNERSHIP_DECLINED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    return _transfer_out(transfer)


@operation("hubs.ownership.cancel", kind="command", permission="hubs.manage", input=ByIdIn, output=OwnershipTransferOut)
def ownership_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """The owner withdraws the offer before it is answered."""
    transfer = _answer(ctx, data.id, "from_user")
    _resolve(transfer, Transfer.CANCELLED)
    record_event(ctx, events.OWNERSHIP_CANCELLED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    return _transfer_out(transfer)


# --- The payer ------------------------------------------------------------------------------------

#: A Spanish NIF, NIE or CIF: nine characters, a letter or digit at each end (form only).
SPANISH_TAX_ID = re.compile(r"^(ES)?[A-Z0-9][0-9]{7}[A-Z0-9]$")
#: An EU VAT number of another country: its two letters, then 8 to 12 letters or digits (form only).
EU_TAX_ID = re.compile(r"^([A-Z]{2})?[A-Z0-9]{8,12}$")


def validate_tax_id(country: str, tax_id: str) -> str:
    """``tax_id`` written as ERPlora invoices it (no spaces, dots nor hyphens, uppercase), if its form
    is one of ``country``'s; else ``ValueError``.

    Only the form: whether the number exists is VIES's answer, which billing asks before charging
    (lot L2-A replaces this hook with the VIES check at checkout).
    """
    normalized = re.sub(r"[\s.\-/]", "", tax_id).upper()
    if not normalized:
        return ""
    pattern = SPANISH_TAX_ID if country == "ES" or normalized.startswith("ES") else EU_TAX_ID
    if not pattern.match(normalized):
        raise ValueError(normalized)
    return normalized


@operation(
    "hubs.billing_profile.update", kind="command", permission="hubs.manage", input=BillingProfileIn, output=BillingProfileOut
)
def billing_profile_update(ctx: OperationContext, data: BillingProfileIn) -> dict:
    """The owner says who ERPlora invoices for the business. «Use the business's data» copies its name
    and country into the payer (PLAN-SAAS §3.1: a copy, not a sync)."""
    member = queries.access(queries.account_of(ctx), data.hub_id, Role.OWNER, lock=True)
    hub = member.hub
    values = data.model_dump(exclude={"hub_id"})
    if data.same_as_business:
        values["billing_name"] = hub.name
        values["billing_country"] = hub.country
    try:
        values["tax_id"] = validate_tax_id(values["billing_country"], values["tax_id"])
    except ValueError:
        raise InvalidPayload(
            _("Invalid payload"), fields={"tax_id": _("Enter a valid tax ID for the country of the payer.")}
        ) from None
    profile = hub.billing_profile
    if profile is None or profile.owner_id != member.user_id:
        # A payer is somebody's: the one another account set up (the owner before a transfer) keeps
        # its data and its other businesses; this business gets a payer of its current owner.
        profile = BillingProfile.objects.create(owner=member.user)
        hub.billing_profile = profile
        hub.save(update_fields=["billing_profile", "updated_at"])
    for field, value in values.items():
        setattr(profile, field, value)
    profile.save()
    record_event(ctx, events.BILLING_PROFILE_UPDATED, {"hub_id": str(hub.id)})
    return queries.payer_of(hub, member.user)


# --- Access, state and the push to the Hub (not operations: called inside or after one) ---------


def sync_access(hub: Hub) -> None:
    """Make ``accounts.HubMembership`` (what the jump checks) equal to the business's answered members.

    Nobody enters a deleted business. Called in the transaction that changed the members or the status.
    """
    deleted = hub.status in (Hub.Status.DELETING, Hub.Status.DELETED)
    wanted = (
        {}
        if deleted
        else dict(
            HubMember.objects.filter(hub=hub, accepted_at__isnull=False).values_list(
                "user_id", "role"
            )
        )
    )
    rows = HubMembership.objects.filter(hub_slug=hub.slug)
    rows.exclude(user_id__in=wanted).delete()
    have = dict(rows.values_list("user_id", "role"))
    for user_id, role in wanted.items():
        if user_id not in have:
            HubMembership.objects.create(user_id=user_id, hub_slug=hub.slug, role=role)
        elif have[user_id] != role:
            HubMembership.objects.filter(user_id=user_id, hub_slug=hub.slug).update(
                role=role
            )


def bump_state(hub_id: UUID) -> None:
    """The snapshot of the business changed: its next push carries a newer version (§2.2)."""
    Hub.objects.filter(pk=hub_id).update(state_version=F("state_version") + 1)


def push_after_commit(hub_id: UUID) -> None:
    """Push the business to the Hub once this transaction commits (never inside it)."""
    transaction.on_commit(partial(_sync_quietly, hub_id), robust=True)


def revoke_after_commit(user_id: UUID, hub_id: UUID | None = None) -> None:
    """End the account's sessions in the business (or in every one) once this transaction commits.

    Best effort: if it is lost, the next snapshot no longer lists the member and the Hub drops them.
    """
    transaction.on_commit(partial(_revoke_quietly, user_id, hub_id), robust=True)


def _sync_quietly(hub_id: UUID) -> None:
    try:
        sync_hub(hub_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the write; it stays owed
        logger.exception("hubs.sync.crashed hub=%s", hub_id)


def _revoke_quietly(user_id: UUID, hub_id: UUID | None) -> None:
    try:
        hub_client.revoke_sessions(str(user_id), str(hub_id) if hub_id else None)
    except (HubUnavailable, HubRefused) as failed:
        logger.warning("hubs.revoke.lost user=%s hub=%s: %s", user_id, hub_id, failed)


#: What one push of a business came to: everything acknowledged, the Hub away (retried, the run
#: fails), or the Hub refusing (recorded on the business, retried, the run fails).
DELIVERED, UNREACHABLE, REFUSED = "delivered", "unreachable", "refused"


def sync_hub(hub_id: UUID) -> bool:
    """Bring the Hub to what the SaaS knows of ``hub_id``; ``True`` when nothing stays owed."""
    return sync_outcome(hub_id) == DELIVERED


def sync_outcome(hub_id: UUID) -> str:
    """Push ``hub_id`` to the Hub: the deletion it owes (and nothing else), the restoration, the
    registry, then the snapshot if the Hub's version is behind.

    Each acknowledgement is recorded as it comes and clears a refusal recorded before. The first
    failure stops: the Hub being away leaves the rest owed (``unreachable``); the Hub refusing (4xx)
    also records its code on the business (``last_hub_error``, through ``hubs.business.record_hub_error``
    and its event), so the panel shows an error instead of
    waiting for ever (``refused``).
    """
    hub = Hub.objects.filter(pk=hub_id).first()
    if hub is None:
        return UNREACHABLE
    call = hub.pending_hub_call
    try:
        if call == Call.DELETE:
            _delete(hub)
            return DELIVERED
        if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
            return DELIVERED
        if call == Call.RESTORE:
            call = _restore(hub)
            if call is None:
                return DELIVERED
        if call == Call.PUT:
            version = hub.registry_version
            hub_client.put_hub(queries.hub_registry(hub.id))
            record_registry_answered(hub.id, version)
        hub.refresh_from_db(fields=["state_version", "pushed_state_version"])
        if hub.pushed_state_version < hub.state_version:
            snapshot = queries.hub_snapshot(hub.id)
            hub_client.put_state(str(hub.id), snapshot)
            record_state_pushed(hub.id, snapshot["version"])
    except HubUnavailable as failed:
        logger.warning("hubs.sync.owed hub=%s call=%s: %s", hub_id, call or "state", failed)
        return UNREACHABLE
    except HubRefused as refused:
        logger.error("hubs.sync.refused hub=%s call=%s: %s", hub_id, call or "state", refused)
        _record_hub_error(hub_id, refused.code[:64])
        return REFUSED
    if Hub.objects.filter(pk=hub_id).exclude(last_hub_error="").exists():
        _record_hub_error(hub_id, None)
    return DELIVERED


def _record_hub_error(hub_id: UUID, code: str | None) -> None:
    """Record (or clear) the Hub's refusal through its command, so the panel hears of it at once."""
    business_record_hub_error(system_ctx_for(hub_id), HubErrorIn(id=hub_id, hub_error=code))


def _delete(hub: Hub) -> None:
    """Send the deletion; a Hub that never had the business (404) has nothing to delete either."""
    try:
        hub_client.delete_hub(str(hub.id))
    except HubRefused as refused:
        if refused.status != 404:
            raise
    record_call_answered(hub.id, Call.DELETE)


def _restore(hub: Hub) -> str | None:
    """Send the restoration; the next call owed (``put`` if the Hub never had it), ``None`` if purged."""
    try:
        hub_client.restore_hub(str(hub.id))
    except HubRefused as refused:
        if refused.code == "hub_purged":
            purged = Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.DELETED, pending_hub_call="")
            if purged:
                HubMembership.objects.filter(hub_slug=hub.slug).delete()
            logger.warning("hubs.sync.purged hub=%s", hub.id)
            return None
        if refused.status != 404:
            raise
        Hub.objects.filter(pk=hub.pk, pending_hub_call=Call.RESTORE).update(pending_hub_call=Call.PUT)
        return Call.PUT
    record_call_answered(hub.id, Call.RESTORE)
    return ""


def record_call_answered(hub_id: UUID, call: str) -> None:
    """The Hub acknowledged ``call``: clear it, unless another call was owed meanwhile."""
    Hub.objects.filter(pk=hub_id, pending_hub_call=call).update(pending_hub_call="")


def record_registry_answered(hub_id: UUID, version: int) -> None:
    """The Hub has the registry ``version``: clear it, unless a newer one is owed (a rename meanwhile)."""
    Hub.objects.filter(pk=hub_id, pending_hub_call=Call.PUT, registry_version=version).update(pending_hub_call="")


def record_state_pushed(hub_id: UUID, version: int) -> None:
    """The Hub has the snapshot ``version``: never moves the pushed version back."""
    Hub.objects.filter(pk=hub_id, pushed_state_version__lt=version, state_version__gte=version).update(
        pushed_state_version=version
    )


# --- The saas-cron runs (manage.py reconcile_hub_states, push_hub_snapshots) ---------------------

#: An sign-up without the Hub's ``ready`` callback this long is asked about (PLAN-SAAS §3.1 step 3).
STUCK_AFTER = timedelta(minutes=2)
LIVE_STATUSES = [Hub.Status.PREPARING, Hub.Status.ACTIVE, Hub.Status.PAST_DUE, Hub.Status.SUSPENDED]
#: Counts that make a run end with an error (the ``task_failed`` alarm), after its whole pass.
FAILING_COUNTS = ("owed", "unreachable", "failed")


def lock_name(command: str) -> str:
    """The advisory lock of ``command``: ``hashtext('erplora.saas.<command>')``, the namespace every lock
    of the SaaS's database takes (``base``'s ``migrate`` and ``report_seal_expiry``)."""
    return f"erplora.saas.{command}"


@contextmanager
def run_exclusively(command: str):
    """Hold the advisory lock of ``command`` while the block runs; yields ``False`` (and runs nothing of
    its own) when another run holds it.

    A session lock, not ``pg_try_advisory_xact_lock``: a run spans many transactions and calls to the Hub
    (one business per transaction, so a failure never undoes another's acknowledgement). One transaction
    around it all would hold every business row it touched until the end, blocking the panel's writes
    (the nightly bump touches every live one), and would sit idle in transaction through every call to
    the Hub, which Aurora ends past 30 s (``idle_in_transaction_session_timeout``,
    ``aws-next/stacks/prod/aurora.tf``), taking the whole pass with it. ``base``'s ``migrate`` holds a
    session lock for the same reason. Released at the end, when the run fails, and when the task dies
    (Postgres ends its session). The SaaS's database is direct, never PgBouncer.
    """
    name = lock_name(command)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        taken = cursor.fetchone()[0]
    try:
        yield taken
    finally:
        if taken:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])


def run_failed(counts: Counter) -> bool:
    """Whether a pass left something owed, unreachable or crashed: its command exits with an error."""
    return any(counts[key] for key in FAILING_COUNTS)


def _sync_counted(hub_id: UUID, counts: Counter) -> None:
    try:
        outcome = sync_outcome(hub_id)
    except Exception:  # noqa: BLE001 - one business never stops the batch; it stays owed
        logger.exception("hubs.sync.crashed hub=%s", hub_id)
        outcome = None
    if outcome == DELIVERED:
        counts["delivered"] += 1
    else:
        counts["owed"] += 1
        counts[REFUSED] += outcome == REFUSED


def reconcile(now=None, stuck_after: timedelta = STUCK_AFTER) -> Counter:
    """One pass of ``reconcile_hub_states``; the counts of what it did (each key is always present)."""
    now = now or timezone.now()
    keys = ("purged", "trials_ended", "delivered", "owed", "refused", "ready", "re_registered", "preparing", "unreachable", "failed")
    counts = Counter({key: 0 for key in keys})
    cutoff = now - Hub.RETENTION
    for hub_id in expired_deletions(cutoff):
        # Re-checked by the UPDATE itself: a business restored since the read is left alone.
        purged = Hub.objects.filter(pk=hub_id, status=Hub.Status.DELETING, deletion_requested_at__lte=cutoff).update(
            status=Hub.Status.DELETED, updated_at=now
        )
        if purged:
            sync_access(Hub.objects.get(pk=hub_id))
            counts["purged"] += 1
    for subscription in Subscription.objects.filter(status=Subscription.Status.TRIALING, trial_end__lte=now):
        ended = Subscription.objects.filter(pk=subscription.pk, status=Subscription.Status.TRIALING).update(
            status=Subscription.Status.ACTIVE, updated_at=now
        )
        if ended:
            bump_state(subscription.hub_id)
            counts["trials_ended"] += 1
    owed = Hub.objects.exclude(status=Hub.Status.DELETED).filter(
        ~Q(pending_hub_call="") | Q(pushed_state_version__lt=F("state_version"), status__in=LIVE_STATUSES)
    )
    for hub_id in owed.order_by("updated_at").values_list("id", flat=True):
        _sync_counted(hub_id, counts)
    stuck = Hub.objects.filter(
        status=Hub.Status.PREPARING, ready_at__isnull=True, pending_hub_call="", provision_requested_at__lte=now - stuck_after
    )
    for hub_id in stuck.values_list("id", flat=True):
        try:
            _settle_stuck(hub_id, counts)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("hubs.reconcile.crashed hub=%s", hub_id)
            counts["failed"] += 1
    return counts


def _settle_stuck(hub_id: UUID, counts: Counter) -> None:
    """Ask the Hub about an sign-up without its ``ready`` callback: ready → mark it; unknown → register again."""
    try:
        answer = hub_client.get_hub(str(hub_id))
    except HubRefused as refused:
        if refused.status != 404:
            counts["unreachable"] += 1
            return
        Hub.objects.filter(pk=hub_id, pending_hub_call="").update(pending_hub_call=Call.PUT)
        _sync_counted(hub_id, counts)
        counts["re_registered"] += 1
        return
    except HubUnavailable:
        counts["unreachable"] += 1
        return
    if isinstance(answer.body, dict) and answer.body.get("status") == "ready":
        business_mark_ready(system_ctx_for(hub_id), MarkReadyIn(id=hub_id))
        counts["ready"] += 1
    else:
        counts["preparing"] += 1


def push_snapshots(*, behind_only: bool = False) -> Counter:
    """One pass of ``push_hub_snapshots``: every live business, each with a newer version (the Hub
    ignores an equal one: PLAN-SAAS §2.2, every night for every business); with ``behind_only``, only
    the ones whose snapshot the Hub is behind on."""
    counts = Counter(pushed=0, owed=0, refused=0)
    live = Hub.objects.filter(status__in=LIVE_STATUSES)
    if not behind_only:
        live.update(state_version=F("state_version") + 1)
    for hub_id in live.filter(pushed_state_version__lt=F("state_version")).order_by("updated_at").values_list("id", flat=True):
        try:
            outcome = sync_outcome(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the batch
            logger.exception("hubs.push.crashed hub=%s", hub_id)
            outcome = None
        counts["pushed" if outcome == DELIVERED else "owed"] += 1
        counts[REFUSED] += outcome == REFUSED
    return counts
