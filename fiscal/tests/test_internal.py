"""``POST /internal/hubs/{id}/representation`` and ``GET /internal/representation/model``: the Hub sends a
business's signed authorisation, and fetches the blank model the customer signs (plan 2026-10-15, «Contrato»).

Server to server, signed as the other ``/internal`` calls (``accounts.signing``: v1 over the body, v2 over the
method, the path and the body), so no CSRF token. The upload runs ``fiscal.representation.submit`` as the
platform, in the owner's channel; every refusal answers the single envelope ``{"error": {"code", "message",
"fields"?}}`` (PLAN §14.1) and nothing is ever cached.
"""

import base64
import io
import json
import time
import uuid
from urllib.parse import urlencode

import pytest
from django.conf import settings
from django.test import RequestFactory
from live.models import OutboxEvent

from accounts.signing import sign, signed_headers
from fiscal import internal
from fiscal.documents import MAX_DOCUMENT_BYTES
from fiscal.models import RepresentationGrant
from fiscal.tests.conftest import PDF, pdf_b64, submission
from hubs.models import Hub
from hubs.tests.conftest import SECRET

pytestmark = pytest.mark.django_db

MODEL_PATH = "/internal/representation/model"


@pytest.fixture(autouse=True)
def _secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET


def path_of(hub_id) -> str:
    return f"/internal/hubs/{hub_id}/representation"


def post(client, hub_id, payload=None, *, secret=SECRET, timestamp=None, raw=None, headers=None):
    body = raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode())
    timestamp = int(time.time()) if timestamp is None else timestamp
    return client.post(
        path_of(hub_id),
        body,
        content_type="application/json",
        headers={
            "X-Erplora-Timestamp": str(timestamp),
            "X-Erplora-Signature": sign(body, timestamp, secret),
            **(headers or {}),
        },
    )


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


# --- The upload -----------------------------------------------------------------------------------------


def test_a_signed_upload_waits_for_the_staff(client, business):
    response = post(client, business.id, submission())

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == ("submitted", 1)
    grant = RepresentationGrant.objects.get(hub=business)
    assert (grant.status, grant.version, grant.taxpayer_tax_id) == ("submitted", 1, "12345678Z")
    assert body["submitted_at"].startswith(grant.submitted_at.date().isoformat())
    assert "no-store" in response["Cache-Control"]


def test_a_newer_upload_takes_the_next_version(client, business):
    post(client, business.id, submission())

    response = post(client, business.id, submission())

    assert (response.status_code, response.json()["version"]) == (201, 2)
    assert list(
        RepresentationGrant.objects.filter(hub=business).order_by("version").values_list("status", flat=True)
    ) == ["returned", "submitted"]


def test_its_event_reaches_the_owners_channel_as_the_platform(client, business, owner):
    post(client, business.id, submission())

    event = OutboxEvent.objects.get(name="fiscal.representation.submitted")
    assert (event.scope_kind, event.scope_key, event.actor) == ("user", str(owner.pk), "system")
    assert "documents" not in json.dumps(event.payload)


def test_the_body_may_name_the_business_of_the_path(client, business):
    response = post(client, business.id, submission(hub_id=str(business.id)))

    assert response.status_code == 201


def test_a_body_naming_another_business_is_refused(client, business):
    """v1 signs the body only: a body replayed on another business's route must not file there."""
    response = post(client, business.id, submission(hub_id=str(uuid.uuid7())))

    assert error_of(response) == (400, "invalid_request")
    assert not RepresentationGrant.objects.exists()


@pytest.mark.parametrize("raw", [b"{not json", b"[]", b"", b"\"text\""], ids=["broken", "list", "empty", "string"])
def test_a_body_that_is_not_a_json_object_is_400(client, business, raw):
    response = post(client, business.id, raw=raw)

    assert error_of(response) == (400, "invalid_request")


def test_a_broken_rule_answers_its_fiscal_code_and_every_field(client, business):
    response = post(client, business.id, submission(documents={"id_copy": pdf_b64()}, signer_name=""))

    assert error_of(response) == (422, "fiscal.signer_required")
    assert set(response.json()["error"]["fields"]) == {"signer_name", "documents.signed_model"}
    assert not RepresentationGrant.objects.exists()


