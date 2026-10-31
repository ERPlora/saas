"""Write operations of hubs, and the push of what the SaaS knows to the Hub service.

One operation = one transaction (``@operation``), with its event in the outbox. Who may write is
decided by the account's ``HubMember`` role (``queries.access``, round 17 §2.7). Every change the Hub
must learn is written in the same transaction (``Hub.pending_hub_call``, ``Hub.state_version``) and
pushed after the COMMIT (``sync_hub``, which never runs inside a transaction); when the Hub is away it
stays owed and ``manage.py reconcile_hub_states`` retries it (plan 2026-10-13 §3, the push to the Hub).

Until the jump to a hub moves to ``hubs`` (plan, L1-A step 2), ``accounts.services.issue_code`` and
``redeem_code`` check an account's access in ``accounts.HubMembership``: ``sync_access``, its only writer,
keeps those rows equal to the answered members of each business, in the same transaction. Taking access
away queues a ``SessionRevocation`` (delivered after the COMMIT, retried by ``reconcile_hub_states``), and a
change of the people of a business is told to its owner and admins (``notify_people``).
"""

import logging
from collections import Counter
from contextlib import contextmanager
from datetime import date, timedelta
from functools import partial
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import AI, INTERNAL, operation
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
from pydantic import ValidationError

from accounts import queries as account_queries
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
    HubUsageDaily,
    Plan,
    SessionRevocation,
    Subscription,
    SubscriptionItem,
)
from hubs.schemas import (
    BillingProfileIn,
    BillingProfileOut,
    BusinessCreateIn,
    BusinessAddressIn,
    BusinessDeleteIn,
    BusinessDetailOut,
    BusinessOpenIn,
    BusinessOpenOut,
    BusinessRowOut,
    BusinessUpdateIn,
    ByIdIn,
    HubErrorIn,
    HubStatusOut,
    SuspensionStepOut,
    HubUsageIn,
    HubUsagePageIn,
    MarkReadyIn,
    MemberInviteIn,
    MemberRoleIn,
    MemberRowOut,
    NotifyPeopleIn,
    NotifyPeopleOut,
    OwnershipTransferIn,
    OwnershipTransferOut,
    RemovedOut,
    SubscriptionApplyIn,
    SubscriptionApplyOut,
    UsageRecordIn,
    UsageRecordOut,
    postal_code_problem,
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


def _refuse_staff(user) -> None:
    """The platform's staff and the customers never share an account: a staff or superuser account neither creates a
    business, nor is invited to one (nor invited again), nor enters one with an invitation that waited while it was
    made staff (409 ``hubs.platform_account``)."""
    if user.is_staff or user.is_superuser:
        raise Conflict(
            _("This address belongs to ERPlora's staff and cannot join a business."), code="hubs.platform_account"
        )


@operation(
    "hubs.business.create",
    kind="command",
    permission="hubs.manage",
    input=BusinessCreateIn,
    output=BusinessDetailOut,
    ai=AI(
        description="Creates a business on the Free plan with its address; one free business per account.",
        risk="high",
    ),
)
def business_create(ctx: OperationContext, data: BusinessCreateIn) -> dict:
    """The sign-up (PLAN-SAAS §3.1 step 2, round 17 §2.3): in one transaction the payer, the business, its
    owner and its Free subscription (no plan carries a trial since 2026-10-15; the Starter trial of ADR-0474
    only if the staff give it one again); after the COMMIT, the Hub.

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
    _refuse_staff(user)
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


def _chosen_slug(slug: str, excluding: UUID | None = None) -> str:
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
    if queries.slug_taken(slug, excluding=excluding):
        raise _slug_taken()
    return slug


def _slug_taken() -> Conflict:
    return Conflict(
        _("This address is taken. Choose another one."), code="hubs.slug_taken"
    )


def _subscribe_to_free(hub: Hub, plan, now) -> Subscription:
    trial = queries.trial_plan()
    if trial is None:
        subscription = Subscription.objects.create(
            hub=hub,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
        )
    else:
        subscription = Subscription.objects.create(
            hub=hub,
            plan=plan,
            trial_plan=trial,
            status=Subscription.Status.TRIALING,
            current_period_start=now,
            trial_start=now,
            trial_end=now + timedelta(days=trial.trial_period_days),
        )
    sync_plan_modules(subscription, now)
    return subscription


# --- Settings, deletion and recovery --------------------------------------------------------------


@operation(
    "hubs.business.update",
    kind="command",
    permission="hubs.manage",
    input=BusinessUpdateIn,
    output=BusinessDetailOut,
    ai=AI(description="Changes the name, country, language or time zone of a business; its owner and administrators."),
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
    "hubs.business.change_address",
    kind="command",
    permission="hubs.manage",
    input=BusinessAddressIn,
    output=BusinessDetailOut,
    ai=AI(
        description="Moves a business to another web address; people must use the new one. Only its owner.",
        risk="high",
    ),
)
def business_change_address(ctx: OperationContext, data: BusinessAddressIn) -> dict:
    """The owner moves the business to another web address (HUBS-F16; PLAN-SAAS §1.1, round 2026-10-15b), checked
    as the Hub checks it (``live.slugs``). The Hub registers it and the photo carries it, both pushed after the
    COMMIT; the jump follows it. The address it leaves stays the business's own (``previous_slug``), so no other
    business takes it and receives the old links and QR codes. The same address again changes nothing."""
    member = queries.access(queries.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.slug == hub.slug:
        return queries.business_detail(member)
    slug = _chosen_slug(data.slug, excluding=hub.id)
    previous = hub.slug
    hub.slug = slug
    hub.previous_slug = previous
    hub.pending_hub_call = hub.pending_hub_call or Call.PUT
    hub.registry_version = F("registry_version") + 1
    hub.state_version = F("state_version") + 1
    try:
        with transaction.atomic():
            hub.save(
                update_fields=[
                    "slug",
                    "previous_slug",
                    "pending_hub_call",
                    "registry_version",
                    "state_version",
                    "updated_at",
                ]
            )
    except IntegrityError:
        raise _slug_taken() from None  # another business took it between the check and the write
    hub.refresh_from_db()
    sync_access(hub, previous_slug=previous)
    record_event(ctx, events.BUSINESS_ADDRESS_CHANGED, {"id": str(hub.id), "slug": slug, "previous_slug": previous})
    push_after_commit(hub.id)
    return queries.business_detail(member)


@operation(
    "hubs.business.delete",
    kind="command",
    permission="hubs.manage",
    input=BusinessDeleteIn,
    output=BusinessDetailOut,
    ai=AI(
        description="Deletes a business: it stops opening at once, is kept 90 days and its plan goes back to Free. "
                    "confirm_name is the business's exact name. Only its owner.",
        risk="high",
    ),
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
    _delete_business(ctx, hub, member.user, base_url=emails.base_url(ctx.request))
    return queries.business_detail(member)


def _delete_business(ctx: OperationContext, hub: Hub, owner, *, base_url: str, unpaid: bool = False) -> None:
    """Delete ``hub`` (PLAN-SAAS §3.4): it stops opening at once, the Hub keeps it 90 days, its plan goes back to
    Free (Stripe's subscription ends in billing's next sweep) and its owner hears until when it can be recovered.
    The owner's own deletion and the end of a long suspension (HUBS-F20, ``unpaid``) take this one path."""
    hub.status = Hub.Status.DELETING
    hub.deletion_requested_at = timezone.now()
    hub.pending_hub_call = Call.DELETE
    # Out of the clock of HUBS-F20: recovered, it comes back on Free, with nothing unpaid.
    hub.suspended_at = hub.suspension_warned_at = hub.suspension_final_notice_at = None
    # The mail «the copy of its data is ready» of this deletion is tried afresh.
    hub.data_copy_mail_attempts = 0
    hub.save(
        update_fields=[
            "status",
            "deletion_requested_at",
            "pending_hub_call",
            "data_copy_mail_attempts",
            "suspended_at",
            "suspension_warned_at",
            "suspension_final_notice_at",
            "updated_at",
        ]
    )
    # A subscription Stripe still bills ends: billing's sweep cancels it (hubs never calls Stripe).
    Subscription.objects.filter(hub=hub, cancel_requested_at__isnull=True).exclude(stripe_subscription_id="").update(
        cancel_requested_at=timezone.now()
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
        partial(_send_deletion, hub, owner, base_url=base_url, unpaid=unpaid),
        robust=True,
    )


def _send_deletion(hub: Hub, owner, *, base_url: str, unpaid: bool) -> None:
    """The deletion mail, after the COMMIT: it leads to the copy of the business's data unless the Hub says the business
    never gets one (``available`` false: no database of its own; ruling of 2026-10-30 on saas#168). The Hub away or
    refusing keeps the way to it: the page itself promises nothing it cannot keep."""
    try:
        data_copy = queries.hub_data_copies(hub.id)["available"]
    except (HubUnavailable, HubRefused):
        data_copy = True
    emails.send_deletion(hub, owner, base_url=base_url, unpaid=unpaid, data_copy=data_copy)


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
    for subscription in Subscription.objects.filter(hub=hub):
        sync_plan_modules(subscription)


@operation(
    "hubs.business.restore",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=BusinessDetailOut,
    ai=AI(description="Recovers a business deleted less than 90 days ago, on the Free plan; only its owner."),
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
    ai=INTERNAL,  # screen
)
def business_open(ctx: OperationContext, data: BusinessOpenIn) -> dict:
    """«Open» (PLAN-SAAS §3.1 step 5), for every role: the Hub's start of the jump, ``url``.

    No code is minted here any more: the Hub binds the jump to the browser with a ``state`` of its own,
    so it starts at its ``/auth/login?next=``, which bounces to ``/hub-login/``; that door mints the
    code (and asks for the second factor of an account that has one). This checks the member and the
    business, and remembers it as the last opened (the launcher lists it first). From the installed app
    (``shell``), the jump carries ``shell=1``: the app links the till to the hub a navigation with that mark
    reaches when it leaves erplora.com (``ERPlora/app`` ``hub_link.rs``).
    """
    member = queries.access(queries.account_of(ctx), data.id)
    hub = member.hub
    if hub.status in NOT_OPENING:
        code, message = NOT_OPENING[hub.status]
        raise Conflict(str(message), code=code)
    HubMember.objects.filter(pk=member.pk).update(last_opened_at=timezone.now())
    record_event(ctx, events.BUSINESS_OPENED, {"id": str(hub.id)})
    url = hub_start_url(hub.slug, data.next)
    return {"url": f"{url}&shell=1" if data.shell else url}


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
    ai=INTERNAL,  # hub
)
def business_mark_ready(ctx: OperationContext, data: MarkReadyIn) -> dict:
    """The Hub's ``POST /internal/hubs/{id}/ready``: the business's database is ready (§3.1 step 3).

    Only the platform calls it (``hubs.internal``). A business being prepared becomes active, and its owner
    hears it by mail after the COMMIT (once: the next call finds it active); one that was suspended or
    deleted meanwhile keeps its status and no mail. Idempotent.
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
    opens = hub.status == Hub.Status.PREPARING
    if opens:
        hub.status = Hub.Status.ACTIVE
        changed.append("status")
    if hub.last_hub_error == PROVISION_FAILED:
        # Ready after the Hub's own retry: the preparation it reported failed is no longer owed.
        hub.last_hub_error, hub.hub_error_at = "", None
        changed += ["last_hub_error", "hub_error_at"]
    if changed:
        hub.save(update_fields=[*changed, "updated_at"])
        record_event(ctx, events.BUSINESS_READY, {"id": str(hub.id)})
    owner = (
        HubMember.objects.filter(hub=hub, role=Role.OWNER).select_related("user").first()
        if opens
        else None
    )
    if owner is not None:
        transaction.on_commit(
            partial(emails.send_ready, hub, owner.user, base_url=emails.base_url(ctx.request)),
            robust=True,
        )
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


@operation(
    "hubs.business.record_hub_error",
    kind="command",
    permission="hubs.manage",
    input=HubErrorIn,
    output=HubStatusOut,
    ai=INTERNAL,  # hub
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


@operation(
    "hubs.business.notify_people",
    kind="command",
    permission="hubs.manage",
    input=NotifyPeopleIn,
    output=NotifyPeopleOut,
    ai=INTERNAL,  # platform
)
def business_notify_people(ctx: OperationContext, data: NotifyPeopleIn) -> dict:
    """A change of the people of the business, recorded on this context's channel, so the lists of that
    account re-run at once (``events.PEOPLE``). Only the platform runs it, from ``notify_people``."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform tells the people of a business."), code="internal_command")
    record_event(ctx, data.event, {"business_id": str(data.id)})
    return {"id": data.id}


