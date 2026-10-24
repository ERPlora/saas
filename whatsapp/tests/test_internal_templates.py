"""WHATSAPP-G15, WHATSAPP-G17 · Door 8, ``POST /internal/whatsapp/templates``, and door 9,
``POST /internal/whatsapp/templates/delete`` (the Hub's WORKBOOK ``whatsapp_inbox``, «Contrato con el SaaS»), and the
mirror of Meta's templates the Hub's snapshot carries.

Door 8 registers a template at Meta (new, or with ``meta_id`` an edit of the one Meta has) once per
``Idempotency-Key``: 200 ``{"meta_id", "status"}``; 409 ``whatsapp.template_invalid | meta_unreachable |
meta_rate_limited | not_connected | reconnect_needed`` with Meta's reason = not taken (``reconnect_needed``: Meta's 190,
the number marked «needs reconnecting»). Door 9 deletes that one template in that language: 200 ``{"deleted": true}``,
or 404 ``whatsapp.template_not_found`` when Meta no longer has it; anything else keeps it.

Meta is replaced at the HTTP border only (``respx``), with Meta's documented bodies. Cases of the old product's
``test_templates.py`` and ``test_whatsapp_templates_door.py``.
"""

import json
from datetime import timedelta

import httpx
import pytest
import respx
from django.utils import timezone

from hubs.models import Hub
from whatsapp import gateway, queries
from whatsapp.models import PhoneNumber, Template, TemplateSubmission
from whatsapp.tests.conftest import GRAPH
from whatsapp.tests.test_internal import door, error_code, internal, number  # noqa: F401 - shared fixtures

TEMPLATES = f"{GRAPH}/W/message_templates"
META_ID = "594425479261596"
CREATED = {"id": META_ID, "status": "PENDING", "category": "UTILITY"}
SUBMIT_KEY = "0199e7c2-0000-7000-8000-0000000000aa"


def template_body(**fields) -> dict:
    return {
        "hub": "bar-manolo",
        "name": "recordatorio",
        "language": "es",
        "category": "UTILITY",
        "header": "Tu cita",
        "body": "Hola {{1}}, te esperamos el {{2}}.",
        "body_examples": ["Ana", "viernes"],
        "footer": "Peluquería Ana",
        "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}],
        "meta_id": "",
        **fields,
    }


def submit(client, payload=None, *, key=SUBMIT_KEY, **kwargs):
    return door(client, "/internal/whatsapp/templates", payload or template_body(), key=key, **kwargs)


def remove(client, payload=None, **kwargs):
    payload = payload or {"hub": "bar-manolo", "name": "recordatorio", "language": "es", "meta_id": META_ID}
    return door(client, "/internal/whatsapp/templates/delete", payload, key=None, **kwargs)


def refused(status: int, code: int, *, subcode: int | None = None, user_msg: str = "", message: str = "Invalid parameter"):
    error = {"message": message, "type": "OAuthException", "code": code, "fbtrace_id": "A1b2"}
    if subcode is not None:
        error["error_subcode"] = subcode
    if user_msg:
        error["error_user_title"] = "Template refused"
        error["error_user_msg"] = user_msg
    return httpx.Response(status, json={"error": error})


def mirrored(hub, **fields) -> Template:
    values = {"name": "recordatorio", "language": "es", "status": "APPROVED", "meta_id": META_ID, "body": "Hola {{1}}",
              "body_examples": ["Ana"], "variables": 1, **fields}
    return Template.objects.create(hub=hub, **values)


