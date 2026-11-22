"""ERPlora's stamp and signature as representative: the staff upload it or remove it, and the models carry it."""

import base64
import binascii
import io

from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event
from PIL import Image, UnidentifiedImageError

from base.refusals import fields_refused
from fiscal import crypto, events
from fiscal.models import RepresentativeStamp
from fiscal.schemas import StampDeleteIn, StampDeleteOut, StampOut, StampUploadIn
from fiscal.services.staff_gate import _staff_with

#: The Django permission that lets a member of the staff change ERPlora's stamp (``fiscal.admin``'s stamp page asks it).
STAMP_PERMISSION = "fiscal.change_representativestamp"
#: The largest stamp kept: it is a stamp and a signature, not a photograph, and it goes in every model.
MAX_STAMP_BYTES = 2 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# --- ERPlora's stamp as representative (FISCAL-F06) ----------------------------------------------------


@operation(
    "fiscal.stamp.upload",
    kind="command",
    permission="fiscal.manage",
    input=StampUploadIn,
    output=StampOut,
    ai=INTERNAL,  # staff
)
def stamp_upload(ctx: OperationContext, data: StampUploadIn) -> dict:
    """A member of the staff with ``STAMP_PERMISSION`` uploads ERPlora's stamp and signature: every model a
    business downloads from now on carries it (``fiscal.anexo``). It replaces the one there was; kept encrypted."""
    user = _staff_with(ctx, STAMP_PERMISSION)
    with translation.override(ctx.language):
        png = _checked_stamp(data.png_base64)
    now = timezone.now()
    RepresentativeStamp.objects.update_or_create(
        slot=RepresentativeStamp.SLOT,
        defaults={
            "image": crypto.encrypt(png),
            "size": len(png),
            "uploaded_at": now,
            "uploaded_by": user,
        },
    )
    record_event(ctx, events.STAMP_CHANGED, {"size": len(png)})
    return {"uploaded_at": now, "size": len(png)}


@operation(
    "fiscal.stamp.delete",
    kind="command",
    permission="fiscal.manage",
    input=StampDeleteIn,
    output=StampDeleteOut,
    ai=INTERNAL,  # staff
)
def stamp_delete(ctx: OperationContext, data: StampDeleteIn) -> dict:
    """A member of the staff with ``STAMP_PERMISSION`` removes ERPlora's stamp: the models go without it until
    another is uploaded (the admin says so). 404 when there is none."""
    _staff_with(ctx, STAMP_PERMISSION)
    deleted, _rows = RepresentativeStamp.objects.filter(
        slot=RepresentativeStamp.SLOT
    ).delete()
    if not deleted:
        raise NotFound(_("There is no stamp to remove."), code="fiscal.no_stamp")
    record_event(ctx, events.STAMP_CHANGED, {"size": 0})
    return {"deleted": True}


def _checked_stamp(value: str) -> bytes:
    """The PNG ``value`` holds in base64, or ``InvalidPayload`` saying why it is not one the model can carry."""

    def refused(code: str, message: str) -> InvalidPayload:
        return fields_refused({"png_base64": message}, code=code)

    not_png = refused(
        "fiscal.stamp_not_png", _("The stamp must be a PNG image.")
    )
    value = "".join(value.split())
    if not value:
        raise refused("fiscal.stamp_required", _("Choose the PNG file of the stamp."))
    if len(value) > 4 * -(-MAX_STAMP_BYTES // 3):
        raise _stamp_too_large(refused)
    try:
        png = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        raise not_png from None
    if not png:
        raise refused("fiscal.stamp_required", _("Choose the PNG file of the stamp."))
    if len(png) > MAX_STAMP_BYTES:
        raise _stamp_too_large(refused)
    if not png.startswith(PNG_MAGIC):
        raise not_png
    try:
        with Image.open(io.BytesIO(png)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise not_png from None
    return png


def _stamp_too_large(refused) -> InvalidPayload:
    return refused(
        "fiscal.stamp_too_large",
        _("The stamp may be %(megabytes)d MB at most.")
        % {"megabytes": MAX_STAMP_BYTES // (1024 * 1024)},
    )
