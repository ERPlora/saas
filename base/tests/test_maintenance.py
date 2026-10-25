"""ACCOUNTS-G82 (and G33, G64): erplora.com in maintenance mode.

The staff turns it on in the admin («Site settings»); from then every visitor gets the maintenance page, 503 with
``Retry-After`` (what Google, Shopify and Stripe answer while a site is down on purpose), and a program the JSON
envelope. The staff with its session keeps using everything, and what must keep working stays out: the health checks
(the load balancer and the deploy would take the tasks out), the static files, the admin and the staff's sign-in, the
Hub's ``/internal`` calls, Stripe's and Meta's webhooks and the CSP reports (PLAN-SAAS §1.1, «Modo mantenimiento»).
"""

import json
import logging

import pytest
from django.core.cache import cache
from django.db import DatabaseError

from base import queries
from base.models import SiteSettings

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def maintenance():
    site = SiteSettings.objects.create(maintenance_mode=True)
    cache.clear()
    return site


def get(client, path, **extra):
    return client.get(path, HTTP_HOST=HOST, **extra)


def is_maintenance(response) -> bool:
    if response.status_code != 503:
        return False
    if response["Content-Type"].startswith("application/json"):
        return json.loads(response.content).get("error", {}).get("code") == "maintenance"
    return 'class="error-page"' in response.content.decode() and "503" in response.content.decode()


class TestOff:
    def test_without_a_row_nothing_changes(self, client):
        assert get(client, "/").status_code == 200

    def test_with_the_switch_off_nothing_changes(self, client):
        SiteSettings.objects.create(maintenance_mode=False)

        assert get(client, "/").status_code == 200
        assert get(client, "/launch").status_code == 200