@pytest.mark.parametrize("field", ["signer_tax_id", "taxpayer_tax_id"])
def test_a_tax_id_longer_than_its_column_is_a_422_not_a_500(client, business, field):
    response = post(client, business.id, submission(**{field: "1" * 17 + "Z"}))

    assert error_of(response) == (422, "invalid_payload")
    assert field in response.json()["error"]["fields"]
    assert not RepresentationGrant.objects.exists()


def test_a_signer_tax_id_with_nothing_left_once_normalised_is_required(client, business):
    response = post(client, business.id, submission(signer_tax_id="--"))

    assert error_of(response) == (422, "fiscal.signer_required")
    assert "signer_tax_id" in response.json()["error"]["fields"]
    assert not RepresentationGrant.objects.exists()


def test_an_unknown_field_is_an_invalid_payload_naming_it(client, business):
    response = post(client, business.id, submission(signer_email="x@example.com"))

    assert error_of(response) == (422, "invalid_payload")
    assert "signer_email" in response.json()["error"]["fields"]


def test_documents_that_are_not_an_object_are_an_invalid_payload(client, business):
    response = post(client, business.id, submission(documents="all of them"))

    assert error_of(response) == (422, "invalid_payload")
    assert "documents" in response.json()["error"]["fields"]


def test_the_messages_speak_the_language_the_hub_asks(client, business):
    response = post(client, business.id, submission(signer_name=""), headers={"Accept-Language": "es"})

    assert response.json()["error"]["fields"]["signer_name"] == (
        "Indica quién firma la autorización: su nombre y su NIF."
    )


def full_pdf_b64(marker: str) -> str:
    """A PDF of exactly ``MAX_DOCUMENT_BYTES``, in base64."""
    head = PDF + marker.encode()
    return base64.b64encode(head + b"x" * (MAX_DOCUMENT_BYTES - len(head))).decode()


def test_four_documents_of_5_mb_are_heard(client, business):
    """Beyond Django's 2.5 MB (``DATA_UPLOAD_MAX_MEMORY_SIZE``), within this view's own ceiling."""
    documents = {name: full_pdf_b64(name) for name in RepresentationGrant.DOCUMENTS}
    body = json.dumps(submission(documents=documents)).encode()
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE < len(body) <= internal.MAX_BODY_BYTES

    response = post(client, business.id, raw=body)

    assert response.status_code == 201
    grant = RepresentationGrant.objects.get(hub=business)
    assert grant.signature_sample is not None and grant.representation_proof is not None


@pytest.fixture
def keep_the_test_connection():
    """Django's real handler closes old connections when a request starts and ends, which would drop the test's own
    transaction; its test client unhooks them the same way."""
    from django.core.signals import request_finished, request_started
    from django.db import close_old_connections

    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


@pytest.mark.usefixtures("keep_the_test_connection")
def test_the_documents_never_touch_the_disk_on_their_way_in(business):
    """FISCAL-F03 · Behind Daphne, Django's handler moves a body past ``FILE_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB) to a
    temporary file on disk before this view runs, the customer's identity documents in it; ``config.asgi`` keeps this
    door's body in memory, up to ``MAX_BODY_BYTES``, and the documents reach the database encrypted and nowhere else."""
    from config.tests.asgi_bodies import asgi_post, files_written

    big = base64.b64encode(PDF + b"x" * 2_400_000).decode()
    body = json.dumps(submission(documents={"signed_model": big, "id_copy": pdf_b64("id")})).encode()
    assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE < len(body) <= internal.MAX_BODY_BYTES

    with files_written() as written:
        status, answer, unread = asgi_post(path_of(business.id), body, secret=SECRET, chunks=5)

    assert (status, answer["status"], unread) == (201, "submitted", 0)
    assert written == []


