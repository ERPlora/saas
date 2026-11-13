"""The messages of hubs reach a Spanish account in Spanish.

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
    # What Stripe says of the plan (hubs.subscription.apply) and the payer's postal code.
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
    # The usage of a business (HubUsageDaily, hubs.usage.*) and its admin.
    "day",
    "files (bytes)",
    "database (bytes)",
    "active that day",
    "active in the 30 days",
    # What the Hub measures during the day, in the admin.
    "requests",
    "peak connections",
    "requests with no room",
    "collected at",
    "daily usage",
    "daily usages",
    "Only the platform records the usage of a business.",
    "No usage of this business has been measured yet: the first figures arrive the night after it is created.",
    "Files",
    "Database",
    # The monthly messages of a plan (Plan and its admin).
    "AI assistant messages a month",
    "WhatsApp messages a month",
    "Requests to the AI assistant a business may make each month (0 = none).",
    "WhatsApp messages a business may send each month (0 = none).",
    "AI assistant and WhatsApp per month",
    # models.py: Plan.max_apps
    "modules turned on",
    "Modules a business may choose to turn on; the ones they require do not count (0 = unlimited).",
    # HUBS-F01: the refusals of the sign-up of a business, which a Spanish account reads.
    "Businesses cannot be created right now. Try again in a few minutes.",
    "You already have a free business. Change its plan to create another one.",
    "This address belongs to ERPlora's staff and cannot join a business.",
    # HUBS-F04, HUBS-F07: «your business is ready» (emails.send_ready).
    "%(business)s is ready",
    "%(business)s is ready: open it and start selling.",
    "Open it: %(url)s",
    "Manage it from the panel: %(url)s",
    # The copies of a business's data: the deletion's way to them, the mail when one
    # is ready (emails.py) and the refusals of a download (queries.data_copy_link).
    "Download a full copy of its data: %(url)s",
    "The copy of the data of %(business)s is ready",
    "The full copy of the data of %(business)s is ready.",
    "Download it from %(url)s until %(date)s.",
    "The copy cannot be downloaded right now. Try again in a moment.",
    "This copy of the data is no longer kept.",
    "copy of the data announced at",
    "tries of the copy's mail",
    "The copy of the data could not be checked right now. Try again in a moment.",
    # admin.py and templates/admin/hubs: «Hubs», which moved here with the jump's read (saas#199).
    "Hub admin",
    "Members",
    "No hub has members yet.",
    # A business's own domain (HUBS-F17): its states and reasons, its refusals and the mail that it stopped being served.
    "Waiting for your records",
    "Connected",
    "Not connected",
    "Being removed",
    "Create the validation record: the certificate is waiting for it.",
    "The certificate could not be asked for now. We will try again within the hour.",
    "The certificate was refused for this domain. Check that its CAA records allow amazon.com, and ask for the domain again.",
    "The validation record did not appear in 72 hours. Create it and ask for the domain again.",
    "There is no room for more domains right now. We will try again every hour.",
    "Create the record that points your domain at ERPlora.",
    "The records of your domain could not be read now. We will try again within the hour.",
    "Your domain points at ERPlora, but it is not being served yet. We will try again within the hour.",
    "Another business is connected to this domain.",
    "Your domain stopped pointing at ERPlora, so your website is no longer served on it. It comes back by itself when the record does.",
    "Your plan does not include an own domain.",
    "This business was deleted.",
    "domain",
    "state",
    "reason",
    "certificate token",
    "certificate",
    "on the listener since",
    "validation record",
    "validation value",
    "proved at",
    "connected at",
    "failures in a row",
    "checked at",
    "own domain",
    "own domains",
    "Own domains are not available yet.",
    "Write only the domain, like www.yourbusiness.com.",
    "That domain belongs to ERPlora. Write your own.",
    "A root domain cannot point at ERPlora. Connect www and redirect the root to it at your provider.",
    "Nobody has registered that domain yet.",
    "The plan of this business does not include an own domain.",
    "This business already has a domain. Remove it first.",
    "Only the platform records what its check learned.",
    "Your domain %(domain)s is no longer connected",
    "%(domain)s stopped pointing at %(business)s on ERPlora, so its website is no longer served on that domain.",
    "Everything else keeps working at its address on erplora.com.",
    "It comes back by itself within the hour once the record is back. The records are here: %(url)s",
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


@pytest.mark.parametrize(
    ("source", "spanish"),
    [
        ("requests", "peticiones"),
        ("peak connections", "pico de conexiones"),
        # The words of the Hub's own screen (BASE-F40): the same figure is called the same on both sides.
        ("requests with no room", "peticiones sin hueco"),
    ],
)
def test_the_figures_of_the_day_read_as_the_hub_says_them(source, spanish):
    with translation.override("es"):
        assert gettext(source) == spanish
