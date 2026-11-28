"""Account → Profile → «Change» the email: a code mailed to the new address, typed in the same session."""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime
from functools import partial

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from accounts import emails, events
from accounts.models import EmailChangeRequest
from accounts.queries import account_lookup, account_profile, account_sessions, ways_in
from accounts.schemas import EmailChangeIn, EmailVerifyIn, EmailVerifyOut, ProfileOut
from accounts.services.attempt_limits import _spent, too_many_attempts
from accounts.services.reauthentication import require_recent_authentication
from base.refusals import fields_refused

logger = logging.getLogger("accounts.services")


def _email_refused(message: str) -> InvalidPayload:
    return fields_refused({"email": message})


def email_belongs_to_another_account(user, email: str) -> bool:
    """Whether another account answers to ``email``, in any letter case: its sign-in email or an address on
    record. allauth's own lookup matches the lowercased address, and older accounts keep their capitals."""
    from allauth.account.models import EmailAddress

    return (
        get_user_model().objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
        or EmailAddress.objects.filter(email__iexact=email).exclude(user=user).exists()
    )


#: Tries a code has (a wrong one each), counted in the database.
EMAIL_CODE_ATTEMPTS = 3
#: Seconds before asking again for the same address sends a new code (a double click sends one).
EMAIL_CODE_RESEND_AFTER = 60
#: Tries an account may make, whatever the code (django-ratelimit, over the cache).
EMAIL_CODE_TRIES_PER_MINUTE = "5/m"
EMAIL_CODE_TRIES_PER_HOUR = "20/h"
#: Codes an address may get, whoever asks for them: nobody's inbox to flood.
EMAIL_CODES_PER_ADDRESS = "3/h"


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _typed_email(request, value: str) -> str:
    """``value`` as the account would keep it (allauth's cleaning folds it to its plain form), or a 422 on the email:
    an address as typed, and one that fits the account."""
    from allauth.account.adapter import get_adapter
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = value.strip().lower()
    try:
        validate_email(email)
        email = get_adapter(request).clean_email(email)
    except ValidationError:
        raise _email_refused(gettext("Enter a valid email address.")) from None
    if len(email) > get_user_model()._meta.get_field("email").max_length:
        raise _email_refused(gettext("Enter a valid email address."))
    return email


def _no_email_change() -> Conflict:
    return Conflict(
        gettext("There is no change of email waiting for a code: ask for a new one."), code="accounts.no_email_change"
    )


@operation(
    "accounts.email.change",
    kind="command",
    permission="accounts.manage",
    input=EmailChangeIn,
    output=ProfileOut,
    ai=INTERNAL,  # reauthentication
)
def email_change(ctx: OperationContext, data: EmailChangeIn) -> dict:
    """Mail a 6-digit code to the new address; the account switches to it once the code is typed in this same
    session (``accounts.email.verify``), and until then it keeps answering to the old one. The change
    waits in ``EmailChangeRequest`` (bound to this session, the code kept as its hash). The account's own address,
    if it never proved it, is proven the same way.

    For another address, a password first (409 ``accounts.password_required``: without one, the session alone
    would change it) and a recent sign-in (401); a code to the account's own address hands nothing over and asks
    for neither. Always allauth's budget for an account's addresses (429 ``accounts.too_many_attempts``) and three
    codes an hour per address (429 ``accounts.too_many_codes``).
    """
    from allauth.core import ratelimit

    user = account_lookup.account_of(ctx)
    if data.email.strip().lower() != user.email.lower():
        if not user.has_usable_password():
            raise Conflict(
                gettext(
                    "Your account has no password yet: set one with «Forgot your password?» before changing your email."
                ),
                code="accounts.password_required",
            )
        require_recent_authentication(ctx)
    request = ctx.request
    if not ratelimit.consume(request, action="manage_email", user=user):
        raise too_many_attempts()
    email = _typed_email(request, data.email)
    if email == user.email.lower() and ways_in.email_is_proven(user, user.email):
        raise _email_refused(gettext("That is already your email."))
    if email_belongs_to_another_account(user, email):
        raise _email_refused(gettext("This email is already used by another account."))
    pending = account_profile.email_change_of(user, request)
    if (
        pending is not None
        and pending.email == email
        and time.time() - pending.created_at.timestamp() < EMAIL_CODE_RESEND_AFTER
    ):
        return account_profile.profile_of(user, request)
    if _spent(request, EMAIL_CODES_PER_ADDRESS, "accounts.email_code.address", f"to:{email}"):
        raise OperationError(
            gettext("That address already got several codes in the last hour: try again later."),
            code="accounts.too_many_codes",
            status=429,
        )
    code = _new_code()
    EmailChangeRequest.objects.update_or_create(
        user=user,
        defaults={
            "session_key": account_sessions.current_session_key(request),
            "email": email,
            "code_hash": _hash_code(code),
            "attempts": 0,
            "created_at": datetime.fromtimestamp(time.time(), tz=UTC),
        },
    )
    if not emails.send_email_code(email, code, language=user.language):
        raise OperationError(
            gettext("We could not send the code. Please try again in a few minutes."),
            code="accounts.code_not_sent",
            status=503,
        )
    logger.info("accounts.email_code_sent user=%s", user.pk)
    record_event(ctx, events.EMAIL_CHANGE_REQUESTED)
    return account_profile.profile_of(user, request)