def test_a_body_beyond_the_ceiling_is_413_before_anything_else(client, business):
    """Not even the signature is checked: an unsigned 33 MB body is refused by its size."""
    body = b"{" + b" " * (internal.MAX_BODY_BYTES + 1024 * 1024) + b"}"

    response = client.post(path_of(business.id), body, content_type="application/json")

    assert error_of(response) == (413, "fiscal.body_too_large")
    assert not RepresentationGrant.objects.exists()


@pytest.mark.parametrize("length", ["lots", "-1"], ids=["not a number", "negative"])
def test_a_body_with_a_broken_length_is_a_bad_request(business, length):
    request = RequestFactory().post(
        path_of(business.id), json.dumps(submission()), content_type="application/json"
    )
    request.META["CONTENT_LENGTH"] = length

    response = internal.representation(request, business.id)

    assert response.status_code == 400
    assert json.loads(response.content)["error"]["code"] == "invalid_request"
    assert not RepresentationGrant.objects.exists()


@pytest.mark.parametrize("length", ["2", None], ids=["understated", "absent"])
def test_a_body_longer_than_the_ceiling_is_413_whatever_its_length_says(business, length):
    """Under ASGI the length may be understated, or absent with a chunked body (HTTP reads a request without
    one as empty, the test client's empty POST among them): what is read is what counts."""
    # Headers that may be signed (a fresh timestamp and a signature), or it is refused before it is read.
    request = RequestFactory().post(
        path_of(business.id), b"{}", content_type="application/json", headers=plausible_headers()
    )
    request._stream = io.BytesIO(b" " * (internal.MAX_BODY_BYTES + 1))
    if length is None:
        del request.META["CONTENT_LENGTH"]
    else:
        request.META["CONTENT_LENGTH"] = length

    response = internal.representation(request, business.id)

    assert response.status_code == 413
    assert json.loads(response.content)["error"]["code"] == "fiscal.body_too_large"


def plausible_headers(**changes) -> dict[str, str]:
    """A fresh timestamp and a signature that only the body could prove wrong."""
    return {"X-Erplora-Timestamp": str(int(time.time())), "X-Erplora-Signature": "0" * 64, **changes}


class UnreadableBody(io.RawIOBase):
    """A body the view must never read: reading it fails the test."""

    def readable(self):
        return True

    def readinto(self, buffer):
        raise AssertionError("the body was read")


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Erplora-Timestamp": str(int(time.time()))},
        {"X-Erplora-Signature": "0" * 64},
        {"X-Erplora-Signature-V2": "0" * 64},
        plausible_headers(**{"X-Erplora-Timestamp": str(int(time.time()) - 3600)}),
        plausible_headers(**{"X-Erplora-Timestamp": str(int(time.time()) + 3600)}),
        plausible_headers(**{"X-Erplora-Timestamp": "soon"}),
        plausible_headers(**{"X-Erplora-Timestamp": "9" * 5000}),
    ],
    ids=[
        "no headers",
        "no signature",
        "no timestamp",
        "v2 without a timestamp",
        "stale",
        "future",
        "not a time",
        "too many digits",
    ],
)
def test_an_unsigned_or_stale_upload_is_401_before_its_body_is_read(business, headers):
    """Up to 32 MB are read only for a call that may be signed: a missing signature or a timestamp out of the
    window is refused from its headers."""
    request = RequestFactory().post(path_of(business.id), b"{}", content_type="application/json", headers=headers)
    request._stream = UnreadableBody()
    request.META["CONTENT_LENGTH"] = str(30 * 1024 * 1024)

    response = internal.representation(request, business.id)

    assert response.status_code == 401
    assert json.loads(response.content)["error"]["code"] == "unauthorized"
    assert not RepresentationGrant.objects.exists()


def test_a_call_that_may_be_signed_is_read_and_then_verified(business):
    """The early refusal looks at the headers only: a forged signature with a fresh timestamp is read and
    refused by the signature itself."""
    request = RequestFactory().post(
        path_of(business.id), json.dumps(submission()), content_type="application/json", headers=plausible_headers()
    )

    response = internal.representation(request, business.id)

    assert response.status_code == 401
    assert not RepresentationGrant.objects.exists()


