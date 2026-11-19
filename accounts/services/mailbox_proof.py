"""Who holds an address: an account whose holder never proved it lets it go, and a reset proves the mailbox."""

import logging

from django.db import transaction

logger = logging.getLogger("accounts.services")


def release_unproven_account(user, *, reason: str) -> None:
    """Strip every credential of an account whose holder never proved its email.

    The address is then reserved by nobody: only whoever opens that mailbox gets in, through «Forgot your
    password?» (or Google, which proves the address), like any invited person. allauth's own defence when
    Google proves an address the account never verified (``socialaccount/internal/flows/
    email_authentication.py``), taken further: that one only wipes the password, and a second factor or a
    linked Google of the squatter's would still let them in, or lock the real owner out at the second step.

    Removes the password (which also ends every browser session of the SaaS: Django checks the session
    against the password hash), every second factor and every linked social account. The account, its
    addresses and what hangs from it stay. Its sessions in the hubs are the caller's to end (``hubs``
    queues a ``SessionRevocation`` of every business).
    """
    from allauth.mfa.models import Authenticator
    from allauth.socialaccount.models import SocialAccount

    with transaction.atomic():
        user.set_unusable_password()
        user.save(update_fields=["password"])
        Authenticator.objects.filter(user=user).delete()
        SocialAccount.objects.filter(user=user).delete()
    logger.warning("accounts.released_unproven_account user=%s reason=%s", user.pk, reason)


def prove_mailbox_by_reset(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``password_reset`` signal: a password set from the key mailed by «Forgot your password?»
    proves the mailbox, so the account's address becomes verified and primary.

    How an account made by an invitation is claimed (its mail links to the reset): allauth's reset leaves
    its address on record unverified, and accepting needs it proved (``queries.ways_in.email_is_proven``). Only
    when the login address is the only one on record: the key goes to the address typed, which may be any
    address of the account, so with another one (a squatter's own, verified) nothing is proven here.
    """
    if user is None:
        return
    from allauth.account.models import EmailAddress

    with transaction.atomic():
        addresses = EmailAddress.objects.select_for_update().filter(user=user)
        if addresses.exclude(email__iexact=user.email).exists():
            return
        address = addresses.first()
        if address is None:
            EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        elif not (address.verified and address.primary):
            address.verified = True
            address.primary = True
            address.save(update_fields=["verified", "primary"])
    logger.info("accounts.reset_proved_the_mailbox user=%s", user.pk)
