"""How an account gets in: whether it proved its email, the providers it signs in with, and whether it has no
way in yet (the invitation of ``hubs``)."""

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount


def email_is_proven(user, email: str) -> bool:
    """Whether ``user`` holds ``email`` by proof rather than by having typed it first.

    Proven means a **verified** ``EmailAddress`` for that address (another verified address proves
    nothing). Two kinds of account have nothing to prove and count as proven: staff, and an account with
    **no** address on record (made by an invitation, which leaves no password until the mailbox's owner
    claims it, by the console or by staff).
    """
    if user.is_staff or user.is_superuser:
        return True
    addresses = EmailAddress.objects.filter(user=user)
    if not addresses.exists():
        return True
    return addresses.filter(email__iexact=email, verified=True).exists()


def linked_providers(user) -> list[str]:
    """The providers the account signs in with (``google``), alphabetically."""
    return sorted(set(SocialAccount.objects.filter(user=user).values_list("provider", flat=True)))


def has_no_way_in(user) -> bool:
    """Whether ``user`` has no way to sign in yet: no usable password and no linked Google. Whoever opens
    its mailbox claims it with «Forgot your password?» or with Google (the invitation's mail says so)."""
    return not user.has_usable_password() and not SocialAccount.objects.filter(user=user).exists()