def test_the_rest_of_the_internal_api_keeps_django_s_ceiling(client, business):
    """Only this view reads beyond 2.5 MB: a 3 MB body to ``/internal/hubs/{id}/ready`` is still refused, as
    Django refuses a body beyond ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (``RequestDataTooBig``, a 400)."""
    body = json.dumps({"id": str(business.id), "padding": "x" * (3 * 1024 * 1024)}).encode()
    timestamp = int(time.time())

    response = client.post(
        f"/internal/hubs/{business.id}/ready",
        body,
        content_type="application/json",
        headers={"X-Erplora-Timestamp": str(timestamp), "X-Erplora-Signature": sign(body, timestamp, SECRET)},
    )

    assert response.status_code == 400
    assert Hub.objects.get(pk=business.pk).status == business.status


def test_an_unknown_business_is_404(client, plans):
    response = post(client, uuid.uuid7(), submission())

    assert error_of(response) == (404, "not_found")


def test_a_deleted_business_is_404(client, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    response = post(client, business.id, submission())

    assert error_of(response) == (404, "not_found")
    assert not RepresentationGrant.objects.exists()


@pytest.mark.parametrize("kind", ["unsigned", "other secret", "stale"])
def test_without_a_valid_signature_nothing_is_filed(client, business, kind):
    if kind == "unsigned":
        response = client.post(
            path_of(business.id), json.dumps(submission()), content_type="application/json"
        )
    elif kind == "other secret":
        response = post(client, business.id, submission(), secret="not-the-secret")
    else:
        response = post(client, business.id, submission(), timestamp=int(time.time()) - 3600)

    assert error_of(response) == (401, "unauthorized")
    assert not RepresentationGrant.objects.exists()


def test_a_v2_signature_for_this_route_is_heard(client, business):
    body = json.dumps(submission()).encode()
    path = path_of(business.id)

    response = client.post(
        path,
        body,
        content_type="application/json",
        headers=signed_headers("POST", path, body, int(time.time()), SECRET),
    )

    assert response.status_code == 201


def test_a_v2_signature_for_another_business_is_unauthorized(client, business, make_user):
    body = json.dumps(submission()).encode()
    headers = signed_headers("POST", path_of(uuid.uuid7()), body, int(time.time()), SECRET)

    response = client.post(path_of(business.id), body, content_type="application/json", headers=headers)

    assert error_of(response) == (401, "unauthorized")


def test_only_post(client, business):
    response = client.get(path_of(business.id))

    assert error_of(response) == (405, "method_not_allowed")
    assert response["Allow"] == "POST"


# --- The blank model ------------------------------------------------------------------------------------


def get_model(client, *, secret=SECRET, timestamp=None, query=None, v2=True):
    """The model as the Hub asks for it: v1 and v2 (``signed_headers``) over the path with ``query``; ``v2=False``
    sends v1 alone, the body-only signature that never covers a query."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    path = f"{MODEL_PATH}?{urlencode(query)}" if query else MODEL_PATH
    headers = (
        signed_headers("GET", path, b"", timestamp, secret)
        if v2
        else {"X-Erplora-Timestamp": str(timestamp), "X-Erplora-Signature": sign(b"", timestamp, secret)}
    )
    return client.get(path, headers=headers)


def model_pages(response):
    from pypdf import PdfReader

    content = b"".join(response.streaming_content) if response.streaming else response.content
    assert content.startswith(b"%PDF")
    return PdfReader(io.BytesIO(content)).pages


def test_the_model_is_the_official_page_filled_in_with_erplora_and_the_rgpd_page(client, synthetic_company):
    """FISCAL-F06 (PLAN-SAAS §4: «el PDF oficial pre-rellenado (Anexo I, p. 11, + hoja RGPD)»)."""
    response = get_model(client)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == (
        'attachment; filename="anexo-i-otorgamiento-representacion-erplora.pdf"'
    )
    assert "no-store" in response["Cache-Control"]
    model, privacy = model_pages(response)
    assert "OTORGA SU REPRESENTACIÓN a" in model.extract_text()
    assert "ACME FISCAL SL" in model.extract_text()
    assert "Responsable: ACME FISCAL SL" in " ".join(privacy.extract_text().split())


def test_the_business_the_hub_names_fills_its_block(client, synthetic_company):
    response = get_model(
        client,
        query={
            "taxpayer_tax_id": "b12345674",
            "taxpayer_name": "Bar Prueba SL",
            "municipality": "Leganés",
            "street": "Avenida Sur",
            "number": "12",
        },
    )

    assert response.status_code == 200
    text = model_pages(response)[0].extract_text()
    assert all(value in text for value in ("Bar Prueba SL", "B12345674", "Leganés", "Avenida Sur"))


def test_a_v2_signature_covers_the_business_the_hub_names(client, synthetic_company):
    """v2 signs the method and the full path, query included: a query changed on the way is a 401."""
    path = f"{MODEL_PATH}?taxpayer_tax_id=B12345674"
    headers = signed_headers("GET", path, b"", int(time.time()), SECRET)

    assert client.get(path, headers=headers).status_code == 200
    assert error_of(client.get(f"{MODEL_PATH}?taxpayer_tax_id=12345678Z", headers=headers)) == (401, "unauthorized")


def test_a_query_signed_with_v1_alone_is_refused_saying_v2_is_needed(client, synthetic_company):
    """v1 signs the body only: with it, anybody holding one captured signature could ask, within its window, for
    the model filled in with another business's details. The Hub signs v2 too; the answer says so."""
    response = get_model(client, query={"taxpayer_tax_id": "B12345674"}, v2=False)

    assert error_of(response) == (401, "signature_v2_required")
    assert "X-Erplora-Signature-V2" in response.json()["error"]["message"]
    assert "no-store" in response["Cache-Control"]


def test_the_model_without_a_query_is_still_heard_with_v1_alone(client, synthetic_company):
    assert get_model(client, v2=False).status_code == 200


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"taxpayer_tax_id": "not-a-nif"}, "taxpayer_tax_id"),
        ({"taxpayer_name": "名前"}, "taxpayer_name"),
        ({"street": "x" * 201}, "street"),
        ({"surprise": "1"}, "surprise"),
    ],
)
def test_what_the_model_cannot_carry_is_refused_naming_the_field(client, query, field):
    response = get_model(client, query=query)

    assert error_of(response) == (422, "invalid_payload")
    assert field in response.json()["error"]["fields"]


