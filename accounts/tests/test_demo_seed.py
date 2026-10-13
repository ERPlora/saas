"""``manage.py demo_seed``: the local accounts of the PoC, two customers and a platform administrator.

Customer and platform roles never mix: the owner and the employee of the hubs are no staff, and the
platform administrator has no hub. The passwords are known, so it only runs with ``DEBUG`` on.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import HubMembership

pytestmark = pytest.mark.django_db


def _seed() -> str:
    out = StringIO()
    # Local development: pytest-django runs every test with DEBUG off.
    with override_settings(DEBUG=True):
        call_command("demo_seed", stdout=out)
    return out.getvalue()


@override_settings(DEBUG=False)
def test_refuses_to_run_without_debug_and_creates_nothing():
    """Known passwords and a superuser: a production database must never get these accounts."""
    with pytest.raises(CommandError, match="demo_seed only runs with DEBUG=True"):
        call_command("demo_seed", stdout=StringIO())

    assert not get_user_model().objects.exists()
    assert not HubMembership.objects.exists()


def test_creates_owner_example_com_as_the_owner_of_hubs_a_and_b_and_no_staff():
    output = _seed()

    owner = get_user_model().objects.get(email="owner@example.com")
    assert owner.check_password("owner")
    assert (owner.is_staff, owner.is_superuser) == (False, False)
    assert sorted(
        HubMembership.objects.filter(user=owner).values_list("hub_slug", "role")
    ) == [
        ("a", "hub_owner"),
        ("b", "hub_owner"),
    ]
    assert "owner@example.com" in output


def test_creates_employee_example_com_as_an_employee_of_hubs_a_and_b_and_no_staff():
    """DEMO-F06 «Intentarlo sin permiso»: the employee only sees the demo's list and detail."""
    output = _seed()

    employee = get_user_model().objects.get(email="employee@example.com")
    assert employee.check_password("employee")
    assert (employee.is_staff, employee.is_superuser) == (False, False)
    assert sorted(
        HubMembership.objects.filter(user=employee).values_list("hub_slug", "role")
    ) == [
        ("a", "hub_employee"),
        ("b", "hub_employee"),
    ]
    assert "employee@example.com" in output


def test_creates_platform_example_com_as_a_superuser_with_no_hub():
    output = _seed()

    platform = get_user_model().objects.get(email="platform@example.com")
    assert platform.check_password("platform")
    assert (platform.is_staff, platform.is_superuser) == (True, True)
    assert not HubMembership.objects.filter(user=platform).exists()
    assert "platform@example.com" in output


def test_the_old_admin_example_com_is_gone():
    _seed()

    assert not get_user_model().objects.filter(email="admin@example.com").exists()


def test_the_demo_hubs_are_valid_hub_slugs_in_local_development():
    """`a` and `b` pass the shared rule only because development lowers its minimum to one letter."""
    _seed()

    memberships = HubMembership.objects.all()
    assert len(memberships) == 4
    for membership in memberships:
        membership.full_clean()


def test_is_idempotent():
    _seed()
    _seed()

    assert get_user_model().objects.count() == 3
    assert HubMembership.objects.count() == 4
