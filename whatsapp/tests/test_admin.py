"""WHATSAPP-G08, WHATSAPP-G18 · What ERPlora's staff can do with the businesses' WhatsApp in the Django admin
(``erplora.com/admin``).

Each business's number (its business, Meta's ids, whether it comes from the WhatsApp Business app, when its permission
expires, whether it needs reconnecting), the mirror of its templates, what waits for its Hub, its sends and its
month's count: seen, never written by hand. Cases of the old product's ``test_admin.py`` and what its WORKFLOW left
``parcial`` (F20): the business of a number is not changed nor activated by hand (only Meta's window connects one),
the permission and the PIN are never shown, nobody reads what a customer wrote, and the pages are translated. The
platform's actions are superusers' (``support`` only sees): disconnect a number, push to the Hub now what waits,
read Meta's templates again.
"""

import json

import httpx
import pytest
import respx
from django.contrib.auth.models import Group
from django.utils import timezone, translation

from whatsapp.models import Delivery, PhoneNumber, Send, Template, Usage
from whatsapp.tests.conftest import GRAPH

pytestmark = pytest.mark.django_db

ADMIN = "/admin/whatsapp"
WABA = "102290129340398"


@pytest.fixture
def number(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id="106540352242922", display_phone="+34 910 00 00 00", waba_id=WABA,
        access_token="EAAG-very-secret-token", registration_pin="246810",
    )


@pytest.fixture
def superuser(make_user):
    return make_user("root@erplora.com", is_staff=True, is_superuser=True)


@pytest.fixture
def as_superuser(client, superuser):
    client.force_login(superuser)
    return client


@pytest.fixture
def as_support(client, make_user):
    user = make_user("support@erplora.com", first_name="Sara", is_staff=True)
    user.groups.add(Group.objects.get(name="support"))
    client.force_login(user)
    return client


def get(client, path):
    return client.get(path, HTTP_HOST="localhost")


def act(client, model, action, ids):
    return client.post(
        f"{ADMIN}/{model}/",
        {"action": action, "_selected_action": [str(pk) for pk in ids]},
        HTTP_HOST="localhost",
        follow=True,
    )


def parked(hub, **fields):
    return Delivery.objects.create(
        hub=hub, kind="message", wa_message_id=fields.pop("wa_message_id", "wamid.1"), contact="34600111222",
        body={"hub": hub.slug, "wa_message_id": "wamid.1", "from": "34600111222", "text": "Hola, mi secreto",
              "type": "text"},
        **fields,
    )


class TestTheNumbers:
    def test_the_list_shows_each_number_and_its_state(self, as_superuser, number, business):
        response = get(as_superuser, f"{ADMIN}/phonenumber/")

        assert response.status_code == 200
        page = response.content.decode()
        assert "+34 910 00 00 00" in page and business.name in page and "106540352242922" in page

    def test_the_list_filters_by_needs_reconnecting_and_finds_by_number(self, as_superuser, number, business):
        PhoneNumber.objects.create(
            hub=business, phone_number_id="999", display_phone="+34 600", waba_id="W", is_active=False,
            needs_reconnect=True,
        )

        flagged = get(as_superuser, f"{ADMIN}/phonenumber/?needs_reconnect__exact=1")
        found = get(as_superuser, f"{ADMIN}/phonenumber/?q=106540352242922")

        assert [row.phone_number_id for row in flagged.context["cl"].result_list] == ["999"]
        assert [row.phone_number_id for row in found.context["cl"].result_list] == ["106540352242922"]

    def test_the_form_never_shows_the_permission_nor_the_pin_and_says_if_it_is_stored(self, as_superuser, number):
        response = get(as_superuser, f"{ADMIN}/phonenumber/{number.pk}/change/")

        assert response.status_code == 200
        page = response.content.decode()
        assert "EAAG-very-secret-token" not in page and "246810" not in page
        assert "Stored: this number can send and receive" in page
        assert 'name="_save"' not in page and 'name="hub"' not in page and 'name="is_active"' not in page

    def test_a_missing_permission_says_the_business_must_connect_again(self, as_superuser, number):
        PhoneNumber.objects.filter(pk=number.pk).update(access_token="")

        page = get(as_superuser, f"{ADMIN}/phonenumber/{number.pk}/change/").content.decode()

        assert "Missing: the business has to connect the number again" in page

    def test_an_expired_permission_says_so(self, as_superuser, number):
        PhoneNumber.objects.filter(pk=number.pk).update(token_expires_at=timezone.now() - timezone.timedelta(days=1))

        page = get(as_superuser, f"{ADMIN}/phonenumber/{number.pk}/change/").content.decode()

        assert "Expired: the business has to connect the number again" in page

    def test_nothing_is_added_nor_deleted_by_hand(self, as_superuser, number):
        assert get(as_superuser, f"{ADMIN}/phonenumber/add/").status_code == 403
        assert get(as_superuser, f"{ADMIN}/phonenumber/{number.pk}/delete/").status_code == 403

    @respx.mock
    def test_disconnect_stops_the_number_forgets_its_permission_and_unsubscribes(self, as_superuser, number):
        unsubscribe = respx.delete(f"{GRAPH}/{WABA}/subscribed_apps").mock(
            return_value=httpx.Response(200, json={"success": True})
        )

        response = act(as_superuser, "phonenumber", "disconnect", [number.pk])

        assert response.status_code == 200
        number.refresh_from_db()
        assert (number.is_active, number.access_token) == (False, "")
        assert unsubscribe.called
        assert "1 number disconnected" in response.content.decode()

    @respx.mock
    def test_read_metas_templates_again(self, as_superuser, number, business):
        respx.get(f"{GRAPH}/{WABA}/message_templates").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "77", "name": "recordatorio", "language": "es", "category": "UTILITY",
                                "status": "APPROVED", "components": [{"type": "BODY", "text": "Hola"}]}]},
            )
        )

        response = act(as_superuser, "phonenumber", "read_templates_again", [number.pk])

        assert response.status_code == 200
        assert Template.objects.get(hub=business).status == "APPROVED"
        assert "read again" in response.content.decode()


