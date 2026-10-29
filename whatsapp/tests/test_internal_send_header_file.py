"""WHATSAPP-F06, WHATSAPP_INBOX-F33 · Door 5 sends a template whose header is a photo, a video or a document.

The Hub hands the header's file with the template (``header_format`` + ``header_sample`` in base64, as door 8 does):
erplora.com tells it by its first bytes, never by its name, within Meta's limits, uploads it to the business's number
(``POST /<PHONE_NUMBER_ID>/media``) and sends the template with the header's parameter naming that upload's id. The
upload never sends a message: whatever happens to it, the place and the key are free and nothing left. The same key
never uploads nor sends twice. Meta is replaced at the HTTP border only (``respx``). A failure of Meta is said as
Meta's (gh:hub#2731).
"""

import base64
import json

import httpx
import pytest
import respx

from whatsapp.models import PhoneNumber, Send
from whatsapp.tests.conftest import GRAPH
from whatsapp.tests.test_internal import ACCEPTED, PHONE_NUMBER_ID, SEND, error_code, send, used
from whatsapp.tests.test_internal import internal, number  # noqa: F401 - fixtures

MEDIA = f"{GRAPH}/{PHONE_NUMBER_ID}/media"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
MB = 1024 * 1024


def with_file(header_format: str = "IMAGE", content: bytes = JPEG, name: str = "carta.jpg", **template) -> dict:
    sample = {"name": name, "content_base64": base64.b64encode(content).decode()}
    return {
        "hub": "bar-manolo",
        "to": "+34600111222",
        "type": "template",
        "template": {
            "name": "oferta_otono",
            "language": "es",
            "variables": ["Ana"],
            "header_format": header_format,
            "header_sample": sample,
            **template,
        },
    }


def uploading(media_id: str = "media-1"):
    return respx.post(MEDIA).mock(return_value=httpx.Response(200, json={"id": media_id}))


@pytest.mark.django_db
class TestAHeaderWithAFile:
    @respx.mock
    def test_a_photo_header_is_uploaded_to_the_number_and_sent_by_its_id(self, client, number, business):
        upload = uploading()
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        response = send(client, with_file())

        assert response.status_code == 200
        sent = upload.calls.last.request
        assert sent.headers["Authorization"] == "Bearer EAAG-token"
        body = sent.content
        assert b'name="messaging_product"\r\n\r\nwhatsapp' in body
        assert b'name="type"\r\n\r\nimage/jpeg' in body
        assert b'filename="carta.jpg"' in body and JPEG in body
        assert json.loads(meta.calls.last.request.content)["template"]["components"] == [
            {"type": "header", "parameters": [{"type": "image", "image": {"id": "media-1"}}]},
            {"type": "body", "parameters": [{"type": "text", "text": "Ana"}]},
        ]
        assert used(business) == 1

    @respx.mock
    def test_a_document_goes_with_its_name(self, client, number):
        uploading("media-2")
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        assert send(client, with_file("DOCUMENT", PDF, "C:\\cartas/../carta.pdf", variables=[])).status_code == 200

        assert json.loads(meta.calls.last.request.content)["template"]["components"] == [
            {"type": "header", "parameters": [{"type": "document", "document": {"id": "media-2", "filename": "carta.pdf"}}]},
        ]

    @respx.mock
    def test_a_body_with_a_file_over_the_other_doors_256_kb_is_read(self, client, number):
        uploading()
        respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        assert send(client, with_file(content=JPEG + b"\x00" * (400 * 1024))).status_code == 200

    @pytest.mark.parametrize(
        ("payload", "said"),
        [
            (with_file("IMAGE", PDF), "JPEG or PNG"),
            (with_file("VIDEO", JPEG), "MP4"),
            (with_file("IMAGE", JPEG + b"\x00" * (5 * MB)), "5 MB"),
            (with_file("IMAGE", header_sample=None), "needs its file"),
            (with_file("LOCATION"), "a text, a photo, a video or a document"),
        ],
    )
    @respx.mock
    def test_a_file_meta_would_refuse_never_reaches_meta(self, client, number, business, payload, said):
        upload = respx.post(MEDIA)
        meta = respx.post(SEND)

        response = send(client, payload)

        assert (response.status_code, error_code(response)) == (409, "whatsapp.template_invalid")
        assert said in response.json()["error"]["message"]
        assert not upload.called and not meta.called
        assert used(business) == 0 and not Send.objects.exists()

    @respx.mock
    def test_the_same_key_never_uploads_nor_sends_twice(self, client, number, business):
        upload = uploading()
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        first = send(client, with_file())
        again = send(client, with_file())

        assert first.json() == again.json()
        assert (upload.call_count, meta.call_count, used(business)) == (1, 1, 1)


@pytest.mark.django_db
class TestMetaAndTheUpload:
    @pytest.mark.parametrize(
        ("meta_code", "code"), [(100, "whatsapp.meta_rejected"), (190, "whatsapp.reconnect_needed")]
    )
    @respx.mock
    def test_metas_refusal_of_the_upload_is_its_409_and_nothing_left(self, client, number, business, meta_code, code):
        respx.post(MEDIA).mock(
            return_value=httpx.Response(400, json={"error": {"code": meta_code, "message": "(#100) Invalid parameter"}})
        )
        meta = respx.post(SEND)

        response = send(client, with_file())

        assert (response.status_code, error_code(response)) == (409, code)
        assert "Invalid parameter" in response.json()["error"]["message"], "Meta's own reason, never ERPlora's"
        assert not meta.called and used(business) == 0 and not Send.objects.exists()
        # Meta's 190 (the permission expired or withdrawn) marks the number, as a refused send does.
        assert PhoneNumber.objects.get(pk=number.pk).needs_reconnect is (meta_code == 190)

    @pytest.mark.parametrize(
        "failure",
        [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.Response(200, json={})],
        ids=["no_connection", "no_answer", "no_id"],
    )
    @respx.mock
    def test_meta_not_answering_the_upload_left_nothing_and_the_same_key_sends_once(
        self, client, number, business, failure
    ):
        """Even an upload that may have reached Meta sent no message: the key is free, and the retry sends once."""
        upload = respx.post(MEDIA)
        if isinstance(failure, httpx.Response):
            upload.mock(return_value=failure)
        else:
            upload.mock(side_effect=failure)
        meta = respx.post(SEND).mock(return_value=httpx.Response(200, json=ACCEPTED))

        response = send(client, with_file())

        assert (response.status_code, error_code(response)) == (503, "whatsapp.meta_unreachable")
        assert "Meta" in response.json()["error"]["message"] and "ERPlora" not in response.json()["error"]["message"]
        assert not meta.called and used(business) == 0
        upload.mock(side_effect=None, return_value=httpx.Response(200, json={"id": "media-9"}))
        assert send(client, with_file()).status_code == 200
        assert (meta.call_count, used(business)) == (1, 1)
