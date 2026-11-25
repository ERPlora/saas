"""``GET /whatsapp/media/<id>``: a customer's photo, voice note, video or document, opened from the
Hub's inbox (door 1 carries this address in ``media.url``).

The browser opens it with the person's erplora.com session: only an accepted member of the business the message is
for gets it, streamed from Meta as it arrives and never kept here. Meta is replaced at the HTTP border only
(``respx``). Meta's link is fetched only from its hosts and over https, never redirected; everything is decided
before the first byte; nothing is cached; the id is
checked against the business's own messages, and what is not a picture, a sound or a video is never shown on
erplora.com's origin (downloaded, sandboxed).
"""

import logging
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
import respx
from django.utils import timezone

from whatsapp import media
from whatsapp.models import Delivery, PhoneNumber
from whatsapp.tests.conftest import GRAPH

pytestmark = pytest.mark.django_db

MEDIA_ID = "1479537139650973"
LOOKASIDE = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1479537139650973"
JPEG = b"\xff\xd8\xff\xe0jpeg-bytes"


@pytest.fixture
def number(whatsapp_on, business):
    return PhoneNumber.objects.create(
        hub=business, phone_number_id="106540352242922", display_phone="+34 910 00 00 00", waba_id="W",
        access_token="EAAG-token",
    )


def attachment(hub, *, media_id=MEDIA_ID, mime="image/jpeg", filename=""):
    return Delivery.objects.create(
        hub=hub, kind="message", wa_message_id=f"wamid.{media_id}", media_id=media_id,
        body={"type": "image", "media": {"mime_type": mime, "filename": filename, "caption": ""}},
        delivered_at=timezone.now(),
    )


def meta_has_it(mime="image/jpeg", content=JPEG, url=LOOKASIDE, **said):
    info = respx.get(f"{GRAPH}/{MEDIA_ID}").mock(
        return_value=httpx.Response(
            200,
            json={"url": url, "mime_type": mime, "sha256": "abc", "file_size": len(content), "id": MEDIA_ID,
                  "messaging_product": "whatsapp", **said},
        )
    )
    download = respx.get(url).mock(return_value=httpx.Response(200, content=content, headers={"Content-Type": mime}))
    return info, download


def open_media(client, row_or_id):
    ref = row_or_id.id if isinstance(row_or_id, Delivery) else row_or_id
    return client.get(f"/whatsapp/media/{ref}", HTTP_HOST="localhost")


def body(response) -> bytes:
    return b"".join(response.streaming_content)


def error_code(response) -> str:
    return response.json()["error"]["code"]


@respx.mock
def test_a_member_opens_the_photo_streamed_from_meta_and_never_cached(client, number, business, owner):
    info, download = meta_has_it()
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert response.status_code == 200
    assert body(response) == JPEG
    assert response["Content-Type"] == "image/jpeg"
    assert response["Content-Length"] == str(len(JPEG))
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Disposition"].startswith("inline")
    assert info.calls.last.request.headers["Authorization"] == "Bearer EAAG-token"
    assert download.calls.last.request.headers["Authorization"] == "Bearer EAAG-token"


def test_without_a_session_it_is_401_and_meta_never_called(client, number, business):
    row = attachment(business)

    with respx.mock(assert_all_called=False) as router:
        response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (401, "unauthorized")
    assert not router.calls


def test_a_person_of_another_business_gets_404_and_meta_never_called(client, number, business, other_business):
    row = attachment(business)
    client.force_login(other_business.members.get().user)

    with respx.mock(assert_all_called=False) as router:
        response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (404, "whatsapp.media_not_found")
    assert "no-store" in response["Cache-Control"]
    assert not router.calls


def test_an_invitation_not_answered_yet_gets_404(client, number, business, make_user):
    from hubs.tests.conftest import add_member

    invitee = make_user("invitee@example.com")
    add_member(business, invitee, "hub_employee", accepted=False)
    row = attachment(business)
    client.force_login(invitee)

    with respx.mock(assert_all_called=False):
        response = open_media(client, row)

    assert response.status_code == 404