def notify_people(ctx: OperationContext, event: str, hub_id: UUID, *also) -> None:
    """Tell the owner, the admins and the accounts in ``also`` of a change of the business's people, each on
    its own channel (``hubs.business.notify_people``), but the actor, whose own event already re-runs its
    lists. Called inside the command: it leaves after the COMMIT, and nothing leaves if it rolls back."""
    actor = getattr(ctx.actor, "pk", None)
    for user_id in queries.people_to_tell(hub_id, also):
        if user_id != actor:
            business_notify_people(system_context(Scope("user", str(user_id))), NotifyPeopleIn(id=hub_id, event=event))


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
        raise PermissionDenied(_("You cannot change your own membership."), code="hubs.own_membership")
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
    # Somebody with no way in yet (a new account, or one released below) is told how to claim it.
    new_account = account_queries.has_no_way_in(member.user)
    transaction.on_commit(
        partial(emails.send_invitation, member, base_url=emails.base_url(ctx.request), new_account=new_account),
        robust=True,
    )


@operation(
    "hubs.member.invite",
    kind="command",
    permission="hubs.manage",
    input=MemberInviteIn,
    output=MemberRowOut,
    ai=AI(
        description="Invites a person by email to a business with a role below one's own; the invitation lasts 7 days.",
    ),
)
def member_invite(ctx: OperationContext, data: MemberInviteIn) -> dict:
    """Invite somebody to the business with a role below one's own (round 17 §2.8).

    The invitation is a member without an answer, valid for 7 days; an address without an account gets
    one to claim (no password: Google or «Forgot your password?»). An account that never proved the
    address is released first (saas#2541, ``accounts.services.release_unproven_account``): whoever opens
    the mailbox claims it, and its sessions in every business end. The plan must have a seat for one
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
        _refuse_staff(member.user)
        _check_seat(hub, now)
        member.role = data.role
        member.invitation_message = data.message
        member.save(update_fields=["role", "invitation_message"])
        _renew(member, actor.user, now)
    else:
        _check_seat(hub, now)
        user = get_user_model().objects.filter(email__iexact=data.email).first()
        if user is None:
            user = get_user_model().objects.create_user(email=data.email, password=None, language=hub.language)
        else:
            _refuse_staff(user)
            if not account_queries.email_is_proven(user, data.email):
                account_services.release_unproven_account(user, reason="invited_while_unverified")
                revoke_after_commit(user.pk)
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
    notify_people(ctx, events.MEMBER_CHANGED, hub.id, member.user_id)
    _mail_invitation(ctx, member)
    return queries.member_row(actor, member, now)


@operation(
    "hubs.member.change_role",
    kind="command",
    permission="hubs.manage",
    input=MemberRoleIn,
    output=MemberRowOut,
    ai=AI(description="Gives a member or a pending invitation of a business another role below one's own."),
)
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
            # The role travels in the Hub's session (``/internal/auth/redeem``): it signs in again with the new one.
            revoke_after_commit(target.user_id, target.hub_id)
        record_event(ctx, events.MEMBER_ROLE_CHANGED, {"id": str(target.id), "hub_id": str(target.hub_id)})
        notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
    return queries.member_row(actor, target, timezone.now())


@operation(
    "hubs.member.remove",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    ai=AI(
        description="Takes a person out of one business: their access to it ends; their account and other businesses "
                    "stay.",
    ),
)
def member_remove(ctx: OperationContext, data: ByIdIn) -> dict:
    """Take somebody out of this business only (their other businesses and account stay): their
    access ends, the Hub learns it in the next snapshot and ends their sessions there."""
    _actor, target = _managed(ctx, data.id)
    if target.is_pending:
        raise Conflict(_("This person has not answered yet: cancel the invitation."), code="hubs.member_pending")
    _refuse_a_payer(target)
    hub = target.hub
    _take_out(target)
    record_event(ctx, events.MEMBER_REMOVED, {"id": str(data.id), "hub_id": str(hub.id)})
    notify_people(ctx, events.MEMBER_CHANGED, hub.id, target.user_id)
    revoke_after_commit(target.user_id, hub.id)
    return {"id": data.id}


def _refuse_a_payer(target: HubMember) -> None:
    """saas#2587: whoever still pays for the business (the owner before a hand-over, ``queries.still_pays``)
    stays in it until the business is paid otherwise; out of it, it would pay for a business it no longer sees."""
    if not queries.still_pays(target):
        return
    name = target.user.get_full_name() or target.user.email
    if queries.is_payer(target):
        message = _(
            "%(name)s still pays for this business. Say who pays from now on first: your billing details are asked "
            "when you pay a plan or a module here."
        ) % {"name": name}
    else:
        message = _(
            "This business's plan is still paid with %(name)s's card: keep it with yours in Billing first."
        ) % {"name": name}
    raise Conflict(message, code="hubs.member_pays")


def _take_out(member: HubMember) -> None:
    """Take ``member`` out of its business (removed, or its account deleted): an ownership offer pending to it is
    cancelled, its access goes with it (``sync_access``) and, once it had answered, the Hub gets a snapshot
    without it after the COMMIT."""
    hub = member.hub
    HubOwnershipTransfer.objects.filter(
        hub=hub, to_user_id=member.user_id, status=HubOwnershipTransfer.Status.PENDING
    ).update(status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now())
    member.delete()
    sync_access(hub)
    if member.accepted_at is not None:
        bump_state(hub.id)
        push_after_commit(hub.id)


def _pending_only(target: HubMember) -> None:
    if not target.is_pending:
        raise Conflict(_("This person already answered the invitation."), code="hubs.member_not_pending")


@operation(
    "hubs.member.resend",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=MemberRowOut,
    ai=AI(description="Sends a pending invitation to a business again, valid for 7 more days."),
)
def member_resend(ctx: OperationContext, data: ByIdIn) -> dict:
    """Send the invitation again: it gets 7 more days."""
    actor, target = _managed(ctx, data.id)
    _pending_only(target)
    _refuse_staff(target.user)
    now = timezone.now()
    if target.is_expired(now):
        _check_seat(target.hub, now)
    _renew(target, actor.user, now)
    record_event(ctx, events.MEMBER_INVITATION_RESENT, {"id": str(target.id), "hub_id": str(target.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
    _mail_invitation(ctx, target)
    return queries.member_row(actor, target, now)


@operation(
    "hubs.member.cancel",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    ai=AI(description="Withdraws an invitation to a business nobody answered yet."),
)
def member_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """Withdraw an invitation nobody answered: the row goes."""
    _actor, target = _managed(ctx, data.id)
    _pending_only(target)
    target.delete()
    record_event(ctx, events.MEMBER_INVITATION_CANCELLED, {"id": str(data.id), "hub_id": str(target.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
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


@operation(
    "hubs.invitation.accept",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=BusinessRowOut,
    ai=AI(description="Accepts an invitation of this account to a business, within its 7 days."),
)
def invitation_accept(ctx: OperationContext, data: ByIdIn) -> dict:
    """Accept an invitation within its 7 days: the account enters with the role it says, if the plan
    still has a seat beside the people already inside (``_check_seat_to_enter``). An account that never
    proved its address confirms it first (saas#2541: 403 ``hubs.email_unverified``)."""
    member = _my_invitation(ctx, data.id)
    _refuse_staff(member.user)
    if not account_queries.email_is_proven(member.user, member.user.email):
        raise PermissionDenied(
            _("Confirm your email address before accepting the invitation."), code="hubs.email_unverified"
        )
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
    notify_people(ctx, events.MEMBER_CHANGED, member.hub_id)
    push_after_commit(member.hub_id)
    return queries.business_row(member, now)


@operation(
    "hubs.invitation.decline",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    ai=AI(description="Declines an invitation of this account to a business."),
)
def invitation_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """Decline an invitation: the row goes (round 17 §2.8)."""
    member = _my_invitation(ctx, data.id)
    member.delete()
    record_event(ctx, events.INVITATION_DECLINED, {"id": str(data.id), "hub_id": str(member.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, member.hub_id)
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
    "hubs.ownership.transfer",
    kind="command",
    permission="hubs.manage",
    input=OwnershipTransferIn,
    output=OwnershipTransferOut,
    ai=AI(
        description="Offers a business to one of its members, who has 7 days to accept; the payer does not change and the "
                    "owner stays as administrator.",
        risk="high",
    ),
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
    notify_people(ctx, events.OWNERSHIP_CHANGED, hub.id, target.user_id)
    transaction.on_commit(
        partial(
            emails.send_ownership_offer,
            transfer,
            base_url=emails.base_url(ctx.request),
            paid_until=queries.paid_until(hub.id),
        ),
        robust=True,
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


@operation(
    "hubs.ownership.accept",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    ai=AI(
        description="Accepts the offer to become the owner of a business; the previous owner stays as administrator.",
    ),
)
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
    # A paid plan stops renewing on the previous payer's card; the new owner keeps it with theirs (HUBS-F28).
    from billing.services import end_renewal_after_hand_over, expire_open_checkouts

    paid_until = end_renewal_after_hand_over(transfer.hub, transfer.to_user)
    # What the previous owner left open in Stripe Checkout can no longer be paid (review of saas#89).
    transaction.on_commit(partial(expire_open_checkouts, transfer.hub_id), robust=True)
    sync_access(transfer.hub)
    bump_state(transfer.hub_id)
    # Both roles changed, and each travels in its Hub session: both sign in again.
    revoke_after_commit(outgoing.user_id, transfer.hub_id)
    revoke_after_commit(incoming.user_id, transfer.hub_id)
    record_event(ctx, events.OWNERSHIP_ACCEPTED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.from_user_id)
    push_after_commit(transfer.hub_id)
    transaction.on_commit(
        partial(
            emails.send_ownership_accepted, transfer, base_url=emails.base_url(ctx.request), paid_until=paid_until
        ),
        robust=True,
    )
    return _transfer_out(transfer)


def _resolve(transfer: HubOwnershipTransfer, status: str) -> None:
    transfer.status = status
    transfer.resolved_at = timezone.now()
    transfer.save(update_fields=["status", "resolved_at"])


@operation(
    "hubs.ownership.decline",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    ai=AI(description="Declines the offer to become the owner of a business; nothing changes."),
)
def ownership_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """The named recipient says no: nothing about the business changes."""
    transfer = _answer(ctx, data.id, "to_user")
    _resolve(transfer, Transfer.DECLINED)
    record_event(ctx, events.OWNERSHIP_DECLINED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.from_user_id)
    return _transfer_out(transfer)


@operation(
    "hubs.ownership.cancel",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    ai=AI(description="The owner withdraws an offer of the business nobody answered yet."),
)
def ownership_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """The owner withdraws the offer before it is answered."""
    transfer = _answer(ctx, data.id, "from_user")
    _resolve(transfer, Transfer.CANCELLED)
    record_event(ctx, events.OWNERSHIP_CANCELLED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.to_user_id)
    return _transfer_out(transfer)


# --- The payer ------------------------------------------------------------------------------------


@operation(
    "hubs.billing_profile.update",
    kind="command",
    permission="hubs.manage",
    input=BillingProfileIn,
    output=BillingProfileOut,
    ai=AI(
        description="Changes who ERPlora invoices for a business: name, tax ID, billing address and email; only its "
                    "owner.",
    ),
)
def billing_profile_update(ctx: OperationContext, data: BillingProfileIn) -> dict:
    """The owner says who ERPlora invoices for the business. «Use the business's data» copies its name
    and country into the payer (PLAN-SAAS §3.1: a copy, not a sync).

    The tax ID goes through billing's VAT door (``billing.services.validate_vat_for_profile``, lot L2-B):
    written as ERPlora invoices it and asked to VIES, whose verdict is logged; a malformed one is the
    field's 422, one VIES does not confirm is kept as identification (it buys no reverse charge)."""
    from billing.services import MalformedVatNumber, retax_payer, validate_vat_for_profile

    member = queries.access(queries.account_of(ctx), data.hub_id, Role.OWNER, lock=True)
    hub = member.hub
    values = data.model_dump(exclude={"hub_id"})
    if data.same_as_business:
        values["billing_name"] = hub.name
        values["billing_country"] = hub.country
    problem = postal_code_problem(values["billing_country"], values["billing_postal_code"])
    if problem:
        raise InvalidPayload(_("Invalid payload"), fields={"billing_postal_code": problem})
    try:
        # Without the payer's country yet (it may wait for the first checkout), read it in the business's.
        country = values["billing_country"] or hub.country
        values["tax_id"] = validate_vat_for_profile(country, values["tax_id"]).vat_number
    except MalformedVatNumber:
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
    # The live subscription takes the rate of the new place from its next invoice (BILLING-F02).
    transaction.on_commit(partial(retax_payer, profile.pk))
    return queries.payer_of(hub, member.user)


# --- What Stripe says of the plan (billing, lot L2-B) ---------------------------------------------

#: The fields of ``Subscription`` that ``hubs.subscription.apply`` writes as they come (``None`` clears the
#: two texts).
APPLIED_FIELDS = (
    "billing_interval",
    "status",
    "stripe_customer_id",
    "stripe_subscription_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "trial_start",
    "trial_end",
    "unpaid_reason",
    "unpaid_since",
    "unpaid_invoice_url",
    "cancel_requested_at",
)
CLEARED_TO_EMPTY = ("unpaid_reason", "unpaid_invoice_url", "stripe_customer_id", "stripe_subscription_id")
#: How a standing moves a business (a deleted one never moves; a paid one not ready yet is preparing).
STANDING_MOVES = {
    "good": {Hub.Status.PAST_DUE: Hub.Status.ACTIVE, Hub.Status.SUSPENDED: Hub.Status.ACTIVE},
    "grace": {Hub.Status.ACTIVE: Hub.Status.PAST_DUE},
    "suspended": {
        Hub.Status.PREPARING: Hub.Status.SUSPENDED,
        Hub.Status.ACTIVE: Hub.Status.SUSPENDED,
        Hub.Status.PAST_DUE: Hub.Status.SUSPENDED,
    },
}


@operation(
    "hubs.subscription.apply",
    kind="command",
    permission="hubs.manage",
    input=SubscriptionApplyIn,
    output=SubscriptionApplyOut,
    ai=INTERNAL,  # platform
)
def subscription_apply(ctx: OperationContext, data: SubscriptionApplyIn) -> dict:
    """Write what the LIVE Stripe subscription says of a business (billing reads it: webhook, checkout,
    the sweep of unpaid plans). Only the platform runs it, in the owner's channel (``system_ctx_for``).

    A field left out is left as it is. What the Hub sees (the effective plan, the commercial status and
    ``modules[]``, PLAN-SAAS §2.2) bumps ``state_version`` and is pushed after the COMMIT; anything written
    records ``hubs.subscription.changed``. A paid subscription carries its own trial, so it ends the trial
    plan of the sign-up. A deleted business keeps its status whatever the standing.
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform applies what Stripe says."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.hub_id).first()
    if hub is None:
        raise queries.not_found()
    sent = data.model_dump(exclude_unset=True, exclude={"hub_id"})
    seen_before = _what_the_hub_sees(hub.id)
    subscription = Subscription.objects.select_for_update().filter(hub=hub).first()
    # Only a business stopped for not paying comes back with a payment (nothing else suspends one today,
    # but a payment must never undo a suspension it did not cause).
    was_unpaid = bool(subscription and subscription.unpaid_reason)
    changed = False
    plan = None
    if "plan" in sent:
        plan = Plan.objects.filter(slug=sent["plan"]).first()
        if plan is None:
            raise InvalidPayload(_("Invalid payload"), fields={"plan": _("There is no plan with this identifier.")})
    if subscription is None:
        subscription = Subscription(hub=hub, plan=plan or queries.free_plan())
        changed = True
    changes = {}
    if plan is not None and subscription.plan_id != plan.pk:
        changes["plan"] = plan
    # A customer sent alone is the payer's (``billing.ensure_customer``): a live subscription keeps the one Stripe
    # charges until Stripe says otherwise (the previous payer's card after a hand-over, HUBS-F28).
    payers_only = "stripe_subscription_id" not in sent and bool(subscription.stripe_subscription_id)
    for field in APPLIED_FIELDS:
        if field == "stripe_customer_id" and payers_only:
            continue
        if field in sent:
            value = sent[field]
            if value is None and field in CLEARED_TO_EMPTY:
                value = ""
            if getattr(subscription, field) != value:
                changes[field] = value
    paid_plan = plan is not None and plan.price_monthly > 0
    if sent.get("stripe_subscription_id") and paid_plan and subscription.trial_plan_id is not None:
        # The paid plan carries its own trial in Stripe; modules alone leave the business on Free.
        changes["trial_plan"] = None
    for field, value in changes.items():
        setattr(subscription, field, value)
    if changes or changed:
        subscription.save()
        changed = True
    customer = sent.get("stripe_customer_id")
    profile = hub.billing_profile
    if customer and profile is not None and not profile.stripe_customer_id:
        BillingProfile.objects.filter(pk=profile.pk).update(stripe_customer_id=customer, updated_at=timezone.now())
        changed = True
    elif customer and profile is not None and profile.stripe_customer_id != customer:
        logger.warning(
            "hubs.subscription.customer_differs hub=%s payer=%s subscription=%s",
            hub.id,
            profile.stripe_customer_id,
            customer,
        )
    if "modules" in sent:
        changed |= _apply_modules(subscription, data.modules or [])
    changed |= sync_plan_modules(subscription)
    if "standing" in sent:
        changed |= _apply_standing(hub, sent["standing"], was_unpaid=was_unpaid)
    if _what_the_hub_sees(hub.id) != seen_before:
        bump_state(hub.id)
        push_after_commit(hub.id)
    if changed:
        record_event(ctx, events.SUBSCRIPTION_CHANGED, {"id": str(hub.id)})
    hub.refresh_from_db(fields=["state_version"])
    return {"hub_id": hub.id, "state_version": hub.state_version, "changed": changed}


def _what_the_hub_sees(hub_id: UUID) -> tuple:
    snapshot = queries.hub_snapshot(hub_id)
    return snapshot["status"], snapshot["plan"], snapshot["modules"]


def _apply_modules(subscription: Subscription, rights) -> bool:
    """The bought modules become ``rights``; the ones the plan includes are not Stripe's to touch, unless Stripe
    bills one open-ended: then its row is bought (with the Stripe item that cancelling it needs)."""
    changed = False
    wanted = {right.module_slug: right for right in rights}
    bought = SubscriptionItem.objects.filter(subscription=subscription, source=SubscriptionItem.Source.PURCHASE)
    gone = bought.exclude(module_slug__in=wanted)
    if gone.exists():
        gone.delete()
        changed = True
    have = {item.module_slug: item for item in SubscriptionItem.objects.filter(subscription=subscription)}
    for slug, right in wanted.items():
        item = have.get(slug)
        if item is None:
            SubscriptionItem.objects.create(
                subscription=subscription,
                module_slug=slug,
                source=SubscriptionItem.Source.PURCHASE,
                stripe_item_id=right.stripe_item_id,
                valid_until=right.valid_until,
            )
            changed = True
        elif item.source == SubscriptionItem.Source.PLAN and right.valid_until is None:
            item.source = SubscriptionItem.Source.PURCHASE
            item.stripe_item_id = right.stripe_item_id
            item.valid_until = None
            item.save(update_fields=["source", "stripe_item_id", "valid_until", "updated_at"])
            changed = True
        elif item.source == SubscriptionItem.Source.PURCHASE and (
            item.stripe_item_id != right.stripe_item_id or item.valid_until != right.valid_until
        ):
            item.stripe_item_id = right.stripe_item_id
            item.valid_until = right.valid_until
            item.save(update_fields=["stripe_item_id", "valid_until", "updated_at"])
            changed = True
    return changed


def sync_plan_modules(subscription: Subscription, now=None) -> bool:
    """Make the business's ``source="plan"`` rights the modules its plan includes now; ``True`` if a row changed.

    The plan is the one the business has now (``effective_plan``): what only the sign-up's trial includes lasts
    until ``trial_end``. A module Stripe bills open-ended keeps its bought row (cancelling it needs its Stripe
    item); a bought one already cancelled (``valid_until``) yields its row to the plan, so the right never lapses.
    Called wherever the plan may change: ``hubs.subscription.apply``, the sign-up, the restore, a trial's end.
    """
    now = now or timezone.now()
    wanted = dict.fromkeys(queries.modules_included_in(subscription.plan))
    effective = subscription.effective_plan(now)
    if effective.pk != subscription.plan_id:
        for slug in queries.modules_included_in(effective):
            wanted.setdefault(slug, subscription.trial_end)
    items = SubscriptionItem.objects.filter(subscription=subscription)
    rows = {item.module_slug: item for item in items}
    changed = False
    for slug, item in rows.items():
        if item.source == SubscriptionItem.Source.PURCHASE and item.valid_until is None:
            wanted.pop(slug, None)
        elif item.source == SubscriptionItem.Source.PLAN and slug not in wanted:
            item.delete()
            changed = True
    for slug, until in wanted.items():
        item = rows.get(slug)
        if item is None:
            SubscriptionItem.objects.create(
                subscription=subscription, module_slug=slug, source=SubscriptionItem.Source.PLAN, valid_until=until
            )
            changed = True
        elif (item.source, item.valid_until, item.stripe_item_id) != (SubscriptionItem.Source.PLAN, until, ""):
            item.source, item.valid_until, item.stripe_item_id = SubscriptionItem.Source.PLAN, until, ""
            item.save(update_fields=["source", "valid_until", "stripe_item_id", "updated_at"])
            changed = True
    return changed


def owe_plan_rights(plan: Plan, now=None) -> int:
    """The staff changed in the admin what ``plan`` gives (``queries.SNAPSHOT_PLAN_FIELDS``; HUBS-F31): each live
    business on it, as its plan or as the trial's, gets the modules of its level written (``sync_plan_modules``) and,
    when its snapshot changes, owes the Hub a newer one, which the next pass of ``reconcile_hub_states`` (every 15
    minutes) delivers instead of the night's. How many businesses owe it.

    Never pushed here: a plan may have thousands of businesses, and the admin's save is one transaction.
    """
    now = now or timezone.now()
    owed = 0
    subscriptions = Subscription.objects.select_related("plan", "trial_plan").filter(
        Q(plan=plan) | Q(trial_plan=plan), hub__status__in=LIVE_STATUSES
    )
    for subscription in subscriptions.order_by("pk"):
        changed = sync_plan_modules(subscription, now)
        if changed or subscription.effective_plan(now) == plan:
            bump_state(subscription.hub_id)
            owed += 1
    return owed


def owe_module_rights(tier: str, previous_tier: str | None = None, now=None) -> int:
    """A paid module of ``tier`` was added in the admin, or moved there from ``previous_tier`` (HUBS-F34): every live
    business whose plan (or trial) reaches either level gets its plan's modules written again (``sync_plan_modules``)
    and, where they changed, owes the Hub a newer snapshot, which the next pass of ``reconcile_hub_states`` delivers.
    How many businesses owe it. Never pushed here, as ``owe_plan_rights``."""
    now = now or timezone.now()
    reached = [queries.LEVELS.index(level) for level in (tier, previous_tier) if level in queries.LEVELS]
    if not reached:
        return 0
    plans = Plan.objects.filter(included_level__in=queries.LEVELS[min(reached) :])
    owed = 0
    subscriptions = Subscription.objects.select_related("plan", "trial_plan").filter(
        Q(plan__in=plans) | Q(trial_plan__in=plans), hub__status__in=LIVE_STATUSES
    )
    for subscription in subscriptions.order_by("pk"):
        if sync_plan_modules(subscription, now):
            bump_state(subscription.hub_id)
            owed += 1
    return owed


def _apply_standing(hub: Hub, standing: str, *, was_unpaid: bool) -> bool:
    if standing == "good" and not was_unpaid:
        return False
    status = STANDING_MOVES[standing].get(hub.status)
    if status == Hub.Status.ACTIVE and hub.ready_at is None:
        status = Hub.Status.PREPARING
    if status is None or status == hub.status:
        return False
    now = timezone.now()
    # The clock of HUBS-F20: suspending dates it; leaving the suspension (it paid) stops it and forgets its notices.
    clock = (
        {"suspended_at": now, "suspension_warned_at": None, "suspension_final_notice_at": None}
        if status == Hub.Status.SUSPENDED
        else {"suspended_at": None, "suspension_warned_at": None, "suspension_final_notice_at": None}
    )
    Hub.objects.filter(pk=hub.pk).update(status=status, updated_at=now, **clock)
    hub.status = status
    logger.info("hubs.subscription.standing hub=%s standing=%s status=%s", hub.id, standing, status)
    return True


# --- Access, state and the push to the Hub (not operations: called inside or after one) ---------


def sync_access(hub: Hub, previous_slug: str = "") -> None:
    """Make ``accounts.HubMembership`` (what the jump checks) equal to the business's answered members.

    Nobody enters a deleted business. Called in the transaction that changed the members or the status.
    The only writer of ``HubMembership`` (``hubs/tests/test_access_mirror.py``); ``queries.verify_access_mirror``
    and the check ``hubs.W001`` say where the two disagree. Retired with the mirror once the jump reads
    ``HubMember`` (``hubs/README.md``, «Pendiente»).
    """
    if previous_slug and previous_slug != hub.slug:
        # The business moved to another address (HUBS-F16): the jump follows it.
        HubMembership.objects.filter(hub_slug=previous_slug).delete()
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


def seed_demo_business(slug: str, people: dict) -> Hub:
    """The business of a hub that already runs in the local Hub (``demo_seed``: ``a`` and ``b``), with
    ``people`` (account → ``hub_*`` role) answered on it; creates what is missing, changes nothing else.

    Adopted, not provisioned: active, ready and owing the Hub nothing (as the data migration ``0006`` adopts
    the hubs of the phase-1 seed), on the Free plan if it is seeded; named after its address, in Spain.
    Its access goes through ``sync_access``.
    """
    roles = set(people.values())
    if not roles <= set(Role.values):
        raise ValueError(f"not customer roles: {sorted(roles - set(Role.values))}")
    with transaction.atomic():
        hub = Hub.objects.filter(slug=slug).first()
        if hub is None:
            now = timezone.now()
            owner = next((user for user, role in people.items() if role == Role.OWNER), None)
            hub = Hub.objects.create(
                slug=slug,
                name=slug,
                country="ES",
                language=owner.language if owner is not None else settings.LANGUAGE_CODE,
                status=Hub.Status.ACTIVE,
                ready_at=now,
                pushed_state_version=1,
                state_version=1,
            )
            plan = queries.free_plan()
            if plan is not None:
                sync_plan_modules(
                    Subscription.objects.create(
                        hub=hub, plan=plan, status=Subscription.Status.ACTIVE, current_period_start=now
                    ),
                    now,
                )
        for user, role in people.items():
            joined = timezone.now()
            HubMember.objects.get_or_create(
                hub=hub, user=user, defaults={"role": role, "joined_at": joined, "accepted_at": joined}
            )
        sync_access(hub)
    return hub


def bump_state(hub_id: UUID) -> None:
    """The snapshot of the business changed: its next push carries a newer version (§2.2)."""
    Hub.objects.filter(pk=hub_id).update(state_version=F("state_version") + 1)


def push_after_commit(hub_id: UUID) -> None:
    """Push the business to the Hub once this transaction commits (never inside it)."""
    transaction.on_commit(partial(_sync_quietly, hub_id), robust=True)


def revoke_after_commit(user_id: UUID, hub_id: UUID | None = None) -> SessionRevocation:
    """End the account's sessions in the business (or in every one, ``hub_id`` empty).

    Queued in this transaction (``SessionRevocation``) and delivered once it commits; if the Hub is away
    or refuses it, ``reconcile_hub_states`` retries it (``deliver_revocation``). A removed member also
    leaves the next snapshot, the Hub's second way of learning it.
    """
    revocation = SessionRevocation.objects.create(user_id=user_id, hub_id=hub_id)
    transaction.on_commit(partial(_deliver_quietly, revocation.id), robust=True)
    return revocation


# --- What an account's own changes mean to its businesses (``accounts.signals``, connected in apps.py) --


def end_account_sessions(sender, user_id: UUID, **kwargs) -> SessionRevocation:
    """``accounts.signals.sessions_ended``: the account's sessions end in every business too (PLAN-SAAS §2.1).

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
    """allauth's ``email_changed``: the snapshot's ``members[]`` carries the address (PLAN-SAAS §2.2)."""
    _people_changed(user.pk)


def _people_changed(user_id: UUID) -> None:
    for hub_id in queries.answered_business_ids(user_id):
        bump_state(hub_id)
        push_after_commit(hub_id)
        notify_people(system_ctx_for(hub_id), events.MEMBER_CHANGED, hub_id)


def _sync_quietly(hub_id: UUID) -> None:
    try:
        sync_hub(hub_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the write; it stays owed
        logger.exception("hubs.sync.crashed hub=%s", hub_id)


def _deliver_quietly(revocation_id: UUID) -> None:
    try:
        deliver_revocation(revocation_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the write; it stays queued
        logger.exception("hubs.revoke.crashed revocation=%s", revocation_id)


#: The wait before retrying a revocation the Hub did not take: 15 minutes (one ``reconcile_hub_states``
#: run) after the first failure, doubling with each one, never more than 6 hours.
REVOCATION_FIRST_WAIT = timedelta(minutes=15)
REVOCATION_LONGEST_WAIT = timedelta(hours=6)


def revocation_backoff(attempts: int) -> timedelta:
    """How long a revocation waits after its ``attempts``-th failed delivery."""
    return min(REVOCATION_FIRST_WAIT * 2 ** max(attempts - 1, 0), REVOCATION_LONGEST_WAIT)


def deliver_revocation(revocation_id: UUID) -> str:
    """Send a queued revocation to the Hub: ``DELIVERED`` (also when nothing was left to send), or
    ``UNREACHABLE``/``REFUSED`` with the error and the next wait recorded on the row.

    A purged business has no session left: delivered without a call. Idempotent: a delivered row is
    never sent again, and the Hub's revoke is idempotent if two deliveries race.
    """
    revocation = SessionRevocation.objects.select_related("hub").filter(pk=revocation_id, delivered_at__isnull=True).first()
    if revocation is None:
        return DELIVERED
    if revocation.hub is None or revocation.hub.status != Hub.Status.DELETED:
        try:
            hub_client.revoke_sessions(str(revocation.user_id), str(revocation.hub_id) if revocation.hub_id else None)
        except HubUnavailable as failed:
            _revocation_failed(revocation, str(failed))
            return UNREACHABLE
        except HubRefused as refused:
            _revocation_failed(revocation, str(refused))
            return REFUSED
    SessionRevocation.objects.filter(pk=revocation.pk, delivered_at__isnull=True).update(
        delivered_at=timezone.now(), attempts=F("attempts") + 1, last_error=""
    )
    return DELIVERED


def _revocation_failed(revocation: SessionRevocation, error: str) -> None:
    attempts = revocation.attempts + 1
    logger.warning("hubs.revoke.owed user=%s hub=%s attempt=%s: %s", revocation.user_id, revocation.hub_id, attempts, error)
    SessionRevocation.objects.filter(pk=revocation.pk, delivered_at__isnull=True).update(
        attempts=attempts,
        last_error=error[:255],
        next_attempt_at=timezone.now() + revocation_backoff(attempts),
    )


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
            # The registry is acknowledged by now: a refusal from here on is the snapshot's (a ``whatsapp`` block
            # out of the Hub's schema refuses it whole, hub#127), and the log has to say which.
            call = "state"
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
    if Hub.objects.filter(pk=hub_id).exclude(last_hub_error__in=["", PROVISION_FAILED]).exists():
        # A delivered call clears the Hub's last refusal, not a preparation it still owes (``ready`` clears that one).
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
                sync_access(Hub.objects.get(pk=hub.pk))
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
#: The Hub's last error recorded on a business it says it could not prepare (``failed``): the panel shows «We could not
#: prepare it. We keep retrying» (the Hub retries on its own and calls ``ready`` once it can), never «preparing» for ever.
PROVISION_FAILED = "hubs.provision_failed"
#: How far before its deletion the Hub's copy of a business may say it was made and still be that deletion's (the two
#: clocks; the Hub copies on receiving the ``DELETE``, after the SaaS's COMMIT).
DATA_COPY_CLOCK_SKEW = timedelta(minutes=1)
#: How many passes the mail «the copy is ready» is tried before it is given up (a recipient refused for good: SES in
#: its sandbox, an address gone). A mail is logged, never raised (``emails``): it never fails a pass.
DATA_COPY_MAIL_ATTEMPTS = 6
#: Counts that make a run end with an error (the ``task_failed`` alarm), after its whole pass.
FAILING_COUNTS = (
    "owed",
    "unreachable",
    "failed",
    "provision_failed",
    "unexpected",
    "sessions_pending",
)


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
    keys = (
        "purged",
        "trials_ended",
        "delivered",
        "owed",
        "refused",
        "ready",
        "re_registered",
        "preparing",
        "provision_failed",
        "unexpected",
        "unreachable",
        "failed",
        "data_copies_told",
        "data_copy_unsent",
        "data_copy_none",
        "sessions_ended",
        "sessions_pending",
    )
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
            sync_plan_modules(Subscription.objects.get(pk=subscription.pk), now)
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
    # Deleted, not told since this deletion, the mail not given up, and somebody to tell: an owner whose account was
    # deleted since (``HubMember.user`` cascades) leaves nobody, so the Hub is not asked (review of saas#168).
    untold = Hub.objects.filter(
        Q(data_copy_mailed_at__isnull=True) | Q(data_copy_mailed_at__lt=F("deletion_requested_at")),
        Exists(HubMember.objects.filter(hub=OuterRef("pk"), role=Role.OWNER)),
        status=Hub.Status.DELETING,
        deletion_requested_at__isnull=False,
        data_copy_mail_attempts__lt=DATA_COPY_MAIL_ATTEMPTS,
    )
    for hub_id in untold.values_list("id", flat=True):
        try:
            _tell_data_copy(hub_id, counts)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("hubs.data_copy.crashed hub=%s", hub_id)
            counts["failed"] += 1
    due = SessionRevocation.objects.filter(delivered_at__isnull=True, next_attempt_at__lte=now)
    for revocation_id in due.order_by("next_attempt_at").values_list("id", flat=True):
        try:
            outcome = deliver_revocation(revocation_id)
        except Exception:  # noqa: BLE001 - one revocation never stops the pass; it stays queued
            logger.exception("hubs.revoke.crashed revocation=%s", revocation_id)
            outcome = None
        counts["sessions_ended" if outcome == DELIVERED else "sessions_pending"] += 1
    return counts


def _settle_stuck(hub_id: UUID, counts: Counter) -> None:
    """Ask the Hub about a sign-up without its ``ready`` callback: ready → mark it; still preparing → wait; failed →
    the panel says so (``PROVISION_FAILED``); unknown → register again. Any other answer (the Hub calls ended a
    business the SaaS is preparing, or a status off the contract) is logged for a person and fails the run."""
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
    status = answer.body.get("status") if isinstance(answer.body, dict) else None
    if status == "ready":
        business_mark_ready(system_ctx_for(hub_id), MarkReadyIn(id=hub_id))
        counts["ready"] += 1
    elif status in hub_client.PREPARING_STATUSES:
        counts["preparing"] += 1
    elif status == hub_client.FAILED_STATUS:
        logger.warning("hubs.reconcile.provision_failed hub=%s", hub_id)
        _record_hub_error(hub_id, PROVISION_FAILED)
        counts["provision_failed"] += 1
    else:
        logger.error("hubs.reconcile.unexpected_status hub=%s status=%r", hub_id, status)
        counts["unexpected"] += 1


def _tell_data_copy(hub_id: UUID, counts: Counter) -> None:
    """«We'll let you know» of a deleted business's page: once the Hub keeps the copy it made at this deletion
    (``offboarding``, no older than ``deletion_requested_at``), its owner is told by mail, once; asked again on each pass
    until then. The Hub away or refusing (anything but a 404) counts ``unreachable`` and fails the pass; a mail that
    cannot leave counts ``data_copy_unsent`` and is tried again next pass, ``DATA_COPY_MAIL_ATTEMPTS`` times at most."""
    hub = Hub.objects.get(pk=hub_id)
    try:
        kept = queries.hub_data_copies(hub.id)
    except (HubUnavailable, HubRefused):
        counts["unreachable"] += 1
        return
    if not kept["available"]:
        # No database of its own: no copy will ever come, and its page promised none.
        counts["data_copy_none"] += 1
        return
    since = hub.deletion_requested_at - DATA_COPY_CLOCK_SKEW
    if not any(copy["kind"] == "offboarding" and copy["created_at"] >= since for copy in kept["copies"]):
        return
    owner = HubMember.objects.filter(hub=hub, role=Role.OWNER).select_related("user").first()
    if not emails.send_data_copy_ready(hub, owner.user if owner else None, base_url=emails.base_url(None)):
        attempts = hub.data_copy_mail_attempts + 1
        Hub.objects.filter(pk=hub.pk).update(data_copy_mail_attempts=F("data_copy_mail_attempts") + 1)
        counts["data_copy_unsent"] += 1
        if attempts >= DATA_COPY_MAIL_ATTEMPTS:
            logger.error("hubs.data_copy.mail_given_up hub=%s attempts=%s", hub.id, attempts)
        return
    Hub.objects.filter(pk=hub.pk).update(data_copy_mailed_at=timezone.now())
    counts["data_copies_told"] += 1


# --- The platform's actions in the admin (hubs.admin) ----------------------------------------------


def send_latest_state(hub_ids) -> Counter:
    """«Send the latest state to the Hub»: a newer snapshot of each live business, pushed now (with whatever
    else it owes). ``{delivered, owed}``; what stays owed, ``reconcile_hub_states`` retries."""
    for hub_id in Hub.objects.filter(pk__in=hub_ids, status__in=LIVE_STATUSES).values_list("id", flat=True):
        bump_state(hub_id)
    return retry_owed(hub_ids)


def retry_owed(hub_ids) -> Counter:
    """«Retry what the Hub still owes»: the pass of ``reconcile_hub_states`` on these businesses only (the
    registry, a deletion, a restoration, a snapshot behind). ``{delivered, owed}``."""
    counts = Counter(delivered=0, owed=0)
    for hub_id in hub_ids:
        try:
            outcome = sync_outcome(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the others; it stays owed
            logger.exception("hubs.admin.sync_crashed hub=%s", hub_id)
            outcome = None
        counts["delivered" if outcome == DELIVERED else "owed"] += 1
    return counts


def deliver_revocations(revocation_ids) -> Counter:
    """«End the sessions now»: deliver these revocations without waiting for their next attempt.
    ``{delivered, pending}``."""
    counts = Counter(delivered=0, pending=0)
    for revocation_id in revocation_ids:
        counts["delivered" if deliver_revocation(revocation_id) == DELIVERED else "pending"] += 1
    return counts


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


# --- Usage: the nightly collection (lot L4-A, PLAN-SAAS §5) -----------------------------------------

#: The figures of a day of usage, as ``HubUsageDaily`` keeps them.
USAGE_FIGURES = ("s3_bytes", "db_bytes", "active_users_1d", "active_users_30d")
#: Counts that make ``collect_hub_usage`` end with an error, after its whole pass.
USAGE_FAILING_COUNTS = ("unreachable", "refused", "invalid", "failed")


@operation(
    "hubs.usage.record",
    kind="command",
    permission="hubs.manage",
    input=UsageRecordIn,
    output=UsageRecordOut,
    ai=INTERNAL,  # hub
)
def usage_record(ctx: OperationContext, data: UsageRecordIn) -> dict:
    """One day of a business's usage as the Hub measured it (``collect_hub_usage``); only the platform runs it.

    A day measured again replaces its figures. New or different figures are told to the owner and the admins
    (``hubs.business.usage_collected``), whose page re-runs; the same figures again write and tell nothing.
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform records the usage of a business."), code="internal_command")
    if not Hub.objects.filter(pk=data.id).exists():
        raise queries.not_found()
    figures = {name: getattr(data, name) for name in USAGE_FIGURES}
    sample, created = HubUsageDaily.objects.select_for_update().get_or_create(
        hub_id=data.id, day=data.day, defaults=figures
    )
    changed = created or any(getattr(sample, name) != value for name, value in figures.items())
    if changed:
        if not created:
            HubUsageDaily.objects.filter(pk=sample.pk).update(**figures, collected_at=timezone.now())
        notify_people(ctx, events.BUSINESS_USAGE_COLLECTED, data.id)
    return {"id": data.id, "day": data.day, "changed": changed}


def usage_run_failed(counts: Counter) -> bool:
    """Whether a pass of ``collect_hub_usage`` met the Hub away or refusing, or an answer off the contract."""
    return any(counts[key] for key in USAGE_FAILING_COUNTS)


def collect_usage(day: date) -> Counter:
    """One pass of ``collect_hub_usage``: every page of ``GET /internal/usage?day=``, each business's day
    recorded on its own (one bad row, or one that fails, never stops the others).

    Counts: ``pages``; ``recorded`` (new or different) and ``unchanged``; ``unknown`` (a hub the SaaS never
    sold: the Hub's own, its templates; logged, not an error); ``invalid`` (a row, a page or a cursor off the
    contract); ``unreachable`` and ``refused`` (the Hub away, or its 4xx: the pass ends there, with what it
    had); ``failed`` (a row that crashed)."""
    keys = ("pages", "recorded", "unchanged", "unknown", "invalid", "unreachable", "refused", "failed")
    counts = Counter({key: 0 for key in keys})
    cursor, seen = None, set()
    while True:
        try:
            answer = hub_client.get_usage(day, cursor)
        except HubUnavailable as away:
            logger.error("hubs.usage.unreachable day=%s: %s", day, away)
            counts["unreachable"] += 1
            break
        except HubRefused as refused:
            logger.error("hubs.usage.refused day=%s: %s", day, refused)
            counts["refused"] += 1
            break
        try:
            page = HubUsagePageIn.model_validate(answer.body)
        except ValidationError as broken:
            logger.error("hubs.usage.invalid_page day=%s: %s", day, broken)
            counts["invalid"] += 1
            break
        if page.day != day:
            logger.error("hubs.usage.invalid_page day=%s: the Hub answered for %s", day, page.day)
            counts["invalid"] += 1
            break
        counts["pages"] += 1
        for row in page.hubs:
            _record_counted(day, row, counts)
        cursor = page.next_cursor
        if cursor is None:
            break
        if cursor in seen:
            logger.error("hubs.usage.invalid_page day=%s: the Hub sent the cursor %r again", day, cursor)
            counts["invalid"] += 1
            break
        seen.add(cursor)
    return counts


def _record_counted(day: date, row: dict, counts: Counter) -> None:
    try:
        measured = HubUsageIn.model_validate(row)
    except ValidationError as broken:
        logger.error("hubs.usage.invalid_row day=%s: %s", day, broken)
        counts["invalid"] += 1
        return
    try:
        recorded = usage_record(
            system_context(Scope("user", "system")), UsageRecordIn(**measured.model_dump(), day=day)
        )
    except NotFound:
        logger.warning("hubs.usage.unknown_hub day=%s hub=%s", day, measured.id)
        counts["unknown"] += 1
        return
    except Exception:  # noqa: BLE001 - one business never stops the pass; the run fails after it
        logger.exception("hubs.usage.crashed day=%s hub=%s", day, measured.id)
        counts["failed"] += 1
        return
    counts["recorded" if recorded.changed else "unchanged"] += 1


# --- The clock of a suspended business (HUBS-F20) -------------------------------------------------

#: Days after the suspension of an unpaid plan: the first notice, the last one, and the deletion (PLAN-SAAS §1.1,
#: round 2026-10-15b; ERPlora/saas ``SUSPENDED_HUB_*_DAYS``).
SUSPENDED_WARN_DAYS = 30
SUSPENDED_FINAL_NOTICE_DAYS = 150
SUSPENDED_DELETE_DAYS = 180

#: What a pass of the clock counts (``billing.services.sweep_unpaid`` adds them to its own).
AGE_COUNTS = ("warned", "final_notice", "expired", "undated", "mail_failed", "errors")


def age_suspended() -> Counter:
    """One pass of the clock over every suspended business (HUBS-F20), each in its own transaction: one that
    fails is logged and counted, never stops the others. Run hourly by ``billing.services.sweep_unpaid``."""
    counts = Counter({key: 0 for key in AGE_COUNTS})
    suspended = Hub.objects.filter(status=Hub.Status.SUSPENDED).order_by("pk").values_list("pk", flat=True)
    for hub_id in list(suspended):
        try:
            outcome = business_age_suspension(system_ctx_for(hub_id), ByIdIn(id=hub_id)).outcome
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception("hubs.suspension.failed hub=%s", hub_id)
            counts["errors"] += 1
            continue
        if outcome:
            counts[outcome] += 1
    return counts


@operation(
    "hubs.business.age_suspension",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=SuspensionStepOut,
    ai=INTERNAL,  # scheduled
)
def business_age_suspension(ctx: OperationContext, data: ByIdIn) -> dict:
    """The step of the clock that is due for one suspended business (HUBS-F20), platform only: the first notice
    (day 30), the last one (day 150, also when a late pass finds both due), or the deletion (day 180, only after
    the last notice went out), each once. A notice is marked sent only if its mail left (a failed one goes again
    on the next pass). A suspension nobody dated is never deleted: it is logged for a person."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform ages a suspension."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.id, status=Hub.Status.SUSPENDED).first()
    if hub is None:
        return {"id": data.id, "outcome": ""}
    if hub.suspended_at is None:
        logger.error("hubs.suspension.undated hub=%s: a person has to look at it", hub.id)
        return {"id": hub.id, "outcome": "undated"}
    now = timezone.now()
    days = (now - hub.suspended_at).days
    owner = HubMember.objects.select_related("user").filter(hub=hub, role=Role.OWNER).first()
    delete_on = hub.suspended_at + timedelta(days=SUSPENDED_DELETE_DAYS)
    base_url = emails.base_url(None)
    if days >= SUSPENDED_DELETE_DAYS and hub.suspension_final_notice_at is not None:
        _delete_business(ctx, hub, owner.user if owner else None, base_url=base_url, unpaid=True)
        logger.info("hubs.suspension.expired hub=%s", hub.id)
        return {"id": hub.id, "outcome": "expired"}
    if days >= SUSPENDED_FINAL_NOTICE_DAYS and hub.suspension_final_notice_at is None:
        field, outcome, final = "suspension_final_notice_at", "final_notice", True
    elif days >= SUSPENDED_WARN_DAYS and hub.suspension_warned_at is None and hub.suspension_final_notice_at is None:
        field, outcome, final = "suspension_warned_at", "warned", False
    else:
        return {"id": hub.id, "outcome": ""}
    if owner is None or not emails.send_suspension_notice(
        hub, owner.user, base_url=base_url, delete_on=delete_on, final=final
    ):
        return {"id": hub.id, "outcome": "mail_failed"}
    Hub.objects.filter(pk=hub.pk).update(**{field: now})
    return {"id": hub.id, "outcome": outcome}
