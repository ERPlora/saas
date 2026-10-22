"""FIX-SAAS-WHATSAPP-GATEWAY-DOORS, WHATSAPP-G05 · Door 5, ``POST /internal/whatsapp/send``, and door 6,
``POST /internal/whatsapp/erase`` (the Hub's WORKBOOK ``whatsapp_inbox``, «Contrato con el SaaS»).

The Hub calls them signed (v1 over the body, as ``apps/whatsapp_inbox/gateway.py`` does), with an
``Idempotency-Key`` on the send. Answers of door 5: 200 ``{"wa_message_id"}`` (Meta accepted it); 409
``whatsapp.cap_reached | not_connected | reconnect_needed | window_closed | template_not_approved |
recipient_blocked | meta_rejected`` (it did not leave); another 4xx (also 429) did not leave; a 5xx: nobody knows, and the Hub retries with the same key. erplora.com
never sends the same key twice and reserves the month's allowance atomically when it accepts.

Meta is replaced at the HTTP border only (``respx``). Cases of the old product's ``test_notify.py``,
``test_notify_idempotency.py``, ``test_plan_and_quota_count_the_same.py``, ``test_whatsapp_error_codes.py`` and
``test_demo_hub_cannot_send.py``.
"""

import json
import threading
import time
from datetime import timedelta

import httpx
import pytest
import respx
from django.db import connection
from django.test import Client
from django.utils import timezone

from accounts.signing import sign
from hubs.models import Hub, Plan, Subscription
from whatsapp.models import Delivery, PhoneNumber, Send, Template, Usage
from whatsapp.tests.conftest import GRAPH

SECRET = "test-internal-secret"
KEY = "0199e7c2-0000-7000-8000-000000000001"
PHONE_NUMBER_ID = "106540352242922"
SEND = f"{GRAPH}/{PHONE_NUMBER_ID}/messages"
ACCEPTED = {"messaging_product": "whatsapp", "contacts": [{"input": "34600111222", "wa_id": "34600111222"}],
            "messages": [{"id": "wamid.HBgLMzQ2MDAxMTEyMjIVAgARGBI"}]}


def door(client, path, payload, *, key=KEY, secret=SECRET, timestamp=None, raw=None):
    body = raw if raw is not None else json.dumps(payload, separators=(",", ":")).encode()
    stamp = int(time.time()) if timestamp is None else timestamp
    headers = {"HTTP_X_ERPLORA_TIMESTAMP": str(stamp), "HTTP_X_ERPLORA_SIGNATURE": sign(body, stamp, secret)}
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    return client.post(path, data=body, content_type="application/json", HTTP_HOST="localhost", **headers)


def send(client, payload=None, **kwargs):
    payload = payload or {"hub": "bar-manolo", "to": "+34600111222", "type": "text", "text": "Sí, mañana a las 10"}
    return door(client, "/internal/whatsapp/send", payload, **kwargs)


def error_code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def internal(settings, whatsapp_on):
    settings.INTERNAL_SHARED_SECRET = SECRET
    return settings


@pytest.fixture
def number(internal, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id=PHONE_NUMBER_ID, display_phone="+34 910 00 00 00", waba_id="W",
        access_token="EAAG-token",
    )


def used(hub) -> int:
    row = Usage.objects.filter(hub=hub).first()
    return row.used if row else 0


