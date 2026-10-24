"""The messages L1-A2 added to hubs reach a Spanish account in Spanish (UI in ``en`` + ``es``, PLAN §5).

Read through Django's catalog of the app (``hubs/locale/es/LC_MESSAGES/django.mo``), so a ``.po`` edited
without compiling it fails too.
"""

import pytest
from django.utils import translation
from django.utils.translation import gettext, ngettext

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
    # L2-B: what Stripe says of the plan (hubs.subscription.apply) and the payer's postal code.
    "Only the platform applies what Stripe says.",
    "There is no plan with this identifier.",
    "A Spanish postal code has five digits, e.g. 28001.",
    "Paid",
    "Card declined",
    "Card changed",
    "Authentication required",
    "Payment failed",
    "why it is unpaid",
    "unpaid since",
    "invoice to pay",
    # L4-A: the usage of a business (HubUsageDaily, hubs.usage.*) and its admin.
    "day",
    "files (bytes)",
    "database (bytes)",
    "active that day",
    "active in the 30 days",
    "collected at",
    "daily usage",
    "daily usages",
    "Only the platform records the usage of a business.",
    "No usage of this business has been measured yet: the first figures arrive the night after it is created.",
    "Files",
    "Database",
    # 2026-10-15: the monthly messages of a plan (Plan and its admin).
    "AI assistant messages a month",
    "WhatsApp messages a month",
    "Requests to the AI assistant a business may make each month (0 = none).",
    "WhatsApp messages a business may send each month (0 = none).",
    "AI assistant and WhatsApp per month",
    # models.py: Plan.max_apps (2026-10-24)
    "modules turned on",
    "Modules a business may choose to turn on; the ones they require do not count (0 = unlimited).",
    # HUBS-F01 (HUBS-G65): the refusals of the sign-up of a business, which a Spanish account reads.
    "Businesses cannot be created right now. Try again in a few minutes.",
    "You already have a free business. Change its plan to create another one.",
    "This address belongs to ERPlora's staff and cannot join a business.",
    # HUBS-F04, HUBS-F07: «your business is ready» (emails.send_ready).
    "%(business)s is ready",
    "%(business)s is ready: open it and start selling.",
    "Open it: %(url)s",
    "Manage it from the panel: %(url)s",
]


@pytest.mark.parametrize("message", NEW_MESSAGES)
def test_each_new_message_has_its_spanish(message):
    with translation.override("es"):
        spanish = gettext(message)

    assert spanish != message
    assert spanish.count("%(count)d") == message.count("%(count)d")


#: HUBS-F31: the admin's notice when what a plan gives changes (``PlanAdmin.save_model``), singular and plural.
PLAN_RIGHTS_NOTICE = (
    "%(count)d business on this plan gets the change within 15 minutes.",
    "%(count)d businesses on this plan get the change within 15 minutes.",
)


#: HUBS-F34: the same notice in the modules' admin (``apps.admin.ModuleAdmin.save_model``, the catalog of ``apps``).
MODULE_RIGHTS_NOTICE = (
    "%(count)d business whose plan includes it gets the change within 15 minutes.",
    "%(count)d businesses whose plan includes it get the change within 15 minutes.",
)


@pytest.mark.parametrize("notice", [PLAN_RIGHTS_NOTICE, MODULE_RIGHTS_NOTICE], ids=["plan", "module"])
@pytest.mark.parametrize("count", [1, 2])
def test_the_notice_of_a_plan_change_has_its_spanish(count, notice):
    with translation.override("es"):
        spanish = ngettext(*notice, count)

    assert spanish not in notice
    assert spanish.count("%(count)d") == 1


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
