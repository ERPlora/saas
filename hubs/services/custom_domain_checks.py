"""The hourly check of a business's own domain (``check_custom_domains``) and what it records."""

import logging
from collections import Counter
from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs import domain_checks, edge_client, emails, events
from hubs.models import CustomDomain, Hub, HubMember, new_certificate_token
from hubs.queries import custom_domains, plan_catalog
from hubs.queries.access_control import Role
from hubs.schemas import CustomDomainRecordIn, CustomDomainRecordOut
from hubs.services.hub_callbacks import system_ctx_for
from hubs.services.hub_push import bump_state, sync_hub

logger = logging.getLogger(__name__)


#: Checks in a row that find it not pointing here or not served before it is no longer served.
CUSTOM_DOMAIN_FAILURES_TO_LAPSE = 3
#: How long a certificate waits on the shared listener for a CNAME that does not come: its place is another's.
CUSTOM_DOMAIN_PENDING_LIMIT = timedelta(days=14)
#: Counts that make ``check_custom_domains`` end with an error, after its whole pass. AWS, the DNS or the Hub being away
#: are not: they come back, and the next pass tries again.
CUSTOM_DOMAIN_FAILING_COUNTS = ("crashed", "metric_unpublished")

_NOT_ISSUED_YET = "PENDING_VALIDATION"
_ISSUED = "ISSUED"
_TIMED_OUT = "VALIDATION_TIMED_OUT"


