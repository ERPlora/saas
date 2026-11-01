"""``manage.py create_platform_user <email> --role admin|support``: the platform's staff, from the console.

Platform users are created only here or in the SaaS admin: ``admin`` is a superuser (staff),
``support`` is staff in the ``support`` group (view only). Running it again on the same email
updates the role. A customer of a hub is never turned into platform staff.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command

from accounts.models import HubMembership

pytestmark = pytest.mark.django_db

STRONG = "a-long-pass-phrase-9"


def run(*args) -> str:
    out = StringIO()
    call_command("create_platform_user", *args, stdout=out)
    return out.getvalue()


def staff(email="help@erplora.com"):
    return get_user_model().objects.get(email=email)


def in_support(user) -> bool:
    return user.groups.filter(name="support").exists()


def test_admin_is_a_superuser_with_staff_and_the_given_password():
    output = run("boss@erplora.com", "--role", "admin", "--password", STRONG)

    user = staff("boss@erplora.com")
    assert (user.is_staff, user.is_superuser, in_support(user)) == (True, True, False)
    assert user.check_password(STRONG)
    assert "boss@erplora.com" in output


def test_support_is_staff_in_the_support_group_and_no_superuser():
    run("help@erplora.com", "--role", "support", "--password", STRONG)

    user = staff()
    assert (user.is_staff, user.is_superuser, in_support(user)) == (True, False, True)
    # View only: the accounts (accounts 0003), since L1-A2 the account plane of the businesses (hubs 0007) and,
    # since L3-A, the Account page's preferences, photo, API keys and sessions (accounts 0006) and, since the
    # review of the fiscal documentation, the businesses' signed authorisations (fiscal 0002) and, since
    # APP-WHATSAPP, the businesses' WhatsApp: numbers, templates, sends, the month's count and what waits for the Hub
    # (whatsapp 0002, WHATSAPP-G18) and, since hub#603, the businesses' daily usage (hubs 0024, HUBS-F23).
    assert set(user.get_all_permissions()) == {
        "accounts.view_user",
        "accounts.view_hubmembership",
        "accounts.view_authexchangecode",
        "accounts.view_apikey",
        "accounts.view_userpreferences",
        "accounts.view_profilephoto",
        "usersessions.view_usersession",
        "hubs.view_hub",
        "hubs.view_hubmember",
        "hubs.view_hubownershiptransfer",
        "hubs.view_billingprofile",
        "hubs.view_subscription",
        "hubs.view_subscriptionitem",
        "hubs.view_sessionrevocation",
        "hubs.view_hubusagedaily",
        "fiscal.view_representationgrant",
        "whatsapp.view_phonenumber",
        "whatsapp.view_template",
        "whatsapp.view_send",
        "whatsapp.view_usage",
        "whatsapp.view_delivery",
    }


def test_the_email_is_the_account_s_normalised_email():
    run("Help@ERPLORA.com", "--role", "support", "--password", STRONG)

    assert staff().email == "help@erplora.com"


def test_without_a_password_a_new_account_has_no_usable_password():
    run("help@erplora.com", "--role", "support")

    assert not staff().has_usable_password()


def test_running_it_again_updates_the_role_and_keeps_the_password():
    run("help@erplora.com", "--role", "admin", "--password", STRONG)
    run("help@erplora.com", "--role", "support")

    user = staff()
    assert (user.is_staff, user.is_superuser, in_support(user)) == (True, False, True)
    assert user.check_password(STRONG)

    run("help@erplora.com", "--role", "admin")

    user = staff()
    assert (user.is_staff, user.is_superuser, in_support(user)) == (True, True, False)
    assert get_user_model().objects.count() == 1


def test_a_given_password_replaces_the_old_one():
    run("help@erplora.com", "--role", "support", "--password", STRONG)
    run("help@erplora.com", "--role", "support", "--password", "another-long-phrase-7")

    assert staff().check_password("another-long-phrase-7")


def test_a_weak_password_is_refused_and_nothing_is_created():
    with pytest.raises(CommandError, match="password"):
        run("help@erplora.com", "--role", "support", "--password", "123")

    assert not get_user_model().objects.exists()


@pytest.mark.parametrize("role", ["owner", "hub_admin", "superuser", ""])
def test_only_admin_and_support_are_platform_roles(role):
    with pytest.raises(CommandError):
        run("help@erplora.com", "--role", role, "--password", STRONG)

    assert not get_user_model().objects.exists()


def test_a_customer_of_a_hub_is_never_turned_into_platform_staff(ana):
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)

    with pytest.raises(CommandError, match="customer"):
        run("ana@example.com", "--role", "support")

    ana.refresh_from_db()
    assert (ana.is_staff, ana.is_superuser, in_support(ana)) == (False, False, False)


@pytest.mark.parametrize("role", ["admin", "support"])
def test_the_store_review_account_is_never_turned_into_platform_staff(ana, role):
    """ACCOUNTS-F49: its sign-in skips the mailed code, so it never leads to the admin."""
    get_user_model().objects.filter(pk=ana.pk).update(is_store_review_account=True)

    with pytest.raises(CommandError, match="store review account"):
        run("ana@example.com", "--role", role)

    ana.refresh_from_db()
    assert (ana.is_staff, ana.is_superuser, in_support(ana)) == (False, False, False)


def test_without_the_support_group_it_fails_loudly():
    Group.objects.filter(name="support").delete()

    with pytest.raises(CommandError, match="support"):
        run("help@erplora.com", "--role", "support", "--password", STRONG)

    assert not get_user_model().objects.exists()
