"""The local accounts of ``demo_seed``: a customer and a platform administrator, their address proven."""

from django.contrib.auth import get_user_model

from accounts.services.platform_staff import PLATFORM_ADMIN, create_platform_user


def _prove_demo_address(user) -> None:
    """A local account of ``demo_seed`` never owes the code that proves its address, only the sign-in code
    every password sign-in mails (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``): its address is on record, proven, also
    on an account seeded before every account had to prove it (``ACCOUNT_EMAIL_VERIFICATION``)."""
    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=user, email=user.email.lower(), defaults={"verified": True, "primary": True}
    )


def seed_demo_customer(email: str, password: str):
    """Create (or leave as it is) a customer account of ``demo_seed``: never staff, in no hub yet, its
    address proven.

    Its businesses and roles are ``hubs.services.seed_demo_business``'s.
    """
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user = get_user_model().objects.create_user(email=email, password=password)
    _prove_demo_address(user)
    return user


def seed_demo_platform_admin(email: str, password: str):
    """Create (or leave as it is) a platform administrator: superuser of the admin, member of no hub, its
    address proven."""
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user, _ = create_platform_user(email, PLATFORM_ADMIN, password)
    _prove_demo_address(user)
    return user
