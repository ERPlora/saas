"""The Django admin of the users: their pages load, the staff find and filter them, the page shows what the account
chose and accepted, and only a superuser sets the store review mark; a customer is never made staff here."""

from html import unescape

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from accounts.tests.admin_pages import _as_posted, _change_page
from accounts.tests.conftest import enter
from hubs.models import HubMember

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", ["user", "authexchangecode"])
def test_changelist_and_change_page_load(staff_client, model):
    client, _ = staff_client

    response = client.get(f"/admin/accounts/{model}/")

    assert response.status_code == 200


def test_the_user_change_page_loads(staff_client):
    client, admin = staff_client

    assert client.get(f"/admin/accounts/user/{admin.pk}/change/").status_code == 200


def test_a_user_can_be_added_with_email_and_password(staff_client):
    client, _ = staff_client

    response = client.post(
        "/admin/accounts/user/add/",
        {"email": "bo@example.com", "password1": "a-long-pass-phrase", "password2": "a-long-pass-phrase", "usable_password": "true"},
    )

    assert response.status_code == 302
    assert get_user_model().objects.get(email="bo@example.com").check_password("a-long-pass-phrase")


@pytest.mark.parametrize("query", ["lp@example", "Lucía", "Pérez"])
def test_the_staff_find_an_account_by_its_email_or_its_names(staff_client, query):
    """The staff find an account by its email or its name; the names are not in the address."""
    client, _ = staff_client
    get_user_model().objects.create_user(email="lp@example.com", password="x", first_name="Lucía", last_name="Pérez")

    response = client.get("/admin/accounts/user/", {"q": query})

    assert [user.email for user in response.context["cl"].result_list] == ["lp@example.com"]


@pytest.mark.parametrize(
    ("filters", "found"),
    [
        ({"language__exact": "es"}, ["ana@example.com"]),
        ({"is_staff__exact": "1"}, ["root@example.com"]),
        ({"is_active__exact": "0"}, []),
    ],
)
def test_the_staff_filter_the_accounts_by_active_staff_and_language(staff_client, ana, filters, found):
    """The staff filter the accounts by active, staff and language."""
    client, _ = staff_client

    response = client.get("/admin/accounts/user/", filters)

    assert sorted(user.email for user in response.context["cl"].result_list) == found
    # The admin answers any lookup on a field of its own: the filters must be offered on the page too.
    offered = {spec.field_path for spec in response.context["cl"].filter_specs}
    assert {"is_active", "is_staff", "language"} <= offered


def test_the_user_page_shows_the_preferences_and_the_photo(staff_client, ana):
    from accounts.models import ProfilePhoto, UserPreferences

    client, _ = staff_client
    UserPreferences.objects.create(user=ana, theme_mode="dark", transparency=False)
    ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert ("Dark" in page.text, "Transparency effects" in page.text) == (True, True)
    assert "data:image/png;base64,iVBORw==" in page.text


def test_the_user_page_hides_the_preferences_and_the_photo_it_never_saved(staff_client, ana):
    """An account on the defaults has no row there; an empty read-only box says nothing."""
    from accounts.models import ProfilePhoto, UserPreferences

    client, _ = staff_client

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert [inline.opts.model for inline in page.context["inline_admin_formsets"]] == [HubMember]

    UserPreferences.objects.create(user=ana, theme_mode="dark")
    ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")
    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert [inline.opts.model for inline in page.context["inline_admin_formsets"]] == [
        UserPreferences,
        ProfilePhoto,
        HubMember,
    ]


def test_the_user_page_shows_the_terms_it_accepted_read_only(staff_client, ana):
    """What the account accepted and when, as evidence; nobody edits it."""
    from datetime import UTC, date, datetime

    client, _ = staff_client
    get_user_model().objects.filter(pk=ana.pk).update(
        terms_accepted_at=datetime(2026, 10, 14, 9, 30, tzinfo=UTC), terms_version=date(2026, 10, 13), privacy_version=date(2026, 10, 13)
    )

    page = client.get(f"/admin/accounts/user/{ana.pk}/change/")

    assert page.status_code == 200
    assert "Terms accepted at" in page.text
    assert "Oct. 14, 2026" in page.text
    for field in ("terms_accepted_at", "terms_version", "privacy_version"):
        assert f'name="{field}"' not in page.text


REFUSED_ON_STAFF = "A staff account cannot be a store review account."


def _save(client, user, **changes):
    return client.post(f"/admin/accounts/user/{user.pk}/change/", _as_posted(_change_page(client, user), **changes))


def _mark_for_store_review(user):
    get_user_model().objects.filter(pk=user.pk).update(is_store_review_account=True)