@pytest.mark.django_db
class TestRegistering:
    @respx.mock
    def test_a_new_template_is_created_at_meta_with_its_components(self, client, number, business):
        meta = respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))

        response = submit(client)

        assert (response.status_code, response.json()) == (200, {"meta_id": META_ID, "status": "PENDING"})
        sent = meta.calls.last.request
        assert json.loads(sent.content) == {
            "name": "recordatorio",
            "language": "es",
            "category": "UTILITY",
            "components": [
                {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
                {"type": "BODY", "text": "Hola {{1}}, te esperamos el {{2}}.", "example": {"body_text": [["Ana", "viernes"]]}},
                {"type": "FOOTER", "text": "Peluquería Ana"},
                {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}]},
            ],
        }
        assert sent.headers["Authorization"] == "Bearer EAAG-token"
        assert "EAAG-token" not in str(sent.url)

    @respx.mock
    def test_the_mirror_keeps_what_meta_took_and_the_hub_learns_it(self, client, number, business):
        respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))
        before = Hub.objects.get(pk=business.pk).state_version

        submit(client)

        row = Template.objects.get(hub=business)
        assert (row.meta_id, row.status, row.category, row.body, row.body_examples, row.variables) == (
            META_ID, "PENDING", "UTILITY", "Hola {{1}}, te esperamos el {{2}}.", ["Ana", "viernes"], 2
        )
        assert (row.header_format, row.header, row.footer) == ("TEXT", "Tu cita", "Peluquería Ana")
        assert Hub.objects.get(pk=business.pk).state_version > before
        assert [t["meta_id"] for t in queries.channel_block(business.id)["templates"]] == [META_ID]

    @respx.mock
    def test_a_named_template_is_registered_as_named(self, client, number):
        meta = respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))

        submit(client, template_body(body="Hola {{nombre}}", body_examples=["Ana"]))

        sent = json.loads(meta.calls.last.request.content)
        assert sent["parameter_format"] == "NAMED"
        assert sent["components"][1]["example"] == {"body_text_named_params": [{"param_name": "nombre", "example": "Ana"}]}

    @respx.mock
    def test_with_its_meta_id_the_template_is_edited_on_its_own_node(self, client, number, business):
        mirrored(business, status="APPROVED", rejected_reason="")
        create = respx.post(TEMPLATES)
        edit = respx.post(f"{GRAPH}/{META_ID}").mock(return_value=httpx.Response(200, json={"success": True}))

        response = submit(client, template_body(meta_id=META_ID, body="Hola {{1}}, hasta el {{2}}."))

        assert (response.status_code, response.json()) == (200, {"meta_id": META_ID, "status": "PENDING"})
        assert not create.called
        assert set(json.loads(edit.calls.last.request.content)) == {"category", "components"}
        row = Template.objects.get(hub=business)
        assert (row.status, row.body) == ("PENDING", "Hola {{1}}, hasta el {{2}}.")

    @respx.mock
    def test_the_same_key_never_registers_twice(self, client, number):
        meta = respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))

        first = submit(client)
        again = submit(client)

        assert meta.call_count == 1
        assert again.status_code == 200
        assert again.json() == first.json()

    @respx.mock
    def test_another_key_registers_again(self, client, number):
        meta = respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))
        respx.post(f"{GRAPH}/{META_ID}").mock(return_value=httpx.Response(200, json={"success": True}))

        submit(client)
        submit(client, template_body(meta_id=META_ID), key="another-key")

        assert meta.call_count == 1
        assert TemplateSubmission.objects.count() == 2

    @respx.mock
    def test_meta_saying_it_already_has_it_adopts_its_id_and_edits_it(self, client, number, business):
        """A first call reached Meta and its answer was lost: the retry finds Meta's template instead of failing."""
        respx.post(TEMPLATES).mock(return_value=refused(400, 100, subcode=2388024, user_msg="Ya existe en este idioma."))
        listed = respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": [
            {"id": "778", "name": "recordatorio", "language": "en", "status": "APPROVED"},
            {"id": "777", "name": "recordatorio", "language": "es", "status": "APPROVED"},
        ]}))
        edit = respx.post(f"{GRAPH}/777").mock(return_value=httpx.Response(200, json={"success": True}))

        response = submit(client)

        assert (response.status_code, response.json()) == (200, {"meta_id": "777", "status": "PENDING"})
        assert listed.calls.last.request.url.params["name"] == "recordatorio"
        assert edit.called
        assert Template.objects.get(hub=business).meta_id == "777"

    @respx.mock
    def test_the_same_template_name_of_another_business_is_its_own(self, client, number, business, other_business):
        PhoneNumber.objects.create(hub=other_business, phone_number_id="2", display_phone="+34 911", waba_id="W2",
                                   access_token="EAAG-other")
        mirrored(other_business, meta_id="999")
        respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))

        submit(client)

        assert Template.objects.get(hub=other_business).meta_id == "999"
        assert Template.objects.get(hub=business).meta_id == META_ID


