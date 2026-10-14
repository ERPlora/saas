"""``manage.py demo_seed``: the local accounts of the PoC and their businesses ``a`` and ``b``.

Ported from ``accounts/tests/test_demo_seed.py`` when the command moved to ``hubs`` (L1-A2): the two demo
hubs are businesses of the SaaS (``Hub`` + ``HubMember``, adopted as they already run in the local Hub),
and the jump's access is their mirror (``sync_access``), no longer rows written straight into
``accounts.HubMembership``. Customer and platform roles never mix: the owner and the employee are no
staff, and the platform administrator has no hub. The passwords are known, so it only runs with
``DEBUG`` on.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import HubMembership
from hubs import queries
from hubs.models import Hub, HubMember

pytestmark = pytest.mark.django_db


def _seed() -> str:
    out = StringIO()
    # Local development: pytest-django runs every test with DEBUG off.
    with override_settings(DEBUG=True):
        call_command("demo_seed", stdout=out)
    return out.getvalue()


def _roles(email):
    return sorted(HubMember.objects.filter(user__email=email).values_list("hub__slug", "role"))


@override_settings(DEBUG=False)
def test_refuses_to_run_without_debug_and_creates_nothing():
    """Known passwords and a superuser: a production database must never get these accounts."""
    with pytest.raises(CommandError, match="demo_seed only runs with DEBUG=True"):
        call_command("demo_seed", stdout=StringIO())

    assert not get_user_model().objects.exists()
    assert not Hub.objects.exists()
    assert not HubMembership.objects.exists()


def test_the_demo_hubs_are_businesses_that_already_run_in_the_hub():
    _seed()

    for hub in Hub.objects.order_by("slug"):
        assert (hub.slug, hub.status, hub.pending_hub_call) in {("a", "active", ""), ("b", "active", "")}
        assert hub.ready_at is not None
        assert hub.pushed_state_version == hub.state_version
    assert Hub.objects.count() == 2


def test_creates_owner_example_com_as_the_owner_of_a_and_b_and_no_staff():
    output = _seed()

    owner = get_user_model().objects.get(email="owner@example.com")
    assert owner.check_password("owner")
    assert (owner.is_staff, owner.is_superuser) == (False, False)
    assert _roles("owner@example.com") == [("a", "hub_owner"), ("b", "hub_owner")]
    assert "owner@example.com" in output


def test_creates_employee_example_com_as_an_employee_of_a_and_b_and_no_staff():
    """DEMO-F06 «Intentarlo sin permiso»: the employee only sees the demo's list and detail."""
    output = _seed()

    employee = get_user_model().objects.get(email="employee@example.com")
    assert employee.check_password("employee")
    assert (employee.is_staff, employee.is_superuser) == (False, False)
    assert _roles("employee@example.com") == [("a", "hub_employee"), ("b", "hub_employee")]
    assert "employee@example.com" in output


def test_creates_platform_example_com_as_a_superuser_with_no_hub():
    output = _seed()

    platform = get_user_model().objects.get(email="platform@example.com")
    assert platform.check_password("platform")
    assert (platform.is_staff, platform.is_superuser) == (True, True)
    assert not HubMember.objects.filter(user=platform).exists()
    assert not HubMembership.objects.filter(user=platform).exists()
    assert "platform@example.com" in output


def test_the_jumps_access_is_the_mirror_of_the_businesses():
    _seed()

    assert queries.verify_access_mirror() == []
    assert sorted(HubMembership.objects.values_list("user__email", "hub_slug", "role")) == [
        ("employee@example.com", "a", "hub_employee"),
        ("employee@example.com", "b", "hub_employee"),
        ("owner@example.com", "a", "hub_owner"),
        ("owner@example.com", "b", "hub_owner"),
    ]


def test_the_old_admin_example_com_is_gone():
    _seed()

    assert not get_user_model().objects.filter(email="admin@example.com").exists()


def test_the_demo_hubs_are_valid_hub_slugs_in_local_development():
    """`a` and `b` pass the shared rule only because development lowers its minimum to one letter."""
    _seed()

    for membership in HubMembership.objects.all():
        membership.full_clean()


def test_is_idempotent():
    _seed()
    _seed()

    assert get_user_model().objects.count() == 3
    assert (Hub.objects.count(), HubMember.objects.count(), HubMembership.objects.count()) == (2, 4, 4)