def _spend_a_try(request, user, change: EmailChangeRequest) -> int:
    """Spend one try of ``change`` before its code is compared, and say how many it has spent: within the account's
    budget a minute and an hour (429), and one conditional ``UPDATE`` that two requests at once cannot both pass
    on the last try."""
    from django.db.models import F

    for rate in (EMAIL_CODE_TRIES_PER_MINUTE, EMAIL_CODE_TRIES_PER_HOUR):
        if _spent(request, rate, f"accounts.email_code.tries.{rate}", f"user:{user.pk}"):
            raise too_many_attempts()
    tries = EmailChangeRequest.objects.filter(pk=change.pk, attempts__lt=EMAIL_CODE_ATTEMPTS)
    if not tries.update(attempts=F("attempts") + 1):
        EmailChangeRequest.objects.filter(pk=change.pk).delete()
        raise _no_email_change()
    return EmailChangeRequest.objects.filter(pk=change.pk).values_list("attempts", flat=True).get()


@operation(
    "accounts.email.verify",
    kind="command",
    permission="accounts.manage",
    input=EmailVerifyIn,
    output=EmailVerifyOut,
    repeatable=True,  # Its database, and its tries once per request (_spent): a cut before the COMMIT runs it again.
    ai=INTERNAL,  # reauthentication
)
def email_verify(ctx: OperationContext, data: EmailVerifyIn) -> dict:
    """The code mailed by ``accounts.email.change``, typed in the session that asked for it: the account answers to
    the new address from now on, proven (its only address on record), and the old one is told.

    Each try is consumed by one conditional ``UPDATE`` before the code is compared, and a wrong code answers
    ``verified: false`` (not an error, which would roll the spent try back); the third wrong one ends the change.
    An account has a budget of tries a minute and an hour besides (429). An address another account took meanwhile
    is refused (409 ``accounts.email_taken``), also when the database finds it first. allauth's ``email_changed``
    is sent, for whoever keeps a copy of the address.
    """
    from allauth.account.models import EmailAddress
    from allauth.account.signals import email_changed
    from django.db import IntegrityError

    user = account_lookup.account_of(ctx)
    request = ctx.request
    change = account_profile.email_change_of(user, request)
    if change is None:
        raise _no_email_change()
    attempts = _spend_a_try(request, user, change)
    if not hmac.compare_digest(change.code_hash, _hash_code(data.code.strip())):
        left = max(EMAIL_CODE_ATTEMPTS - attempts, 0)
        if not left:
            EmailChangeRequest.objects.filter(pk=change.pk).delete()
        return {"verified": False, "attempts_left": left, "profile": account_profile.profile_of(user, request)}
    email = change.email
    if email_belongs_to_another_account(user, email):
        raise Conflict(gettext("This email is already used by another account."), code="accounts.email_taken")
    # Read again: ``ctx.actor`` is the request's account, which a try a cut rolled back changed in memory (repeatable).
    user.refresh_from_db(fields=["email"])
    old_email = user.email
    previous = EmailAddress.objects.filter(user=user, email__iexact=old_email).first()
    changed = email != old_email.lower()
    try:
        with transaction.atomic():
            EmailAddress.objects.filter(user=user).exclude(email__iexact=email).delete()
            address, _ = EmailAddress.objects.update_or_create(
                user=user, email__iexact=email, defaults={"email": email, "verified": True, "primary": True}
            )
            if changed:
                user.email = email
                user.save(update_fields=["email"])
            EmailChangeRequest.objects.filter(pk=change.pk).delete()
    except IntegrityError:
        raise Conflict(
            gettext("This email is already used by another account."), code="accounts.email_taken"
        ) from None
    if changed:
        email_changed.send(
            sender=EmailAddress, request=request, user=user, from_email_address=previous, to_email_address=address
        )
        transaction.on_commit(partial(emails.send_email_changed, old_email, email, language=user.language), robust=True)
    logger.info("accounts.email_verified user=%s changed=%s", user.pk, changed)
    record_event(ctx, events.PROFILE_UPDATED)
    return {
        "verified": True,
        "attempts_left": max(EMAIL_CODE_ATTEMPTS - attempts, 0),
        "profile": account_profile.profile_of(user, request),
    }
