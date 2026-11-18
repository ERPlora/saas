"""The saas-cron pass of ``reconcile_hub_states``: what the Hub is still owed and the sign-ups stuck."""

import logging
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import OperationError
from live.operations import AI, operation

from hubs import emails, hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub, HubMember, SessionRevocation, Subscription
from hubs.queries import access_control, businesses, data_copies
from hubs.queries.access_control import Role
from hubs.schemas.businesses import BusinessDetailOut
from hubs.schemas.common import ByIdIn
from hubs.schemas.hub_callbacks import HubMaintenanceIn, MarkReadyIn
from hubs.services.exclusive_runs import run_exclusively
from hubs.services.hub_callbacks import (
    PROVISION_FAILED,
    business_mark_ready,
    business_record_maintenance,
    system_ctx_for,
)
from hubs.services.hub_push import (
    Call,
    DELIVERED,
    LIVE_STATUSES,
    REFUSED,
    _record_hub_error,
    bump_state,
    sync_outcome,
)
from hubs.services.session_revocations import deliver_revocation
from hubs.services.subscription_sync import sync_plan_modules

logger = logging.getLogger(__name__)


@operation(
    "hubs.business.check",
    kind="command",
    permission="hubs.view",
    input=ByIdIn,
    output=BusinessDetailOut,
    ai=AI(
        description="Check the real provisioning status of a business and recover it when it is ready.",
        asks={
            "en": ("check whether my business is ready", "why is my business taking so long to prepare?"),
            "es": ("comprueba si mi negocio ya está listo", "¿por qué tarda tanto en prepararse mi negocio?"),
        },
    ),
)
def business_check(ctx: OperationContext, data: ByIdIn) -> dict:
    """Run the scheduled status poll now for a member, without another path to the Hub or a version bump."""
    member = access_control.access(access_control.account_of(ctx), data.id)
    if member.hub.status == Hub.Status.PREPARING and member.hub.ready_at is None:
        counts = Counter()
        _settle_stuck(data.id, counts)
        if counts["unreachable"] or counts["failed"] or counts["unexpected"]:
            raise OperationError(
                _("The provisioning status could not be checked. Try again."),
                code="hubs.status_unavailable",
                status=503,
            )
    return businesses.business_detail(member)


#: A sign-up without the Hub's ``ready`` callback this long is asked about.
STUCK_AFTER = timedelta(minutes=2)


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


def reconcile_exclusively(stuck_after: timedelta = STUCK_AFTER, go_on: Callable[[], bool] | None = None) -> Counter | None:
    """One pass of ``reconcile`` under the lock of ``reconcile_hub_states``: its counts, or ``None`` when another run
    holds the lock (and this one did nothing). What the command and the ``saas-worker`` (every 15 minutes,
    ``base.worker``; with its ``go_on``) both run."""
    with run_exclusively("reconcile_hub_states") as mine:
        return reconcile(stuck_after=stuck_after, go_on=go_on) if mine else None


def reconcile(now=None, stuck_after: timedelta = STUCK_AFTER, go_on: Callable[[], bool] | None = None) -> Counter:  # noqa: C901, PLR0912
    """One pass of ``reconcile_hub_states``; the counts of what it did (each key is always present).

    ``go_on`` (the ``saas-worker``'s stop request and the round's time budget) is asked before each call to the Hub:
    once it says no, the pass ends after the business in course and ``cut_short`` is 1; what is left is still owed in
    the database, and the next pass does it. The steps that only touch the database always run."""
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
        "cut_short",
    )
    counts = Counter({key: 0 for key in keys})

    def more() -> bool:
        if not counts["cut_short"] and go_on is not None and not go_on():
            counts["cut_short"] = 1
        return not counts["cut_short"]

    cutoff = now - Hub.RETENTION
    for hub_id in businesses.expired_deletions(cutoff):
        # Re-checked by the UPDATE itself: a business restored since the read is left alone.
        purged = Hub.objects.filter(pk=hub_id, status=Hub.Status.DELETING, deletion_requested_at__lte=cutoff).update(
            status=Hub.Status.DELETED, updated_at=now
        )
        if purged:
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
        if not more():
            break
        _sync_counted(hub_id, counts)
    stuck = Hub.objects.filter(
        status=Hub.Status.PREPARING, ready_at__isnull=True, pending_hub_call="", provision_requested_at__lte=now - stuck_after
    )
    for hub_id in () if counts["cut_short"] else stuck.values_list("id", flat=True):
        if not more():
            break
        try:
            _settle_stuck(hub_id, counts)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("hubs.reconcile.crashed hub=%s", hub_id)
            counts["failed"] += 1
    # Deleted, not told since this deletion, the mail not given up, and somebody to tell: an owner whose account was
    # deleted since (``HubMember.user`` cascades) leaves nobody, so the Hub is not asked.
    untold = Hub.objects.filter(
        Q(data_copy_mailed_at__isnull=True) | Q(data_copy_mailed_at__lt=F("deletion_requested_at")),
        Exists(HubMember.objects.filter(hub=OuterRef("pk"), role=Role.OWNER)),
        status=Hub.Status.DELETING,
        deletion_requested_at__isnull=False,
        data_copy_mail_attempts__lt=DATA_COPY_MAIL_ATTEMPTS,
    )
    for hub_id in () if counts["cut_short"] else untold.values_list("id", flat=True):
        if not more():
            break
        try:
            _tell_data_copy(hub_id, counts)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("hubs.data_copy.crashed hub=%s", hub_id)
            counts["failed"] += 1
    due = SessionRevocation.objects.filter(delivered_at__isnull=True, next_attempt_at__lte=now)
    for revocation_id in () if counts["cut_short"] else due.order_by("next_attempt_at").values_list("id", flat=True):
        if not more():
            break
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
    maintenance = answer.body.get("maintenance") if isinstance(answer.body, dict) else None
    business_record_maintenance(system_ctx_for(hub_id), HubMaintenanceIn(id=hub_id, maintenance=maintenance))
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
        kept = data_copies.hub_data_copies(hub.id)
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
