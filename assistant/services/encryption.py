"""The key WhatsApp's tokens and PINs are kept with (``FERNET_KEY``); the AI providers' keys live in the environment.

- ``assistant.encryption.rotate``: every value kept with ``FERNET_KEY`` (``encrypted_columns``: today WhatsApp's tokens
  and PINs) written again with the current key, so the previous one can go.
- A write that needs the key while it is not configured answers 503 ``assistant.encryption_not_configured``.
"""

from django.apps import apps
from django.db.models import TextField, Value
from django.db.models.functions import Cast
from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import OperationError, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

import whatsapp.fields
from assistant import crypto, events
from assistant.schemas import EncryptionRotateIn, EncryptionRotateOut


def _encryption_missing(ctx: OperationContext) -> OperationError:
    with translation.override(ctx.language):
        return OperationError(
            _("The key of the credentials is not configured: nothing can be rotated."),
            code="assistant.encryption_not_configured",
            status=503,
        )


#: The field classes whose columns keep their value with ``FERNET_KEY`` (MultiFernet with ``FERNET_KEY_PREVIOUS``),
#: all rotated together. A new encrypted field class goes here, or the guard of the tests fails. The fiscal
#: documents are kept with their own key (``FISCAL_DOCUMENTS_KEY``, ``fiscal.crypto``) and are not rotated here.
ROTATED_FIELD_CLASSES = (whatsapp.fields.EncryptedTextField,)


def encrypted_columns() -> list[tuple[type, str]]:
    """Every ``(model, field name)`` kept with ``FERNET_KEY``, derived from the models (never a hand-written list)."""
    found = [
        (model, field.name)
        for model in apps.get_models()
        for field in model._meta.concrete_fields
        if type(field) in ROTATED_FIELD_CLASSES
    ]
    return sorted(found, key=lambda column: (column[0]._meta.label, column[1]))


@operation(
    "assistant.encryption.rotate",
    kind="command",
    permission="assistant.manage",
    input=EncryptionRotateIn,
    output=EncryptionRotateOut,
    ai=INTERNAL,  # staff
)
def encryption_rotate(ctx: OperationContext, data: EncryptionRotateIn) -> dict:
    """Write every value kept with ``FERNET_KEY`` again with the current key (``rotate_encryption_keys``, the
    platform only). Each token is rotated as it is, without the value leaving ``assistant.crypto`` nor the row being
    saved (no date of the row moves); one already of the current key is left alone, and one no live key opens is
    never written and is reported. ``dry_run`` counts and writes nothing. 503 ``assistant.encryption_not_configured``."""
    if ctx.actor != "system":
        with translation.override(ctx.language):
            raise PermissionDenied(_("Only the platform rotates the key of the credentials."), code="assistant.platform_only")
    if not crypto.configured():
        raise _encryption_missing(ctx)
    columns = []
    for model, name in encrypted_columns():
        rotated, current, unreadable = 0, 0, []
        rows = model._default_manager.annotate(token=Cast(name, TextField())).exclude(token="").values_list("pk", "token")
        for pk, token in rows.order_by("pk"):
            if crypto.is_current(token):
                current += 1
                continue
            try:
                fresh = crypto.rotate(token)
            except crypto.Undecryptable:
                unreadable.append(str(pk))
                continue
            rotated += 1
            if not data.dry_run:
                model._default_manager.filter(pk=pk).update(**{name: Value(fresh, output_field=TextField())})
        columns.append(
            {"column": f"{model._meta.label}.{name}", "rotated": rotated, "current": current, "unreadable": unreadable}
        )
    totals = {
        "rotated": sum(column["rotated"] for column in columns),
        "current": sum(column["current"] for column in columns),
        "unreadable": sum(len(column["unreadable"]) for column in columns),
    }
    if not data.dry_run:
        record_event(ctx, events.ENCRYPTION_ROTATED, totals)
    return {"columns": columns, **totals}