@pytest.mark.django_db
class TestTheDoorsShape:
    def test_an_unsigned_call_is_refused_and_meta_never_called(self, client, number):
        with respx.mock:
            meta = respx.post(SEND)
            response = send(client, secret="not-the-secret")

        assert (response.status_code, error_code(response)) == (401, "unauthorized")
        assert not meta.called

    def test_a_stale_call_is_refused(self, client, number):
        assert send(client, timestamp=int(time.time()) - 301).status_code == 401

    def test_only_post(self, client, number):
        response = client.get("/internal/whatsapp/send", HTTP_HOST="localhost")

        assert response.status_code == 405

    @pytest.mark.parametrize(
        "payload",
        [
            {"hub": "bar-manolo", "type": "text", "text": "x"},
            {"hub": "bar-manolo", "to": "600", "type": "text", "text": "x"},
            {"hub": "bar-manolo", "to": "+34600111222", "type": "text", "text": "  "},
            {"hub": "bar-manolo", "to": "+34600111222", "type": "template"},
            {"hub": "bar-manolo", "to": "+34600111222", "type": "text", "text": "x", "template": {"name": "a", "language": "es"}},
            {"hub": "bar-manolo", "to": "+34600111222", "type": "image"},
        ],
    )
    def test_a_body_out_of_the_contract_is_422(self, client, number, payload):
        response = send(client, payload)

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")

    def test_a_body_that_is_not_json_is_422(self, client, number):
        assert send(client, raw=b"nope").status_code == 422

    def test_without_its_key_nothing_is_sent(self, client, number):
        response = send(client, key=None)

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert "Idempotency-Key" in response.json()["error"]["message"]

    def test_a_key_over_255_characters_is_422(self, client, number):
        assert send(client, key="k" * 256).status_code == 422

    def test_a_business_the_saas_does_not_know_is_404(self, client, number):
        """saas#2599: a demo is no business of the SaaS; it can never send from ERPlora's Meta app."""
        response = send(client, {"hub": "demo-1a2b3c4d", "to": "+34600111222", "type": "text", "text": "x"})

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")

    def test_a_business_being_deleted_does_not_send(self, client, number, business):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert send(client).status_code == 404