@pytest.mark.django_db
class TestNotTaken:
    def test_a_template_meta_would_refuse_never_reaches_meta(self, client, number, business):
        with respx.mock:
            meta = respx.post(TEMPLATES)
            response = submit(client, template_body(body="Hola {{1}}", body_examples=[]))

        assert (response.status_code, error_code(response)) == (409, "whatsapp.template_invalid")
        assert "example" in response.json()["error"]["message"]
        assert not meta.called
        assert not Template.objects.exists() and not TemplateSubmission.objects.exists()

    @respx.mock
    def test_metas_refusal_is_a_409_with_its_reason_and_nothing_is_kept(self, client, number):
        meta = respx.post(TEMPLATES).mock(
            return_value=refused(400, 100, subcode=2388019, user_msg="El texto supera el límite de caracteres.")
        )

        response = submit(client)
        submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.template_invalid")
        assert "El texto supera el límite de caracteres." in response.json()["error"]["message"]
        assert meta.call_count == 2, "a refused key is free to try again"
        assert not Template.objects.exists()

    @pytest.mark.parametrize("answer", [refused(429, 4), refused(400, 80008)])
    @respx.mock
    def test_a_rate_limit_is_a_retry_not_a_rejection(self, client, number, answer):
        respx.post(TEMPLATES).mock(return_value=answer)

        response = submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_rate_limited")

    @pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
    @respx.mock
    def test_meta_unreachable_is_not_meta_refusing(self, client, number, failure):
        meta = respx.post(TEMPLATES).mock(side_effect=failure)

        response = submit(client)
        submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_unreachable")
        assert meta.call_count == 2
        assert not Template.objects.exists()

    @respx.mock
    def test_meta_failing_with_a_5xx_is_unreachable_too(self, client, number):
        respx.post(TEMPLATES).mock(return_value=httpx.Response(503))

        assert error_code(submit(client)) == "whatsapp.meta_unreachable"

    @respx.mock
    def test_an_expired_permission_asks_the_business_to_connect_again(self, client, number, business):
        respx.post(TEMPLATES).mock(return_value=refused(401, 190, message="Error validating access token"))
        before = Hub.objects.get(pk=business.pk).state_version

        response = submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is True
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_an_expired_permission_editing_one_asks_to_connect_again_too(self, client, number, business):
        mirrored(business)
        respx.post(f"{GRAPH}/{META_ID}").mock(return_value=refused(401, 190, message="Error validating access token"))

        response = submit(client, template_body(meta_id=META_ID))

        assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is True

    @pytest.mark.parametrize("code", sorted(gateway.NOT_CONNECTED - {gateway.EXPIRED_PERMISSION}))
    @respx.mock
    def test_any_other_lost_connection_is_not_connected_and_marks_nothing(self, client, number, business, code):
        respx.post(TEMPLATES).mock(return_value=refused(403, code, message="Permission denied"))

        response = submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is False

    def test_a_business_without_a_number_has_no_account_to_register_into(self, client, internal, business):
        with respx.mock:
            meta = respx.post(TEMPLATES)
            response = submit(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
        assert not meta.called

    def test_a_hub_the_saas_does_not_know_is_404(self, client, number):
        response = submit(client, template_body(hub="nadie"))

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")

    def test_a_key_on_its_way_is_not_registered_a_second_time_at_once(self, client, number, business):
        TemplateSubmission.objects.create(hub=business, idempotency_key=SUBMIT_KEY)

        with respx.mock:
            meta = respx.post(TEMPLATES)
            response = submit(client)

        assert (response.status_code, error_code(response)) == (503, "whatsapp.template_in_progress")
        assert not meta.called

    @respx.mock
    def test_a_key_whose_call_died_long_ago_registers_again(self, client, number, business):
        stuck = TemplateSubmission.objects.create(hub=business, idempotency_key=SUBMIT_KEY)
        TemplateSubmission.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - timedelta(minutes=3))
        respx.post(TEMPLATES).mock(return_value=httpx.Response(200, json=CREATED))

        assert submit(client).status_code == 200

    def test_the_key_is_required(self, client, number):
        response = submit(client, key=None)

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")

    def test_an_unsigned_call_is_refused(self, client, number):
        assert submit(client, secret="not-the-secret").status_code == 401


