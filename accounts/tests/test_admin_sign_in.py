"""Who enters the Django admin: the platform, a superuser or ``support`` (view only); never a customer."""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings

from accounts.tests.conftest import enter
from hubs.models import HubMember

pytestmark = pytest.mark.django_db


class TestWhoEntersTheAdmin:
    """Only the platform enters the admin: a superuser, or ``support`` (view only); never a customer."""

    @pytest.fixture
    def users(self):
        # demo_seed runs only with DEBUG on (local development); pytest-django turns it off.
        with override_settings(DEBUG=True):
            call_command("demo_seed", stdout=StringIO())
        return get_user_model().objects

    def test_the_owner_of_a_hub_is_sent_to_the_admin_login(self, client, users):
        client.force_login(users.get(email="owner@example.com"))

        response = client.get("/admin/")

        assert response.status_code == 302
        assert response.url == "/admin/login/?next=/admin/"

    def test_the_owner_of_a_hub_cannot_sign_in_to_the_admin(self, client, users):
        """The admin's login signs nobody in: it hands over to the SaaS's sign-in (``test_mfa``)."""
        response = client.post("/admin/login/", {"username": "owner@example.com", "password": "owner"})

        assert (response.status_code, response.url) == (302, "/launch?next=/admin/")
        assert client.get("/admin/").status_code == 302

    @pytest.mark.parametrize("role", HubMember.Role.values)
    def test_no_customer_role_enters_the_admin(self, client, ana, role):
        enter(ana, "a", role)
        client.force_login(ana)

        assert client.get("/admin/").status_code == 302
        assert client.get("/admin/accounts/user/").status_code == 302

    def test_the_platform_administrator_enters(self, client, users):
        client.force_login(users.get(email="platform@example.com"))

        assert client.get("/admin/").status_code == 200

    def test_support_sees_accounts_but_cannot_add_change_or_delete(self, client, ana):
        helper = get_user_model().objects.create_user(email="help@erplora.com", password="x", is_staff=True)
        helper.groups.add(Group.objects.get(name="support"))
        client.force_login(helper)

        for model in ("user", "authexchangecode"):
            assert client.get(f"/admin/accounts/{model}/").status_code == 200
        assert client.get("/admin/hubs/hubmember/").status_code == 200
        assert client.get(f"/admin/accounts/user/{ana.pk}/change/").status_code == 200
        assert client.get("/admin/accounts/user/add/").status_code == 403
        assert client.post(f"/admin/accounts/user/{ana.pk}/change/", {"email": "x@example.com"}).status_code == 403
        assert client.get(f"/admin/accounts/user/{ana.pk}/delete/").status_code == 403
        assert get_user_model().objects.get(pk=ana.pk).email == "ana@example.com"
