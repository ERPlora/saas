"""ACCOUNTS-G33: «Site settings» in the admin of erplora.com, the switch of the maintenance mode (one row)."""

import re

import pytest
from django.core.cache import cache

from base.models import SiteSettings

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
CHANGELIST = "/admin/base/sitesettings/"


@pytest.fixture
def superuser(client, django_user_model):
    user = django_user_model.objects.create_superuser(email="staff@example.com", password="x", language="en")
    client.force_login(user)
    return user


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


def test_the_list_opens_the_one_row_creating_it_the_first_time(client, superuser):
    response = client.get(CHANGELIST, HTTP_HOST=HOST)

    site = SiteSettings.objects.get()
    assert response.status_code == 302
    assert response.url == f"{CHANGELIST}{site.pk}/change/"


def test_the_list_keeps_opening_the_same_row(client, superuser):
    site = SiteSettings.objects.create()

    response = client.get(CHANGELIST, HTTP_HOST=HOST)

    assert response.url == f"{CHANGELIST}{site.pk}/change/"
    assert SiteSettings.objects.count() == 1


def test_there_is_no_second_row_to_add_nor_one_to_delete(client, superuser):
    site = SiteSettings.objects.create()

    assert client.get(f"{CHANGELIST}add/", HTTP_HOST=HOST).status_code == 403
    assert client.get(f"{CHANGELIST}{site.pk}/delete/", HTTP_HOST=HOST).status_code == 403


@pytest.mark.usefixtures("spa_manifest")
def test_turning_it_on_says_who_still_enters(client, superuser, django_capture_on_commit_callbacks):
    site = SiteSettings.objects.create()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"{CHANGELIST}{site.pk}/change/",
            {"maintenance_mode": "on", "maintenance_message_en": "Back at 14:00.", "maintenance_message_es": ""},
            HTTP_HOST=HOST,
            follow=True,
        )

    site.refresh_from_db()
    assert site.maintenance_mode is True
    assert site.maintenance_message_en == "Back at 14:00."
    assert "Maintenance mode is on: only the ERPlora staff with a session uses erplora.com." in response.content.decode()
    assert client.get("/", HTTP_HOST=HOST).status_code == 200  # the staff itself still enters


def test_turning_it_off_says_so(client, superuser, django_capture_on_commit_callbacks):
    site = SiteSettings.objects.create(maintenance_mode=True)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"{CHANGELIST}{site.pk}/change/",
            {"maintenance_message_en": "", "maintenance_message_es": ""},
            HTTP_HOST=HOST,
            follow=True,
        )

    site.refresh_from_db()
    assert site.maintenance_mode is False
    assert "Maintenance mode is off: erplora.com is open to everyone." in response.content.decode()


def test_the_admin_speaks_spanish(client, django_user_model):
    client.force_login(
        django_user_model.objects.create_superuser(email="staff@example.com", password="x", language="es")
    )
    site = SiteSettings.objects.create()

    page = client.get(f"{CHANGELIST}{site.pk}/change/", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Ajustes del sitio" in page
    assert "Modo mantenimiento" in page
    assert "Mensaje en español" in page


def test_saving_it_in_spanish_is_said_in_good_spanish(client, django_user_model, django_capture_on_commit_callbacks):
    # Django says «El {name} “{obj}” se cambió correctamente», a singular masculine noun: «El ajustes del sitio» was not.
    client.force_login(
        django_user_model.objects.create_superuser(email="staff@example.com", password="x", language="es")
    )
    site = SiteSettings.objects.create()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"{CHANGELIST}{site.pk}/change/",
            {"maintenance_message_en": "", "maintenance_message_es": ""},
            HTTP_HOST=HOST,
            HTTP_ACCEPT_LANGUAGE="es",
            follow=True,
        )

    page = re.sub(r"<[^>]+>", "", response.content.decode())  # the row's name is a link to it
    assert "El ajuste del sitio “Ajustes del sitio” se cambió correctamente." in page
    assert "El ajustes del sitio" not in page
    assert "Ajustes del sitio" in page  # the admin's index and its breadcrumbs keep the plural


def test_support_without_the_permission_does_not_see_it(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(email="support@example.com", password="x", is_staff=True))

    assert client.get(CHANGELIST, HTTP_HOST=HOST).status_code == 403