@operation(
    "hubs.custom_domain.record",
    kind="command",
    permission="hubs.manage",
    input=CustomDomainRecordIn,
    output=CustomDomainRecordOut,
    ai=INTERNAL,  # only the hourly check runs it
)
def custom_domain_record(ctx: OperationContext, data: CustomDomainRecordIn) -> dict:  # noqa: C901, PLR0912
    """What the hourly check learned, unless the domain left the state it found: the owner removing it wins. A command,
    so a change has its event on the owner's channel, and one of what the Hub is told owes it a newer snapshot."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform records what its check learned."), code="internal_command")
    row = CustomDomain.objects.select_for_update().filter(pk=data.id).first()
    if row is None or row.state != data.expected_state:
        return {"recorded": False}
    before = _what_the_owner_sees(row)
    was_in_snapshot = row.in_snapshot
    now = timezone.now()
    if data.forget:
        row.delete()
        if was_in_snapshot:
            bump_state(row.hub_id)
        record_event(ctx, events.CUSTOM_DOMAIN_CHANGED, {"business_id": str(row.hub_id)})
        return {"recorded": True}
    for field in ("reason", "certificate_arn", "validation_name", "validation_value", "failures"):
        value = getattr(data, field)
        if value is not None:
            setattr(row, field, value)
    if data.state is not None:
        row.state = data.state
        if data.state == CustomDomain.State.ACTIVE:
            row.activated_at = now
    if data.new_token:
        row.certificate_token = new_certificate_token()
    if data.attached is not None:
        row.attached_at = now if data.attached else None
    if data.proven is False:
        row.proven_at = None
    elif data.proven and row.proven_at is None:
        row.proven_at = now
    row.checked_at = now
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError:
        # Another business holds the proof of this name: the Hub would serve neither, so this one waits for that one to fall.
        row.proven_at = None
        row.reason = CustomDomain.Reason.TAKEN
        row.save()
    if was_in_snapshot != row.in_snapshot or data.owe_snapshot:
        bump_state(row.hub_id)
    if _what_the_owner_sees(row) != before:
        record_event(ctx, events.CUSTOM_DOMAIN_CHANGED, {"business_id": str(row.hub_id)})
    return {"recorded": True}


def _what_the_owner_sees(row: CustomDomain) -> tuple:
    return (row.state, row.reason, row.validation_name, row.failures, row.attached_at is None, row.proven_at is None)


class _DomainMovedOn(Exception):
    """The domain left the state the check found it in: its owner removed it. What the check learned is not written."""


def _learned(row: CustomDomain, **facts) -> CustomDomain:
    """Write what the check learned of ``row``, and read it back."""
    answer = custom_domain_record(
        system_ctx_for(row.hub_id), CustomDomainRecordIn(id=row.id, expected_state=row.state, **facts)
    )
    if not answer.recorded:
        raise _DomainMovedOn(str(row.id))
    return custom_domains.custom_domain_row(row.id) if not facts.get("forget") else row


def check_custom_domains() -> Counter:
    """One pass of ``check_custom_domains``: every domain, each on its own, and at the end the certificates attached."""
    counts = Counter(checked=0, crashed=0)
    for domain_id in custom_domains.custom_domain_ids():
        counts["checked"] += 1
        try:
            counts[_check_custom_domain(domain_id)] += 1
        except Exception:  # noqa: BLE001 - one domain never stops the pass
            logger.exception("hubs.custom_domain.crashed domain=%s", domain_id)
            counts["crashed"] += 1
    try:
        edge_client.publish_certificates_attached(custom_domains.certificates_attached())
    except edge_client.EdgeUnavailable as error:
        logger.error("hubs.custom_domain.metric_unpublished: %s", error)
        counts["metric_unpublished"] = 1
    return counts


def custom_domains_failed(counts: Counter) -> bool:
    """Whether a pass of ``check_custom_domains`` has to end with an error."""
    return any(counts[key] for key in CUSTOM_DOMAIN_FAILING_COUNTS)


def _check_custom_domain(domain_id: UUID) -> str:  # noqa: PLR0911
    """Move one domain as far as it goes today; the outcome names what happened, for the counts of the pass."""
    row = custom_domains.custom_domain_row(domain_id)
    if row is None:
        return "gone"
    try:
        if row.state == CustomDomain.State.REMOVING:
            return _finish_removal(row)
        if row.hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
            return _lapse(row, CustomDomain.Reason.BUSINESS_GONE)
        plan = plan_catalog.effective_plan(row.hub_id, timezone.now())
        if plan is None or not plan.includes_custom_domain:
            return _lapse(row, CustomDomain.Reason.NOT_IN_PLAN)
        if row.state == CustomDomain.State.LAPSED:
            return _check_lapsed(row)
        if row.state == CustomDomain.State.PENDING:
            return _check_pending(row)
        return _check_active(row)
    except _DomainMovedOn:
        return "moved_on"
    except edge_client.EdgeUnavailable as error:
        logger.error("hubs.custom_domain.aws domain=%s: %s", row.hostname, error)
        return "aws_unavailable"


def _check_pending(row: CustomDomain) -> str:  # noqa: C901, PLR0911, PLR0912
    """The way to active, step by step and as far as it goes: the certificate, on the listener, the customer's CNAME, the
    snapshot and the probe."""
    target = domain_checks.target_of(row.hub_id)
    try:
        if not row.certificate_arn:
            if not custom_domains.listener_has_room():
                _learned(row, reason=CustomDomain.Reason.QUOTA_FULL)
                return "waiting"
            row = _learned(row, certificate_arn=edge_client.request_certificate(row.hostname, row.certificate_token))
        facts = edge_client.describe_certificate(row.certificate_arn)
        validation = {"validation_name": facts.validation_name, "validation_value": facts.validation_value} if facts.validation_name else {}
        if facts.status == _NOT_ISSUED_YET:
            _learned(row, reason=CustomDomain.Reason.CERTIFICATE_PENDING, **validation)
            return "waiting"
        if facts.status != _ISSUED:
            logger.warning("hubs.custom_domain.certificate domain=%s %s %s", row.hostname, facts.status, facts.failure_reason)
            reason = CustomDomain.Reason.VALIDATION_TIMED_OUT if facts.status == _TIMED_OUT else CustomDomain.Reason.CERTIFICATE_FAILED
            return _lapse(row, reason)
        if not row.attached_at:
            if not custom_domains.listener_has_room():
                _learned(row, reason=CustomDomain.Reason.QUOTA_FULL, **validation)
                return "waiting"
            try:
                edge_client.attach(row.certificate_arn)
            except edge_client.TooManyCertificates:
                logger.error("hubs.custom_domain.listener_full domain=%s", row.hostname)
                _learned(row, reason=CustomDomain.Reason.QUOTA_FULL, **validation)
                return "waiting"
            row = _learned(row, attached=True, **validation)
    except edge_client.EdgeUnavailable as error:
        logger.error("hubs.custom_domain.aws domain=%s: %s", row.hostname, error)
        _learned(row, reason=CustomDomain.Reason.CERTIFICATE_UNAVAILABLE)
        return "aws_unavailable"
    try:
        pointing = domain_checks.points_at(row.hostname, target)
    except domain_checks.DnsUnavailable as error:
        logger.warning("hubs.custom_domain.dns domain=%s: %s", row.hostname, error)
        _learned(row, reason=CustomDomain.Reason.DNS_UNAVAILABLE)
        return "waiting"
    if not pointing:
        if timezone.now() - row.attached_at > CUSTOM_DOMAIN_PENDING_LIMIT:
            return _lapse(row, CustomDomain.Reason.CNAME_MISSING)
        was_in_snapshot = row.in_snapshot
        _learned(row, reason=CustomDomain.Reason.CNAME_MISSING, proven=False)
        if was_in_snapshot:
            sync_hub(row.hub_id)
        return "waiting"
    if row.proven_at is None:
        row = _learned(row, proven=True, reason=CustomDomain.Reason.PROBE_FAILED)
        if row.proven_at is None:
            return "waiting"
    if not sync_hub(row.hub_id):
        return "hub_away"
    if domain_checks.probe(row.hostname, target, row.hub_id) != domain_checks.Probe.SERVED:
        _learned(row, reason=CustomDomain.Reason.PROBE_FAILED)
        return "waiting"
    _learned(row, state=CustomDomain.State.ACTIVE, reason=CustomDomain.Reason.NONE, failures=0)
    logger.info("hubs.custom_domain.active domain=%s hub=%s", row.hostname, row.hub_id)
    return "activated"


def _check_active(row: CustomDomain) -> str:
    """An active domain still has to point here and be served. A question that got no answer says nothing of it."""
    target = domain_checks.target_of(row.hub_id)
    try:
        pointing = domain_checks.points_at(row.hostname, target)
    except domain_checks.DnsUnavailable as error:
        logger.warning("hubs.custom_domain.dns domain=%s: %s", row.hostname, error)
        _learned(row, reason=CustomDomain.Reason.DNS_UNAVAILABLE)
        return "unknown"
    if not pointing:
        return _failed_a_check(row, CustomDomain.Reason.CNAME_MISSING)
    answer = domain_checks.probe(row.hostname, target, row.hub_id)
    if answer == domain_checks.Probe.UNREACHABLE:
        _learned(row, reason=CustomDomain.Reason.PROBE_FAILED)
        return "unknown"
    if answer == domain_checks.Probe.NOT_SERVED:
        return _failed_a_check(row, CustomDomain.Reason.PROBE_FAILED, owe_snapshot=True)
    _learned(row, reason=CustomDomain.Reason.NONE, failures=0)
    return "served"


def _failed_a_check(row: CustomDomain, reason: str, *, owe_snapshot: bool = False) -> str:
    """One failure more; the third in a row and the website stops being served there. ``owe_snapshot``: the Hub says it
    does not know the domain, so it is told again, which is what brings it back if that was all."""
    failures = row.failures + 1
    if failures < CUSTOM_DOMAIN_FAILURES_TO_LAPSE:
        row = _learned(row, reason=reason, failures=failures, owe_snapshot=owe_snapshot)
        if owe_snapshot:
            sync_hub(row.hub_id)
        logger.warning("hubs.custom_domain.failure domain=%s %s of %s", row.hostname, failures, CUSTOM_DOMAIN_FAILURES_TO_LAPSE)
        return "failing"
    return _lapse(row, CustomDomain.Reason.CHECKS_FAILED, tell_the_owner=True)


def _lapse(row: CustomDomain, reason: str, *, tell_the_owner: bool = False) -> str:
    """Out of the snapshot now; its certificate goes as soon as the Hub heard, its place on the listener with it. A
    business that was purged leaves nothing behind."""
    row = _learned(row, state=CustomDomain.State.LAPSED, reason=reason, proven=False, failures=0)
    if tell_the_owner:
        _tell_the_owner_it_lapsed(row)
    outcome = _drop_certificate(row)
    if outcome:
        return outcome
    if row.hub.status == Hub.Status.DELETED:
        _learned(row, forget=True)
        return "gone"
    return "lapsed"


def _tell_the_owner_it_lapsed(row: CustomDomain) -> None:
    owner = HubMember.objects.filter(hub_id=row.hub_id, role=Role.OWNER).select_related("user").first()
    if owner is not None:
        emails.send_custom_domain_lost(row.hub, owner.user, hostname=row.hostname, base_url=emails.base_url(None))


def _check_lapsed(row: CustomDomain) -> str:
    """A certificate still going goes first; then, if the CNAME is back and its reason allows, the way starts again."""
    outcome = _drop_certificate(row)
    if outcome:
        return outcome
    if row.reason not in CustomDomain.RETURNS_BY_ITSELF:
        return "lapsed"
    row = custom_domains.custom_domain_row(row.id)
    try:
        back = domain_checks.points_at(row.hostname, domain_checks.target_of(row.hub_id))
    except domain_checks.DnsUnavailable as error:
        logger.warning("hubs.custom_domain.dns domain=%s: %s", row.hostname, error)
        return "lapsed"
    if not back:
        return "lapsed"
    row = _learned(
        row,
        state=CustomDomain.State.PENDING,
        reason=CustomDomain.Reason.CERTIFICATE_PENDING,
        new_token=True,
        validation_name="",
        validation_value="",
    )
    return _check_pending(row)


def _finish_removal(row: CustomDomain) -> str:
    """The certificate, and the row last: that is what frees the name."""
    outcome = _drop_certificate(row)
    if outcome:
        return outcome
    _learned(row, forget=True)
    return "removed"


def _drop_certificate(row: CustomDomain) -> str:
    """Take the certificate of a domain out of AWS, once the Hub heard it no longer serves it (first the
    snapshot, then the certificate). The empty answer: nothing is left. Otherwise why not yet, for the next pass."""
    if not sync_hub(row.hub_id):
        return "hub_away"
    if not row.certificate_arn:
        return ""
    known_on_the_listener = row.attached_at is not None
    if known_on_the_listener:
        edge_client.detach(row.certificate_arn)
        row = _learned(row, attached=False)
    try:
        edge_client.delete_certificate(row.certificate_arn)
    except edge_client.CertificateInUse:
        logger.info("hubs.custom_domain.certificate_in_use domain=%s", row.hostname)
        if not known_on_the_listener:
            # The ALB may still be letting go, or the pass that attached it lost to the owner or died before writing it:
            # then no row says so, and without this no later pass would ever delete it.
            edge_client.detach(row.certificate_arn)
        return "certificates_in_use"
    _learned(row, certificate_arn="")
    return ""