def test_an_employee_of_the_business_opens_it(client, number, business, make_user):
    from hubs.tests.conftest import add_member

    employee = make_user("employee@example.com")
    add_member(business, employee, "hub_employee")
    row = attachment(business)
    client.force_login(employee)

    with respx.mock:
        meta_has_it()
        response = open_media(client, row)

    assert response.status_code == 200 and body(response) == JPEG


@pytest.mark.parametrize("ref", ["0199e7c2-0000-7000-8000-000000000999", "not-a-uuid"])
def test_an_unknown_attachment_is_404(client, number, business, owner, ref):
    client.force_login(owner)

    response = open_media(client, ref)

    assert (response.status_code, error_code(response)) == (404, "whatsapp.media_not_found")


def test_a_message_without_an_attachment_is_404(client, number, business, owner):
    row = attachment(business, media_id="")
    client.force_login(owner)

    with respx.mock(assert_all_called=False) as router:
        response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (404, "whatsapp.media_not_found")
    assert not router.calls


@respx.mock
def test_an_attachment_meta_no_longer_has_is_404(client, number, business, owner, caplog):
    caplog.set_level(logging.INFO, "whatsapp.media")
    respx.get(f"{GRAPH}/{MEDIA_ID}").mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "Unsupported get request.", "type": "GraphMethodException", "code": 100}}
        )
    )
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (404, "whatsapp.media_not_found")
    assert "whatsapp.media.refused meta_status=400 meta_code=100" in caplog.text


@respx.mock
def test_a_link_that_is_not_metas_is_never_followed(client, number, business, owner, caplog):
    _, download = meta_has_it(url="https://evil.example.com/a.jpg")
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")
    assert not download.called
    assert "whatsapp.media.unavailable error=The attachment's link is not Meta's." in caplog.text


@respx.mock
def test_meta_giving_no_link_is_502(client, number, business, owner):
    respx.get(f"{GRAPH}/{MEDIA_ID}").mock(return_value=httpx.Response(200, json={"id": MEDIA_ID}))
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")


@respx.mock
def test_meta_failing_the_download_is_said_before_the_first_byte(client, number, business, owner):
    _, download = meta_has_it()
    download.mock(return_value=httpx.Response(500))
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")


@respx.mock
def test_meta_unreachable_is_502(client, number, business, owner):
    respx.get(f"{GRAPH}/{MEDIA_ID}").mock(side_effect=httpx.ConnectError("down"))
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")


@respx.mock
def test_unreadable_trusted_certificates_are_502_before_meta(client, number, business, owner, unreadable_ca):
    """The server cannot load its trusted
    certificates: the attachment says it cannot be handed over now, never a 500, and Meta is not asked."""
    info, download = meta_has_it()
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")
    assert not info.called and not download.called


def test_without_a_connected_number_it_is_409(client, whatsapp_on, business, owner):
    row = attachment(business)
    client.force_login(owner)

    with respx.mock(assert_all_called=False) as router:
        response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (409, "whatsapp.not_connected")
    assert not router.calls


@respx.mock
def test_an_expired_permission_is_409_and_marks_the_number_to_reconnect(client, number, business, owner):
    respx.get(f"{GRAPH}/{MEDIA_ID}").mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Error validating access token", "type": "OAuthException", "code": 190}}
        )
    )
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
    number.refresh_from_db()
    assert number.needs_reconnect is True


@respx.mock
def test_an_expired_permission_at_the_download_is_409_and_marks_the_number_to_reconnect(client, number, business, owner):
    _, download = meta_has_it()
    download.mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Error validating access token", "type": "OAuthException", "code": 190}}
        )
    )
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (409, "whatsapp.reconnect_needed")
    number.refresh_from_db()
    assert number.needs_reconnect is True


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(404, json={"error": {"message": "Unsupported get request.", "type": "GraphMethodException", "code": 100}}),
        httpx.Response(403, content=b"Forbidden"),
    ],
)
@respx.mock
def test_any_other_refusal_of_the_download_is_502_and_marks_nothing(client, number, business, owner, caplog, answer):
    _, download = meta_has_it()
    download.mock(return_value=answer)
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert (response.status_code, error_code(response)) == (502, "whatsapp.media_unavailable")
    number.refresh_from_db()
    assert number.needs_reconnect is False
    assert f"whatsapp.media.download_refused meta_status={answer.status_code} meta_code=" in caplog.text


