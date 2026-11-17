"""Account → Profile → «Change photo»."""

from django.utils.translation import gettext
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from accounts import events, photos, queries
from accounts.models import ProfilePhoto
from accounts.schemas import PhotoRemoveIn, PhotoUploadIn, ProfileOut
from accounts.services.attempt_limits import _spent, too_many_attempts
from base.refusals import fields_refused


def _photo_refusal(code: str) -> str:
    return {
        "unsupported": gettext("Upload a JPEG, PNG or WebP image."),
        "too_large": gettext("The photo is too big: at most %(size)s KB. Try a smaller one.")
        % {"size": photos.MAX_PHOTO_BYTES // 1000},
        "dimensions": gettext("The photo is too large: at most %(side)s × %(side)s pixels.") % {"side": photos.MAX_SIDE},
        "animated": gettext("Upload a still image, not an animation."),
    }.get(code, gettext("The image could not be read. Try another one."))


@operation(
    "accounts.photo.upload",
    kind="command",
    permission="accounts.manage",
    input=PhotoUploadIn,
    output=ProfileOut,
    repeatable=True,  # Its database, and its upload once per request (_spent): a cut before the COMMIT runs it again.
    ai=INTERNAL,  # file
)
def photo_upload(ctx: OperationContext, data: PhotoUploadIn) -> dict:
    """Keep the account's photo, cleaned (``accounts.photos``), in place of the one it had."""
    user = queries.account_of(ctx)
    try:
        cleaned, content_type = photos.clean_photo(photos.decode_upload(data.image))
    except photos.PhotoRejected as refused:
        raise fields_refused({"image": _photo_refusal(refused.code)}) from None
    if _spent(ctx.request, f"{photos.UPLOADS_PER_HOUR}/h", "accounts.photo.upload", f"user:{user.pk}"):
        raise too_many_attempts()
    ProfilePhoto.objects.update_or_create(user=user, defaults={"content_type": content_type, "data": cleaned})
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)


@operation(
    "accounts.photo.remove",
    kind="command",
    permission="accounts.manage",
    input=PhotoRemoveIn,
    output=ProfileOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=INTERNAL,  # file
)
def photo_remove(ctx: OperationContext, data: PhotoRemoveIn) -> dict:
    """Remove the account's photo (the panel paints its initials). Without one, nothing changes."""
    user = queries.account_of(ctx)
    ProfilePhoto.objects.filter(user=user).delete()
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)