class TestTheStoreReviewMark:
    """On the account's page only a superuser sets and clears «Store review account»; ``support`` sees
    it; an account of the staff never carries it."""

    @pytest.fixture
    def editor(self, client):
        """Staff that may change accounts without being a superuser (no such role today: the mark stays the
        superuser's even if one comes)."""
        editor = get_user_model().objects.create_user(email="editor@erplora.com", password="x", is_staff=True)
        editor.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="accounts", codename__in=["view_user", "change_user"])
        )
        client.force_login(editor)
        return client

    def test_the_superuser_sees_it_with_what_it_does(self, staff_client, ana):
        client, _ = staff_client

        page = _change_page(client, ana)

        assert 'name="is_store_review_account"' in page.text
        assert "Store review account" in page.text
        assert "Signs in with its password, without the mailed code." in page.text

    def test_the_superuser_marks_it_and_clears_it(self, staff_client, ana):
        client, _ = staff_client

        assert _save(client, ana, is_store_review_account="on").status_code == 302
        ana.refresh_from_db()
        assert ana.is_store_review_account is True

        assert _save(client, ana, is_store_review_account=False).status_code == 302
        ana.refresh_from_db()
        assert ana.is_store_review_account is False

    def test_an_account_of_the_staff_cannot_carry_it_and_nothing_is_saved(self, staff_client):
        client, _ = staff_client
        helper = get_user_model().objects.create_user(
            email="help@erplora.com", password="x", is_staff=True, first_name="Helena"
        )

        response = _save(client, helper, is_store_review_account="on", first_name="Elena")

        assert response.status_code == 200
        assert REFUSED_ON_STAFF in response.text
        helper.refresh_from_db()
        assert (helper.is_store_review_account, helper.first_name) == (False, "Helena")

    def test_nor_does_a_marked_account_become_staff(self, staff_client, ana):
        client, _ = staff_client
        _mark_for_store_review(ana)

        response = _save(client, ana, is_staff="on")

        assert response.status_code == 200
        assert REFUSED_ON_STAFF in response.text
        ana.refresh_from_db()
        assert (ana.is_staff, ana.is_store_review_account) == (False, True)

    def test_the_refusal_speaks_spanish(self, staff_client):
        client, _ = staff_client
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        helper = get_user_model().objects.create_user(email="help@erplora.com", password="x", is_staff=True)

        response = _save(client, helper, is_store_review_account="on")

        assert "Una cuenta del personal no puede ser cuenta de revisión de tienda." in response.text
        assert "Cuenta de revisión de tienda" in response.text

    def test_support_sees_it_and_cannot_change_it(self, client, ana):
        helper = get_user_model().objects.create_user(email="help@erplora.com", password="x", is_staff=True)
        helper.groups.add(Group.objects.get(name="support"))
        client.force_login(helper)
        _mark_for_store_review(ana)

        page = _change_page(client, ana)

        assert page.status_code == 200
        assert "Store review account" in page.text
        assert 'name="is_store_review_account"' not in page.text
        assert client.post(f"/admin/accounts/user/{ana.pk}/change/", {"is_store_review_account": ""}).status_code == 403
        ana.refresh_from_db()
        assert ana.is_store_review_account is True

    def test_staff_who_may_change_accounts_only_see_it(self, editor, ana):
        page = _change_page(editor, ana)

        assert "Store review account" in page.text
        assert 'name="is_store_review_account"' not in page.text
        response = editor.post(
            f"/admin/accounts/user/{ana.pk}/change/", _as_posted(page, is_store_review_account="on")
        )
        assert response.status_code == 302
        ana.refresh_from_db()
        assert ana.is_store_review_account is False

    def test_nor_may_they_make_a_marked_account_staff(self, editor, ana):
        _mark_for_store_review(ana)

        response = _save(editor, ana, is_staff="on")

        assert response.status_code == 200
        assert REFUSED_ON_STAFF in response.text
        ana.refresh_from_db()
        assert (ana.is_staff, ana.is_store_review_account) == (False, True)


ON_A_BUSINESS = "This account is on a business: ERPlora's staff and the customers never share an account."


class TestACustomerIsNoStaff:
    """The account's page never makes ERPlora's staff of somebody on a business (``User.clean``; the businesses
    the mirror does not show, an invitation waiting or one in recovery, are ``hubs/tests/test_members.py``'s)."""

    @pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
    def test_a_customer_is_not_made_staff_here_and_nothing_is_saved(self, staff_client, ana, flag):
        client, _ = staff_client
        enter(ana, "a", "hub_owner")

        response = _save(client, ana, first_name="Anita", **{flag: "on"})

        assert response.status_code == 200
        assert ON_A_BUSINESS in unescape(response.text)
        ana.refresh_from_db()
        assert (ana.is_staff, ana.is_superuser, ana.first_name) == (False, False, "Ana")

    def test_the_refusal_speaks_spanish(self, staff_client, ana):
        client, _ = staff_client
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        enter(ana, "a", "hub_employee")

        response = _save(client, ana, is_staff="on")

        assert "Esta cuenta está en un negocio: el personal de ERPlora y los clientes nunca comparten cuenta." in (
            unescape(response.text)
        )

    def test_an_account_on_no_business_is_made_staff_here(self, staff_client, ana):
        client, _ = staff_client

        assert _save(client, ana, is_staff="on").status_code == 302
        ana.refresh_from_db()
        assert ana.is_staff is True