@pytest.mark.django_db
class TestDeleting:
    @respx.mock
    def test_that_one_template_is_deleted_at_meta_and_from_the_mirror(self, client, number, business):
        mirrored(business)
        english = mirrored(business, language="en", meta_id="778")
        meta = respx.delete(TEMPLATES).mock(return_value=httpx.Response(200, json={"success": True}))
        before = Hub.objects.get(pk=business.pk).state_version

        response = remove(client)

        assert (response.status_code, response.json()) == (200, {"deleted": True})
        assert dict(meta.calls.last.request.url.params) == {"hsm_id": META_ID, "name": "recordatorio"}
        assert list(Template.objects.filter(hub=business)) == [english]
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_without_its_id_the_mirrors_is_used(self, client, number, business):
        mirrored(business)
        meta = respx.delete(TEMPLATES).mock(return_value=httpx.Response(200, json={"success": True}))

        remove(client, {"hub": "bar-manolo", "name": "recordatorio", "language": "es", "meta_id": ""})

        assert meta.calls.last.request.url.params["hsm_id"] == META_ID

    @respx.mock
    def test_without_any_id_meta_is_asked_for_it(self, client, number):
        respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": [
            {"id": "777", "name": "recordatorio", "language": "es", "status": "APPROVED"}]}))
        meta = respx.delete(TEMPLATES).mock(return_value=httpx.Response(200, json={"success": True}))

        response = remove(client, {"hub": "bar-manolo", "name": "recordatorio", "language": "es"})

        assert response.status_code == 200
        assert meta.calls.last.request.url.params["hsm_id"] == "777"

    @respx.mock
    def test_one_meta_does_not_have_is_404_template_not_found(self, client, number, business):
        mirrored(business, meta_id="")
        respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": [
            {"id": "778", "name": "recordatorio", "language": "en", "status": "APPROVED"}]}))
        meta = respx.delete(TEMPLATES)

        response = remove(client, {"hub": "bar-manolo", "name": "recordatorio", "language": "es"})

        assert (response.status_code, error_code(response)) == (404, "whatsapp.template_not_found")
        assert not meta.called
        assert not Template.objects.filter(hub=business, language="es").exists()

    @respx.mock
    def test_meta_refusing_one_it_no_longer_has_is_404_template_not_found(self, client, number, business):
        mirrored(business)
        respx.delete(TEMPLATES).mock(return_value=refused(400, 100, message="Invalid parameter"))
        respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": []}))

        response = remove(client)

        assert (response.status_code, error_code(response)) == (404, "whatsapp.template_not_found")
        assert not Template.objects.filter(hub=business).exists()

    @respx.mock
    def test_meta_refusing_one_it_still_has_keeps_it_and_says_why(self, client, number, business):
        mirrored(business)
        respx.delete(TEMPLATES).mock(return_value=refused(400, 100, user_msg="No se puede borrar ahora."))
        respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": [
            {"id": META_ID, "name": "recordatorio", "language": "es", "status": "APPROVED"}]}))

        response = remove(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.meta_rejected")
        assert "No se puede borrar ahora." in response.json()["error"]["message"]
        assert Template.objects.filter(hub=business).exists()

    @pytest.mark.parametrize(
        ("answer", "code"),
        [(refused(429, 4), "whatsapp.meta_rate_limited"), (httpx.Response(500), "whatsapp.meta_unreachable")],
    )
    @respx.mock
    def test_meta_not_answering_keeps_it(self, client, number, business, answer, code):
        mirrored(business)
        respx.delete(TEMPLATES).mock(return_value=answer)

        response = remove(client)

        assert (response.status_code, error_code(response)) == (409, code)
        assert Template.objects.filter(hub=business).exists()

    @respx.mock
    def test_an_expired_permission_keeps_it_and_asks_to_connect_again(self, client, number, business):
        mirrored(business)
        respx.delete(TEMPLATES).mock(return_value=refused(401, 190, message="Error validating access token"))
        before = Hub.objects.get(pk=business.pk).state_version

        response = remove(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
        assert Template.objects.filter(hub=business).exists()
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is True
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_an_expired_permission_asking_meta_for_its_id_asks_to_connect_again(self, client, number, business):
        respx.get(TEMPLATES).mock(return_value=refused(401, 190, message="Error validating access token"))
        meta = respx.delete(TEMPLATES)

        response = remove(client, {"hub": "bar-manolo", "name": "recordatorio", "language": "es"})

        assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
        assert not meta.called
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is True

    @pytest.mark.parametrize("code", sorted(gateway.NOT_CONNECTED - {gateway.EXPIRED_PERMISSION}))
    @respx.mock
    def test_any_other_lost_connection_keeps_it_as_not_connected(self, client, number, business, code):
        mirrored(business)
        respx.delete(TEMPLATES).mock(return_value=refused(403, code, message="Permission denied"))

        response = remove(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
        assert Template.objects.filter(hub=business).exists()
        assert PhoneNumber.objects.get(hub=business).needs_reconnect is False

    def test_a_business_without_a_number_cannot_delete_at_meta(self, client, internal, business):
        response = remove(client)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")

    def test_a_hub_the_saas_does_not_know_is_its_own_404(self, client, number):
        response = remove(client, {"hub": "nadie", "name": "recordatorio", "language": "es"})

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")

    @respx.mock
    def test_another_business_never_deletes_this_ones_template(self, client, number, business, other_business):
        mirrored(other_business)
        respx.delete(TEMPLATES).mock(return_value=httpx.Response(200, json={"success": True}))

        remove(client)

        assert Template.objects.filter(hub=other_business).exists()


@pytest.mark.django_db
class TestTheMirror:
    @respx.mock
    def test_metas_list_is_read_page_by_page_and_what_it_lost_goes(self, number, business):
        mirrored(business, name="vieja", meta_id="1")
        pages = respx.get(TEMPLATES).mock(side_effect=[
            httpx.Response(200, json={"data": [{"id": "2", "name": "a", "language": "es", "status": "APPROVED",
                                                "components": [{"type": "BODY", "text": "Hola"}]}],
                                      "paging": {"cursors": {"after": "QVFI"}, "next": f"{TEMPLATES}?after=QVFI"}}),
            httpx.Response(200, json={"data": [{"id": "3", "name": "b", "language": "en", "status": "REJECTED",
                                                "rejected_reason": "INVALID_FORMAT"}], "paging": {"cursors": {}}}),
        ])
        before = Hub.objects.get(pk=business.pk).state_version

        gateway.sync_templates(business.id)

        assert pages.calls[1].request.url.params["after"] == "QVFI"
        assert "EAAG-token" not in str(pages.calls[0].request.url)
        assert sorted(Template.objects.filter(hub=business).values_list("name", "status", "rejected_reason")) == [
            ("a", "APPROVED", ""), ("b", "REJECTED", "INVALID_FORMAT")
        ]
        assert Hub.objects.get(pk=business.pk).state_version > before

    @respx.mock
    def test_a_list_that_did_not_come_whole_never_deletes(self, number, business):
        mirrored(business, name="vieja", meta_id="1")
        respx.get(TEMPLATES).mock(side_effect=[
            httpx.Response(200, json={"data": [{"id": "2", "name": "a", "language": "es", "status": "APPROVED"}],
                                      "paging": {"cursors": {"after": "QVFI"}, "next": f"{TEMPLATES}?after=QVFI"}}),
            httpx.Response(500),
        ])

        gateway.sync_templates(business.id)

        assert sorted(Template.objects.filter(hub=business).values_list("name", flat=True)) == ["a", "vieja"]

    @respx.mock
    def test_meta_down_leaves_the_mirror_as_it_was(self, number, business):
        mirrored(business)
        respx.get(TEMPLATES).mock(side_effect=httpx.ConnectError("down"))

        gateway.sync_templates(business.id)

        assert Template.objects.filter(hub=business).count() == 1

    def test_a_business_without_a_number_reads_nothing(self, internal, business):
        with respx.mock:
            meta = respx.get(TEMPLATES)
            gateway.sync_templates(business.id)

        assert not meta.called

    @respx.mock
    def test_a_verdict_on_a_template_the_mirror_lacks_reads_metas_list(self, number, business):
        listed = respx.get(TEMPLATES).mock(return_value=httpx.Response(200, json={"data": [
            {"id": "55", "name": "nueva", "language": "es", "status": "APPROVED"}]}))
        verdict = {"object": "whatsapp_business_account", "entry": [{"id": "W", "time": 1, "changes": [{
            "field": "message_template_status_update",
            "value": {"event": "APPROVED", "message_template_id": 55, "message_template_name": "nueva",
                      "message_template_language": "es", "reason": "NONE"}}]}]}

        gateway.ingest(verdict)

        assert listed.called
        assert Template.objects.get(hub=business).meta_id == "55"