@pytest.mark.usefixtures("maintenance")
class TestOnForAVisitor:
    @pytest.mark.parametrize("path", ["/", "/pricing/", "/launch", "/dashboard/account/profile", "/hub-login/?hub=a"])
    def test_every_page_is_the_maintenance_page(self, client, path):
        response = get(client, path)

        assert is_maintenance(response), path

    def test_it_asks_to_come_back_and_is_never_cached(self, client):
        response = get(client, "/")

        assert response["Retry-After"] == "300"
        assert "no-store" in response["Cache-Control"]

    def test_the_page_says_so_in_english(self, client):
        page = get(client, "/", HTTP_ACCEPT_LANGUAGE="en").content.decode()

        assert "503 · Maintenance" in page
        assert "We will be back soon" in page
        assert "We are improving ERPlora. Come back in a few minutes; your data is safe." in page
        assert 'href="/"' in page

    def test_the_page_says_so_in_spanish(self, client):
        page = get(client, "/", HTTP_ACCEPT_LANGUAGE="es").content.decode()

        assert "503 · Mantenimiento" in page
        assert "Volvemos enseguida" in page
        assert "Estamos mejorando ERPlora. Vuelve en unos minutos; tus datos están a salvo." in page

    def test_the_staffs_message_replaces_the_default_one_in_each_language(self, client, maintenance):
        maintenance.maintenance_message_en = "Back at 14:00 CET."
        maintenance.maintenance_message_es = "Volvemos a las 14:00."
        maintenance.save()
        cache.clear()

        english = get(client, "/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
        spanish = get(client, "/", HTTP_ACCEPT_LANGUAGE="es").content.decode()

        assert "Back at 14:00 CET." in english
        assert "Come back in a few minutes" not in english
        assert "Volvemos a las 14:00." in spanish

    def test_the_staffs_message_is_text_never_html(self, client, maintenance):
        maintenance.maintenance_message_en = '<script>alert("x")</script>'
        maintenance.save()
        cache.clear()

        page = get(client, "/", HTTP_ACCEPT_LANGUAGE="en").content.decode()

        assert '<script>alert("x")</script>' not in page
        assert "&lt;script&gt;" in page

    @pytest.mark.parametrize("path", ["/api/me", "/api/live"])
    def test_a_program_gets_the_json_envelope(self, client, path):
        response = get(client, path)

        assert response.status_code == 503
        assert response["Retry-After"] == "300"
        assert json.loads(response.content)["error"]["code"] == "maintenance"

    def test_a_customer_with_a_session_gets_it_too(self, client, django_user_model):
        client.force_login(django_user_model.objects.create_user(email="ana@example.com", password="x"))

        assert is_maintenance(get(client, "/dashboard/account/profile"))

    def test_an_api_key_of_the_staff_is_no_session(self, client, django_user_model, maintenance):
        from accounts.models import ApiKey

        staff = django_user_model.objects.create_superuser(email="staff@example.com", password="x")
        secret, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=staff, name="ops", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"])
        bearer = {"HTTP_AUTHORIZATION": f"Bearer {secret}"}

        assert is_maintenance(get(client, "/api/hubs/businesses", **bearer))
        maintenance.maintenance_mode = False
        maintenance.save()
        cache.clear()
        assert get(client, "/api/hubs/businesses", **bearer).status_code == 200  # the same key opens it once the switch is off


@pytest.mark.usefixtures("maintenance")
class TestWhatKeepsWorking:
    def test_the_health_checks(self, client):
        assert get(client, "/healthz").status_code == 200
        assert get(client, "/readyz").status_code == 200

    def test_the_static_files(self, client):
        assert not is_maintenance(get(client, "/static/css/error-pages.css"))

    def test_the_admin_and_its_sign_in(self, client):
        response = get(client, "/admin/")

        assert response.status_code == 302
        assert response.url.startswith("/admin/login/")
        assert get(client, "/admin/login/").status_code == 302

    @pytest.mark.parametrize("path", ["/launch?next=/admin/", "/2fa?next=/admin/base/sitesettings/"])
    def test_the_sign_in_pages_on_the_way_to_the_admin(self, client, path):
        assert get(client, path).status_code == 200

    def test_the_sign_in_api(self, client):
        assert get(client, "/_allauth/browser/v1/config").status_code == 200

    def test_the_hubs_internal_calls(self, client):
        response = client.post("/internal/auth/redeem", data="{}", content_type="application/json", HTTP_HOST=HOST)

        assert not is_maintenance(response)

    @pytest.mark.parametrize("path", ["/webhooks/stripe/", "/webhooks/whatsapp/"])
    def test_the_webhooks(self, client, path):
        response = client.post(path, data="{}", content_type="application/json", HTTP_HOST=HOST)

        assert not is_maintenance(response)

    def test_the_csp_reports(self, client):
        response = client.post("/csp-report/", data="{}", content_type="application/csp-report", HTTP_HOST=HOST)

        assert response.status_code == 204

    def test_a_next_that_only_looks_like_the_admin_opens_nothing(self, client):
        assert is_maintenance(get(client, "/launch?next=/administrator/"))
        assert is_maintenance(get(client, "/launch?next=https://evil.example/admin/"))


@pytest.mark.usefixtures("maintenance")
class TestTheStaff:
    def test_the_staff_with_its_session_uses_everything(self, client, django_user_model):
        client.force_login(
            django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)
        )

        assert get(client, "/").status_code == 200
        assert get(client, "/launch").status_code == 200

    def test_an_inactive_staff_account_does_not(self, client, django_user_model):
        staff = django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)
        client.force_login(staff)
        staff.is_active = False
        staff.save()

        assert is_maintenance(get(client, "/"))


class TestTheSwitch:
    def test_turning_it_on_applies_at_once_on_this_task_and_the_others(self, client, django_capture_on_commit_callbacks):
        site = SiteSettings.objects.create()
        assert get(client, "/").status_code == 200

        with django_capture_on_commit_callbacks(execute=True):
            site.maintenance_mode = True
            site.save()

        assert is_maintenance(get(client, "/"))

    def test_turning_it_off_applies_at_once(self, client, maintenance, django_capture_on_commit_callbacks):
        assert is_maintenance(get(client, "/"))

        with django_capture_on_commit_callbacks(execute=True):
            maintenance.maintenance_mode = False
            maintenance.save()

        assert get(client, "/").status_code == 200

    def test_it_is_read_once_and_kept_a_minute(self, client, django_assert_num_queries):
        SiteSettings.objects.create()
        queries.maintenance_state()

        with django_assert_num_queries(0):
            queries.maintenance_state()

        assert queries.MAINTENANCE_KEEP_SECONDS == 60

    @pytest.mark.parametrize("error", [DatabaseError("connection refused"), RuntimeError("a bug")])
    def test_when_the_switch_cannot_be_read_the_site_stays_open_and_the_log_says_why(
        self, client, monkeypatch, caplog, error
    ):
        def unreadable():
            raise error

        monkeypatch.setattr(queries, "_read_maintenance", unreadable)

        with caplog.at_level(logging.WARNING, logger="base.queries"):
            response = get(client, "/")

        assert response.status_code == 200
        assert "base.maintenance_unreadable" in caplog.text