def test_the_stamp_goes_on_the_model_when_there_is_one(client, synthetic_company, stamp_keeper):
    from fiscal import services
    from fiscal.schemas import StampUploadIn
    from fiscal.tests.conftest import staff_ctx, stamp_png

    services.stamp_upload(staff_ctx(stamp_keeper), StampUploadIn(png_base64=base64.b64encode(stamp_png()).decode()))

    assert len(model_pages(get_model(client))[0].images) == 1


def test_without_a_stamp_the_model_goes_without_it_and_the_log_says_so(client, synthetic_company, caplog):
    with caplog.at_level("WARNING", logger="fiscal.internal"):
        response = get_model(client)

    assert len(model_pages(response)[0].images) == 0
    assert "fiscal.model.without_stamp" in caplog.text


def test_a_v2_signed_request_for_the_model_is_heard(client):
    response = client.get(MODEL_PATH, headers=signed_headers("GET", MODEL_PATH, b"", int(time.time()), SECRET))

    assert response.status_code == 200


@pytest.mark.parametrize("kind", ["unsigned", "other secret", "stale"])
def test_the_model_needs_a_valid_signature(client, kind):
    if kind == "unsigned":
        response = client.get(MODEL_PATH)
    elif kind == "other secret":
        response = get_model(client, secret="not-the-secret")
    else:
        response = get_model(client, timestamp=int(time.time()) - 3600)

    assert error_of(response) == (401, "unauthorized")
    assert "no-store" in response["Cache-Control"]


def test_the_model_is_only_read(client):
    response = client.post(MODEL_PATH, b"", content_type="application/json")

    assert error_of(response) == (405, "method_not_allowed")
    assert response["Allow"] == "GET"
