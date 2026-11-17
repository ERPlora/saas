"""The terms and privacy policy an account accepts as it signs up or signs in."""

import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import PRIVACY_VERSION, TERMS_VERSION

logger = logging.getLogger("accounts.services")


def accept_legal_texts(sender, request=None, user=None, **kwargs) -> None:
    """allauth's ``user_signed_up`` and Django's ``user_logged_in``: the account accepts today's terms and privacy
    policy. Creating the account and signing in happen under «By continuing you agree to our Terms &
    Privacy Policy» (the launcher, Google's button too), so each records when and which versions
    (``models.TERMS_VERSION``, ``PRIVACY_VERSION``) unless the account already accepted those: the first date stays.
    Not a session opened by a pass from a business (``accounts.hub_pass``): nobody saw that line on the way."""
    if getattr(request, "hub_pass", None) is not None:
        return
    if user is None or (user.terms_version, user.privacy_version) == (TERMS_VERSION, PRIVACY_VERSION):
        return
    accepted = {"terms_accepted_at": timezone.now(), "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION}
    get_user_model().objects.filter(pk=user.pk).update(**accepted)
    for field, value in accepted.items():
        setattr(user, field, value)
    logger.info("accounts.legal_texts_accepted user=%s terms=%s privacy=%s", user.pk, TERMS_VERSION, PRIVACY_VERSION)