@pytest.mark.django_db
class TestSending:
    @respx.mock
    def test_a_text_goes_to_meta_with_the_numbers_token(self, client, number, business):
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        response = send(client)

        assert (response.status_code, response.json()) == (200, {"wa_message_id": "wamid.HBgLMzQ2MDAxMTEyMjIVAgARGBI"})
        request = meta.calls.last.request
        assert request.headers["Authorization"] == "Bearer EAAG-token"
        assert json.loads(request.content) == {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "34600111222",
            "type": "text",
            "text": {"preview_url": False, "body": "Sí, mañana a las 10"},
        }
        assert used(business) == 1
        assert Send.objects.get().wa_message_id == "wamid.HBgLMzQ2MDAxMTEyMjIVAgARGBI"

    @respx.mock
    def test_sending_moves_the_snapshot_forward(self, client, number, business):
        """The month's usage is in the ``whatsapp`` key of the snapshot: the Hub learns it with a newer version."""
        respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))
        before = Hub.objects.get(pk=business.pk).state_version

        send(client)

        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_a_template_goes_with_its_language_and_variables(self, client, number):
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        send(client, {"hub": "bar-manolo", "to": "+34600111222", "type": "template",
                      "template": {"name": "recordatorio", "language": "es", "variables": ["Ana", "viernes"]}})

        assert json.loads(meta.calls.last.request.content)["template"] == {
            "name": "recordatorio",
            "language": {"code": "es"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": "Ana"}, {"type": "text", "text": "viernes"}]}],
        }

    @respx.mock
    def test_a_template_meta_has_not_approved_does_not_leave(self, client, number, business):
        Template.objects.create(hub=business, name="recordatorio", language="es", status="PENDING")
        meta = respx.post(SEND)

        response = send(client, {"hub": "bar-manolo", "to": "+34600111222", "type": "template",
                                 "template": {"name": "recordatorio", "language": "es"}})

        assert (response.status_code, error_code(response)) == (409, "whatsapp.template_not_approved")
        assert not meta.called and used(business) == 0

    @respx.mock
    def test_a_template_made_in_whatsapp_manager_is_metas_to_judge(self, client, number):
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        response = send(client, {"hub": "bar-manolo", "to": "+34600111222", "type": "template",
                                 "template": {"name": "otra", "language": "es"}})

        assert response.status_code == 200 and meta.called

    def test_without_a_connected_number_nothing_leaves(self, client, number, business):
        PhoneNumber.objects.filter(pk=number.pk).update(is_active=False)

        response = send(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
        assert used(business) == 0

    def test_a_number_whose_token_cannot_be_read_is_not_connected(self, client, number, settings):
        settings.FERNET_KEY = "SWDVBWsq5tg7Eo92t5sGAbJr_rvRBe0wPKwAaX5pvI8="

        assert error_code(send(client)) == "whatsapp.not_connected"


@pytest.mark.django_db
class TestTheSameKeyNeverSendsTwice:
    @respx.mock
    def test_a_retry_gets_the_first_answer_without_a_second_send_or_charge(self, client, number, business):
        """saas#2633: the Hub retries a send it could not confirm with the same key."""
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        first = send(client)
        Plan.objects.update(whatsapp_messages_per_month=1)  # the allowance filled meanwhile
        second = send(client)

        assert first.json() == second.json() and second.status_code == 200
        assert meta.call_count == 1 and used(business) == 1

    def test_a_key_still_on_its_way_answers_5xx_so_the_hub_retries(self, client, number):
        Send.objects.create(hub=number.hub, idempotency_key=KEY, month=timezone.now().strftime("%Y-%m"))

        with respx.mock:
            meta = respx.post(SEND)
            response = send(client)

        assert (response.status_code, error_code(response)) == (503, "whatsapp.send_in_progress")
        assert not meta.called

    @respx.mock
    def test_the_same_key_of_another_business_is_another_message(self, client, number, other_business):
        PhoneNumber.objects.create(hub=other_business, phone_number_id="2", display_phone="+34 2", waba_id="W2", access_token="t")
        respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))
        other = respx.post(f"{GRAPH}/2/messages").mock(return_value=httpx.Response(200, json={"messages": [{"id": "wamid.2"}]}))

        send(client)
        response = send(client, {"hub": "bar-pepe", "to": "+34600111222", "type": "text", "text": "x"})

        assert response.json() == {"wa_message_id": "wamid.2"} and other.called

    @respx.mock
    def test_meta_accepting_without_an_id_is_never_sent_again(self, client, number, business):
        """saas#2653: Meta took it (2xx) but gave no id: the Hub reads «unknown» and retries; erplora.com never sends it
        again, and it counts."""
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json={"messaging_product": "whatsapp"}))

        first = send(client)
        second = send(client)

        assert first.status_code == second.status_code == 502
        assert error_code(second) == "whatsapp.meta_no_id"
        assert meta.call_count == 1 and used(business) == 1

    @respx.mock
    def test_an_answer_meta_never_gave_keeps_the_place_and_resends_after_two_minutes(self, client, number, business):
        meta = respx.post(SEND).mock(side_effect=httpx.ReadTimeout("slow"))

        first = send(client)
        soon = send(client)
        Send.objects.update(updated_at=timezone.now() - timedelta(minutes=3))
        meta.mock(return_value=httpx.Response(200, json=ACCEPTED))
        later = send(client)

        assert (first.status_code, error_code(first)) == (502, "whatsapp.meta_unknown")
        assert (soon.status_code, error_code(soon)) == (503, "whatsapp.send_in_progress")
        assert later.status_code == 200
        assert meta.call_count == 2 and used(business) == 1


