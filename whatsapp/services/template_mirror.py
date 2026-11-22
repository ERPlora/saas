"""Doors 8 and 9, the business's templates at Meta and their mirror here.

- ``whatsapp.template.claim`` / ``whatsapp.template.record``: door 8, a template's registration at Meta by its
  ``Idempotency-Key``: a key Meta took answers what it said the first time, never registers again;
- ``whatsapp.template.forget`` / ``whatsapp.template.sync``: the mirror of Meta's templates, after a deletion at
  Meta (door 9) and when Meta's list is read again.
"""

from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from live.context import OperationContext
from live.errors import OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from whatsapp import events, queries
from whatsapp.models import PhoneNumber, Template, TemplateSubmission
from whatsapp.schemas import (
    TemplateClaimIn,
    TemplateClaimOut,
    TemplateForgetIn,
    TemplateForgetOut,
    TemplateRecordIn,
    TemplateRecordOut,
    TemplateSyncIn,
    TemplateSyncOut,
)
from whatsapp.services.channel_snapshot import announce_channel
from whatsapp.services.message_sends import IN_FLIGHT
from whatsapp.services.platform_actor import PERMISSION

#: What the mirror takes of a template (``templates.mirror`` / ``templates.from_meta``), besides its name and language.
MIRRORED = (
    "category", "status", "rejected_reason", "meta_id", "header_format", "header", "body", "body_examples", "footer",
    "buttons", "variables",
)


def template_in_progress() -> OperationError:
    return OperationError(
        "This template is already being registered: retry with the same key.",
        code="whatsapp.template_in_progress",
        status=503,
    )


@operation(
    "whatsapp.template.claim",
    kind="command",
    permission=PERMISSION,
    input=TemplateClaimIn,
    output=TemplateClaimOut,
    ai=INTERNAL,  # hub
)
def template_claim(ctx: OperationContext, data: TemplateClaimIn) -> TemplateClaimOut:
    """Take a template's registration by its key before Meta is called, or answer what Meta said the first time."""
    hub = queries.known_hub(data.hub)
    if hub is None:
        raise queries.unknown_hub()
    existing = TemplateSubmission.objects.select_for_update().filter(hub=hub, idempotency_key=data.key).first()
    if existing is not None and existing.state == TemplateSubmission.State.DONE:
        return TemplateClaimOut(
            outcome="done", submission_id=existing.id, hub_id=hub.id, meta_id=existing.meta_id, status=existing.status
        )
    if existing is not None and existing.updated_at > timezone.now() - IN_FLIGHT:
        raise template_in_progress()
    number = PhoneNumber.objects.filter(hub=hub, is_active=True).first()
    if number is None or not number.access_token:
        raise queries.not_connected()
    if existing is not None:
        # An earlier call with this key died on its way: this one registers it.
        existing.save(update_fields=["updated_at"])
        submission = existing
    else:
        try:
            with transaction.atomic():
                submission = TemplateSubmission.objects.create(hub=hub, idempotency_key=data.key)
        except IntegrityError:
            raise template_in_progress() from None
    return TemplateClaimOut(
        outcome="claimed", submission_id=submission.id, hub_id=hub.id, waba_id=number.waba_id, token=number.access_token
    )


@operation(
    "whatsapp.template.record",
    kind="command",
    permission=PERMISSION,
    input=TemplateRecordIn,
    output=TemplateRecordOut,
    ai=INTERNAL,  # hub
)
def template_record(ctx: OperationContext, data: TemplateRecordIn) -> TemplateRecordOut:
    """How Meta ended a claimed registration: taken (the mirror keeps it, the Hub learns it) or not (the key is
    forgotten, free to try again)."""
    submission = TemplateSubmission.objects.select_for_update().filter(pk=data.submission_id).first()
    if submission is None:
        return TemplateRecordOut(outcome="gone")
    if data.outcome == "released":
        submission.delete()
        return TemplateRecordOut(outcome="released")
    submission.state = TemplateSubmission.State.DONE
    submission.meta_id = str(data.mirror.get("meta_id") or "")
    submission.status = str(data.mirror.get("status") or "")
    submission.save(update_fields=["state", "meta_id", "status", "updated_at"])
    _mirror(submission.hub_id, data.mirror)
    announce_channel(submission.hub_id)
    record_event(
        ctx,
        events.TEMPLATE_REGISTERED,
        {"hub_id": str(submission.hub_id), "meta_id": submission.meta_id, "status": submission.status},
    )
    return TemplateRecordOut(outcome="done")


@operation(
    "whatsapp.template.forget",
    kind="command",
    permission=PERMISSION,
    input=TemplateForgetIn,
    output=TemplateForgetOut,
    ai=INTERNAL,  # hub
)
def template_forget(ctx: OperationContext, data: TemplateForgetIn) -> TemplateForgetOut:
    """That one template, in that language, leaves the mirror: Meta deleted it or no longer has it."""
    deleted, _ = Template.objects.filter(hub_id=data.hub_id, name=data.name, language=data.language).delete()
    if deleted:
        announce_channel(data.hub_id)
        record_event(ctx, events.TEMPLATE_FORGOTTEN, {"hub_id": str(data.hub_id)})
    return TemplateForgetOut(forgotten=bool(deleted))


@operation(
    "whatsapp.template.sync",
    kind="command",
    permission=PERMISSION,
    input=TemplateSyncIn,
    output=TemplateSyncOut,
    ai=INTERNAL,  # hub
)
def template_sync(ctx: OperationContext, data: TemplateSyncIn) -> TemplateSyncOut:
    """Write Meta's list of the business's templates on the mirror. What the list lacks is deleted only when it came
    whole: a list cut short says nothing of what it did not reach."""
    seen: set[tuple[str, str]] = set()
    changed = False
    for item in data.items:
        seen.add((item["name"], item["language"]))
        changed = _mirror(data.hub_id, item) or changed
    if data.complete:
        rows = Template.objects.filter(hub_id=data.hub_id).values_list("pk", "name", "language")
        lost = [pk for pk, name, language in rows if (name, language) not in seen]
        if lost:
            Template.objects.filter(pk__in=lost).delete()
            changed = True
    if changed:
        announce_channel(data.hub_id)
    record_event(ctx, events.TEMPLATES_SYNCED, {"hub_id": str(data.hub_id), "complete": data.complete})
    return TemplateSyncOut(changed=changed)


def _mirror(hub_id: UUID, item: dict) -> bool:
    """Keep ``item`` (a template as the mirror keeps it) for the business; whether anything changed."""
    values = {name: item[name] for name in MIRRORED if name in item}
    named = Template.objects.select_for_update().filter(hub_id=hub_id, name=item["name"], language=item["language"])
    row = named.first()
    if row is None:
        Template.objects.create(hub_id=hub_id, name=item["name"], language=item["language"], **values)
        return True
    if all(getattr(row, name) == value for name, value in values.items()):
        return False
    for name, value in values.items():
        setattr(row, name, value)
    row.save()
    return True