class TestWhatWaitsForTheHub:
    def test_the_list_says_what_the_hub_took_and_what_still_waits_without_what_the_customer_wrote(
        self, as_superuser, business
    ):
        row = parked(business, last_error="HTTP 404 app_inactive", attempts=3)

        response = get(as_superuser, f"{ADMIN}/delivery/")
        detail = get(as_superuser, f"{ADMIN}/delivery/{row.pk}/change/")

        assert response.status_code == 200 and detail.status_code == 200
        for page in (response.content.decode(), detail.content.decode()):
            assert "wamid.1" in page and "HTTP 404 app_inactive" in page
            assert "mi secreto" not in page and "34600111222" not in page

    def test_the_list_filters_what_the_hub_has_not_taken(self, as_superuser, business):
        parked(business, wa_message_id="wamid.waiting")
        parked(business, wa_message_id="wamid.taken", delivered_at=timezone.now())

        response = get(as_superuser, f"{ADMIN}/delivery/?delivered_at__isnull=True")

        assert [row.wa_message_id for row in response.context["cl"].result_list] == ["wamid.waiting"]

    def test_push_now_what_waits(self, as_superuser, business, hub_double):
        hub_double.answer("POST", r"^/internal/whatsapp/inbound$", 200, {"created": True})
        row = parked(business, next_attempt_at=timezone.now() + timezone.timedelta(hours=1), attempts=4)

        response = act(as_superuser, "delivery", "push_now", [row.pk])

        row.refresh_from_db()
        assert row.delivered_at is not None
        assert "1 taken by the Hub" in response.content.decode()

    def test_nothing_is_added_changed_nor_deleted_by_hand(self, as_superuser, business):
        row = parked(business)

        assert get(as_superuser, f"{ADMIN}/delivery/add/").status_code == 403
        assert get(as_superuser, f"{ADMIN}/delivery/{row.pk}/delete/").status_code == 403
        assert 'name="_save"' not in get(as_superuser, f"{ADMIN}/delivery/{row.pk}/change/").content.decode()


class TestTheRest:
    def test_templates_sends_and_the_months_count_are_seen(self, as_superuser, business):
        Template.objects.create(hub=business, name="recordatorio", language="es", status="REJECTED",
                                rejected_reason="INVALID_FORMAT")
        Send.objects.create(hub=business, idempotency_key="k-1", month="2026-10", wa_message_id="wamid.9")
        Usage.objects.create(hub=business, month="2026-10", used=12)

        templates = get(as_superuser, f"{ADMIN}/template/").content.decode()
        sends = get(as_superuser, f"{ADMIN}/send/").content.decode()
        usage = get(as_superuser, f"{ADMIN}/usage/").content.decode()

        assert "recordatorio" in templates and "INVALID_FORMAT" in templates
        assert "k-1" in sends and "wamid.9" in sends
        assert "2026-10" in usage and ">12<" in usage

    def test_the_templates_are_not_written_by_hand(self, as_superuser, business):
        template = Template.objects.create(hub=business, name="recordatorio", language="es")

        assert get(as_superuser, f"{ADMIN}/template/add/").status_code == 403
        assert get(as_superuser, f"{ADMIN}/template/{template.pk}/delete/").status_code == 403


class TestWhoSeesWhat:
    def test_support_sees_every_list_and_has_no_action(self, as_support, number, business):
        parked(business)

        for model in ("phonenumber", "template", "delivery", "send", "usage"):
            assert get(as_support, f"{ADMIN}/{model}/").status_code == 200, model
        numbers = get(as_support, f"{ADMIN}/phonenumber/").content.decode()
        deliveries = get(as_support, f"{ADMIN}/delivery/").content.decode()
        assert 'value="disconnect"' not in numbers and 'value="push_now"' not in deliveries

    @respx.mock(assert_all_called=False)
    def test_support_cannot_run_an_action(self, as_support, number):
        act(as_support, "phonenumber", "disconnect", [number.pk])

        number.refresh_from_db()
        assert number.is_active

    def test_staff_without_the_permission_sees_nothing(self, client, make_user, number):
        client.force_login(make_user("someone@erplora.com", is_staff=True))

        assert get(client, f"{ADMIN}/phonenumber/").status_code == 403


def test_the_admin_speaks_spanish():
    with translation.override("es"):
        assert str(PhoneNumber._meta.verbose_name_plural) == "Números de WhatsApp"
        assert str(Delivery._meta.verbose_name_plural) == "Entregas de WhatsApp al Hub"
        assert str(Template._meta.verbose_name_plural) == "Plantillas de WhatsApp"


def test_no_admin_page_ever_names_the_token(as_superuser, number, business):
    parked(business)
    pages = [get(as_superuser, f"{ADMIN}/{model}/").content.decode() for model in ("phonenumber", "delivery")]

    assert all("EAAG-very-secret-token" not in page for page in pages)
    assert json.dumps("246810") not in "".join(pages)