@pytest.mark.django_db
class TestMetasRefusals:
    @pytest.mark.parametrize(
        ("meta_code", "code"),
        [
            (131047, "whatsapp.window_closed"),
            (470, "whatsapp.window_closed"),
            (131026, "whatsapp.recipient_blocked"),
            (131050, "whatsapp.recipient_blocked"),
            (132001, "whatsapp.template_not_approved"),
            (132015, "whatsapp.template_not_approved"),
            (100, "whatsapp.meta_rejected"),
        ],
    )
    @respx.mock
    def test_a_refusal_is_409_with_its_code_and_frees_the_place(self, client, number, business, meta_code, code):
        meta = respx.post(SEND).mock(
            return_value=httpx.Response(400, json={"error": {"message": f"(#{meta_code}) Meta says no", "code": meta_code}})
        )

        response = send(client)
        again = send(client)

        assert (response.status_code, error_code(response)) == (409, code)
        assert "Meta says no" in response.json()["error"]["message"]
        # Nothing left, nothing counts, and the same key can go out again (the Hub's «Retry»).
        assert used(business) == 0 and meta.call_count == 2 and again.status_code == 409

    @respx.mock
    def test_metas_rate_limit_is_a_429_that_left_nothing(self, client, number, business):
        respx.post(SEND).mock(return_value=httpx.Response(400, json={"error": {"message": "Throughput", "code": 130429}}))

        response = send(client)

        assert (response.status_code, error_code(response)) == (429, "whatsapp.meta_rate_limited")
        assert used(business) == 0

    def test_an_expired_or_withdrawn_permission_asks_to_reconnect_and_tells_the_hub(
        self, client, number, business, hub_double, django_capture_on_commit_callbacks
    ):
        """FIX-SAAS-WHATSAPP-EXPIRED-TOKEN-SAYS-NOT-CONNECTED (WHATSAPP-F06, F03): Meta's 190 (the business's
        permission expired, or the business withdrew it in Meta) is not «not connected»: only connecting the number
        again fixes it. The answer says so with its own code, the number is marked «needs reconnecting» and the Hub
        gets the snapshot that says it, with a newer version."""
        before = Hub.objects.get(pk=business.pk).state_version
        with respx.mock:
            respx.route(url__startswith=hub_double.url).pass_through()
            respx.post(SEND).mock(
                return_value=httpx.Response(
                    401, json={"error": {"message": "Session has expired", "type": "OAuthException", "code": 190}}
                )
            )
            with django_capture_on_commit_callbacks(execute=True):
                response = send(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
        assert "Session has expired" in response.json()["error"]["message"]
        assert PhoneNumber.objects.get(pk=number.pk).needs_reconnect is True
        assert used(business) == 0 and not Send.objects.exists()
        version = Hub.objects.get(pk=business.pk).state_version
        assert version > before
        pushed = hub_double.calls_to("PUT", f"/internal/hubs/{business.pk}/state")[-1].body
        assert (pushed["version"], pushed["whatsapp"]["status"]) == (version, "reconnect_needed")

    @pytest.mark.parametrize("meta_code", [10, 200, 131031, 133010])
    @respx.mock
    def test_metas_other_connection_refusals_stay_not_connected_and_mark_nothing(self, client, number, meta_code):
        """Only 190 is the permission to reconnect: the other codes of a number Meta will not send from keep
        ``whatsapp.not_connected`` and leave the number as it was."""
        respx.post(SEND).mock(
            return_value=httpx.Response(400, json={"error": {"message": f"(#{meta_code}) Meta says no", "code": meta_code}})
        )

        response = send(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
        assert PhoneNumber.objects.get(pk=number.pk).needs_reconnect is False

    @respx.mock
    def test_meta_unreachable_left_nothing_and_the_hub_retries(self, client, number, business):
        meta = respx.post(SEND).mock(side_effect=httpx.ConnectError("down"))

        response = send(client)

        assert (response.status_code, error_code(response)) == (503, "whatsapp.meta_unreachable")
        assert used(business) == 0 and not Send.objects.exists()
        meta.mock(return_value=httpx.Response(200, json=ACCEPTED))
        assert send(client).status_code == 200


@pytest.mark.django_db
class TestTheMonthsAllowance:
    def test_a_free_business_sends_its_plans_thirty_then_stops(self, client, number, business):
        Usage.objects.create(hub=business, month=timezone.now().strftime("%Y-%m"), used=30)

        with respx.mock:
            meta = respx.post(SEND)
            response = send(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.cap_reached")
        assert not meta.called

    @respx.mock
    def test_a_plan_of_zero_includes_none(self, client, number, business):
        Plan.objects.update(whatsapp_messages_per_month=0)

        assert error_code(send(client)) == "whatsapp.cap_reached"

    @respx.mock
    def test_the_paid_plan_gives_its_own_allowance(self, client, number, business):
        Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))
        Usage.objects.create(hub=business, month=timezone.now().strftime("%Y-%m"), used=30)
        respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        assert send(client).status_code == 200
        assert used(business) == 31

    @respx.mock
    def test_last_months_count_does_not_spend_this_ones(self, client, number, business):
        Usage.objects.create(hub=business, month="2000-01", used=30)
        respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        assert send(client).status_code == 200


def waiting_on_a_lock(count: int, *, within: float) -> bool:
    """Whether ``count`` other sessions of this test database wait on a lock, before ``within`` seconds."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0] >= count:
                return True
        time.sleep(0.05)
    return False


#: The sends that race for the last message of the month (see the test below for why six).
SENDERS = 6


@pytest.mark.django_db(transaction=True)
def test_simultaneous_sends_cannot_pass_the_cap_together(make_user, settings, whatsapp_on):
    """saas#2652: with one message left, six sends at once: one leaves, five are refused.

    To make them meet where it matters, as several processes would, another connection holds the month's counter
    until the six wait on it (each one has already read it by then); then it lets go. Six, because with the test's
    own connection and the one holding the counter they fill the pool (``max_size`` 8): a seventh would wait for a
    connection instead of for the counter. A reservation
    that read the counter and wrote it apart would let the six through; ``UPDATE … WHERE used < limit`` lets one.
    The place is reserved before Meta is called, so Meta's slowness opens no window either."""
    from django.db import transaction

    from hubs.tests.conftest import create_business, put_the_catalogue_back

    settings.INTERNAL_SHARED_SECRET = SECRET
    put_the_catalogue_back()
    business = create_business(make_user("race@example.com"))
    PhoneNumber.objects.create(hub=business, phone_number_id=PHONE_NUMBER_ID, display_phone="+34", waba_id="W", access_token="t")
    month = timezone.now().strftime("%Y-%m")
    Usage.objects.create(hub=business, month=month, used=29)
    held, release = threading.Event(), threading.Event()
    answers = []

    def hold_the_counter():
        try:
            with transaction.atomic():
                Usage.objects.select_for_update().get(hub=business, month=month)
                held.set()
                release.wait(10)
        finally:
            connection.close()

    def one(key):
        try:
            payload = {"hub": business.slug, "to": "+34600111222", "type": "text", "text": key}
            answers.append(send(Client(), payload, key=key).status_code)
        finally:
            connection.close()

    with respx.mock:
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))
        holder = threading.Thread(target=hold_the_counter)
        holder.start()
        assert held.wait(5)
        senders = [threading.Thread(target=one, args=(f"k{n}",)) for n in range(SENDERS)]
        for thread in senders:
            thread.start()
        # Let go only once the six wait on the counter (each one has read it by then): never on a guess of time,
        # which a loaded machine outruns (the read-then-write mutant once survived a fixed second).
        assert waiting_on_a_lock(SENDERS, within=30), "the sends never met at the month's counter"
        release.set()
        for thread in (holder, *senders):
            thread.join(15)

    assert sorted(answers) == [200] + [409] * (SENDERS - 1)
    assert meta.call_count == 1
    assert Usage.objects.get(hub=business, month=month).used == 30


