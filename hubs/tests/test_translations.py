"""The messages L1-A2 added to hubs reach a Spanish account in Spanish (UI in ``en`` + ``es``, PLAN §5).

Read through Django's catalog of the app (``hubs/locale/es/LC_MESSAGES/django.mo``), so a ``.po`` edited
without compiling it fails too.
"""

import pytest
from django.utils import translation
from django.utils.translation import gettext

NEW_MESSAGES = [
    # services.py
    "Confirm your email address before accepting the invitation.",
    "Only the platform tells the people of a business.",
    # models.py: SessionRevocation
    "account",
    "Empty: every business of the account.",
    "requested at",
    "delivered at",
    "attempts",
    "next attempt at",
    "last error",
    "session revocation",
    "session revocations",
    # admin.py: the platform's actions
    "Send the latest state to the Hub",
    "Retry what the Hub still owes",
    "%(count)d business(es) up to date in the Hub.",
    "%(count)d business(es) still owed: the Hub is away or refused it (see its last refusal); "
    "reconcile_hub_states retries it.",
    "End the sessions in the Hub now",
    "%(count)d session end(s) delivered.",
    "%(count)d session end(s) still pending: the Hub is away or refused it; reconcile_hub_states retries it.",
]


@pytest.mark.parametrize("message", NEW_MESSAGES)
def test_each_new_message_has_its_spanish(message):
    with translation.override("es"):
        spanish = gettext(message)

    assert spanish != message
    assert spanish.count("%(count)d") == message.count("%(count)d")


@pytest.mark.django_db
def test_the_unconfirmed_refusal_is_said_in_spanish(business, owner):
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from live.errors import PermissionDenied

    from hubs import services
    from hubs.models import HubMember
    from hubs.schemas import ByIdIn
    from hubs.tests.conftest import ctx_for

    ana = get_user_model().objects.create_user(email="ana@example.com", password=None)
    EmailAddress.objects.create(user=ana, email=ana.email, primary=True, verified=False)
    member = HubMember.objects.create(hub=business, user=ana, role="hub_employee")

    with translation.override("es"), pytest.raises(PermissionDenied) as refused:
        services.invitation_accept(ctx_for(ana, language="es"), ByIdIn(id=member.id))

    assert refused.value.message == "Confirma tu correo electrónico antes de aceptar la invitación."