@pytest.mark.parametrize(
    "mime, served",
    [
        ("application/pdf", "application/pdf"),
        ("text/html", "application/octet-stream"),
        ("image/svg+xml", "application/octet-stream"),
        ("application/x-msdownload", "application/octet-stream"),
    ],
)
@respx.mock
def test_what_is_not_a_picture_a_sound_or_a_video_is_downloaded_never_shown(
    client, number, business, owner, mime, served
):
    meta_has_it(mime=mime, content=b"<html><script>alert(1)</script></html>")
    row = attachment(business, mime=mime, filename="factura.pdf")
    client.force_login(owner)

    response = open_media(client, row)

    assert response.status_code == 200
    assert response["Content-Type"] == served
    assert response["Content-Disposition"] == 'attachment; filename="factura.pdf"'
    assert response["Content-Security-Policy"] == "default-src 'none'; sandbox"
    body(response)


@respx.mock
def test_a_file_without_a_name_is_downloaded_under_a_plain_one(client, number, business, owner):
    meta_has_it(mime="application/pdf")
    row = attachment(business, mime="application/pdf")
    client.force_login(owner)

    response = open_media(client, row)

    assert response["Content-Disposition"] == 'attachment; filename="attachment"'
    body(response)


@pytest.mark.parametrize(("said", "served"), [("image/png", "image/png"), ("", "image/jpeg"), (None, "image/jpeg")])
@respx.mock
def test_metas_type_now_wins_over_the_one_the_message_came_with(client, number, business, owner, said, served):
    meta_has_it(mime_type=said)
    row = attachment(business, mime="image/jpeg")
    client.force_login(owner)

    response = open_media(client, row)

    assert response["Content-Type"] == served
    body(response)


@pytest.mark.parametrize(("size", "length"), [(0, "0"), (12, "12"), (-1, None), ("12", None), (None, None)])
@respx.mock
def test_the_length_is_said_only_when_meta_gives_one(client, number, business, owner, size, length):
    meta_has_it(file_size=size)
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert response.headers.get("Content-Length") == length
    body(response)


@respx.mock
def test_the_download_is_closed_with_the_response_even_if_it_was_never_read(
    client, number, business, owner, monkeypatch
):
    meta_has_it()
    closed = []

    @contextmanager
    def download(url, *, token):
        yield SimpleNamespace(iter_bytes=lambda size: iter([JPEG]))
        closed.append(url)

    monkeypatch.setattr(media.meta, "download", download)
    row = attachment(business)
    client.force_login(owner)

    response = open_media(client, row)

    assert closed == []
    response.close()
    assert closed == [LOOKASIDE]


@pytest.mark.parametrize("mime", ["audio/ogg", "video/mp4", "image/webp"])
@respx.mock
def test_a_sound_a_video_or_a_sticker_plays_inline(client, number, business, owner, mime):
    meta_has_it(mime=mime)
    row = attachment(business, mime=mime)
    client.force_login(owner)

    response = open_media(client, row)

    assert response["Content-Type"] == mime and response["Content-Disposition"].startswith("inline")
    body(response)


def test_only_get_is_allowed(client, number, business, owner):
    row = attachment(business)
    client.force_login(owner)

    response = client.post(f"/whatsapp/media/{row.id}", HTTP_HOST="localhost")

    assert response.status_code == 405


def test_an_attachment_is_never_indexed(client, number, business):
    from public.crawlers import NOINDEX_HEADER

    row = attachment(business)

    response = open_media(client, row)

    assert response["X-Robots-Tag"] == NOINDEX_HEADER


def test_robots_txt_keeps_crawlers_out_of_the_attachments():
    from public.crawlers import private_prefixes

    assert "/whatsapp/" in private_prefixes()