@pytest.mark.django_db
class TestForgettingANumber:
    def test_door_6_forgets_the_numbers_messages_and_those_ids_of_this_business_only(self, client, number, business, other_business):
        for hub, wamid, contact in ((business, "wamid.1", "34600111222"), (business, "wamid.2", "34611000000"),
                                    (business, "wamid.3", "34611000000"), (other_business, "wamid.9", "34600111222")):
            Delivery.objects.create(hub=hub, kind=Delivery.Kind.MESSAGE, wa_message_id=wamid, contact=contact)
        Delivery.objects.create(hub=business, kind=Delivery.Kind.STATUS, wa_message_id="wamid.2")

        response = door(client, "/internal/whatsapp/erase",
                        {"hub": "bar-manolo", "phone": "+34600111222", "wa_message_ids": ["wamid.2"]}, key=None)

        assert (response.status_code, response.json()) == (200, {"erased": True})
        left = sorted(Delivery.objects.values_list("hub__slug", "kind", "wa_message_id"))
        assert left == [("bar-manolo", "message", "wamid.3"), ("bar-pepe", "message", "wamid.9")]

    def test_door_6_for_an_unknown_business_is_404(self, client, internal):
        response = door(client, "/internal/whatsapp/erase", {"hub": "nobody", "phone": "+34600111222", "wa_message_ids": []}, key=None)

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")

    def test_door_6_needs_a_number(self, client, number):
        response = door(client, "/internal/whatsapp/erase", {"hub": "bar-manolo", "wa_message_ids": []}, key=None)

        assert response.status_code == 422
