"""The account's photo: ``accounts.photos`` (what an upload may be, and what is kept of it) and the operations
``accounts.photo.upload`` and ``accounts.photo.remove`` (plan 2026-10-13, L3-A; Account → Profile, «Change photo»).

Ported from ERPlora/saas ``apps/dashboard/profile`` (``TestAvatarViews`` of ``test_views.py``), with what the old
upload did not check: only JPEG, PNG or WebP, recognised by their bytes (never by the name or the type the
browser claims); at most ``MAX_PHOTO_BYTES`` and ``MAX_SIDE`` pixels; no animation; and nothing of what a phone
writes inside a photo (the place it was taken, the camera, comments) is kept, except a JPEG's orientation, so it
does not turn sideways. Kept in the database (no media storage in the SaaS) and shown as a data URL.
"""

import base64
import struct

import pytest
from live.live_registry import live_registry

from accounts import events, photos, services
from accounts.models import ProfilePhoto
from accounts.schemas import PhotoRemoveIn, PhotoUploadIn
from accounts.tests import images
from accounts.tests.conftest import HOST, api_get, api_post, ctx_for

pytestmark = pytest.mark.django_db

UPLOAD = "/api/accounts/photo"
REMOVE = "/api/accounts/photo/remove"


def _segments(data: bytes) -> list[int]:
    """The markers of a JPEG up to its scan."""
    markers, i = [], 2
    while i < len(data):
        marker = data[i + 1]
        markers.append(marker)
        if marker == 0xDA:
            return markers
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return markers


def _png_chunks(data: bytes) -> list[bytes]:
    kinds, i = [], 8
    while i < len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        kinds.append(data[i + 4 : i + 8])
        i += 12 + length
    return kinds


def _webp_chunks(data: bytes) -> list[bytes]:
    kinds, i = [], 12
    while i < len(data):
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        kinds.append(data[i : i + 4])
        i += 8 + size + (size % 2)
    return kinds


class TestWhatAPhotoMayBe:
    def test_a_png_is_kept_as_it_is(self):
        data = images.png()

        assert photos.clean_photo(data) == (data, "image/png")

    def test_a_jpeg_and_a_webp_are_recognised_by_their_bytes(self):
        assert photos.clean_photo(images.jpeg())[1] == "image/jpeg"
        assert photos.clean_photo(images.webp(images.vp8l()))[1] == "image/webp"

    @pytest.mark.parametrize(
        "data",
        [
            b"GIF89a\x01\x00\x01\x00",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            b"%PDF-1.7",
            b"",
        ],
    )
    def test_anything_else_is_refused(self, data):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(data)

        assert refused.value.code == "unsupported"

    def test_too_many_bytes_is_refused_before_reading_them(self):
        data = images.png(extra=[images.png_chunk(b"tEXt", b"x" * photos.MAX_PHOTO_BYTES)])

        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(data)

        assert refused.value.code == "too_large"

    @pytest.mark.parametrize(
        "data",
        [
            images.png(width=photos.MAX_SIDE + 1, height=1),
            images.jpeg(width=1, height=photos.MAX_SIDE + 1),
            images.webp(images.vp8l(width=photos.MAX_SIDE + 1, height=1)),
            images.webp(images.vp8x(photos.MAX_SIDE + 1, 1), images.vp8l()),
        ],
    )
    def test_too_many_pixels_are_refused(self, data):
        """A small file can unfold into a huge picture in every browser that paints the avatar."""
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(data)

        assert refused.value.code == "dimensions"

    @pytest.mark.parametrize(
        "data",
        [
            images.png(before_idat=[images.png_chunk(b"acTL", struct.pack(">II", 2, 0))]),
            images.webp(images.vp8x(3, 2, flags=0x02), images.webp_chunk(b"ANIM", b"\x00" * 6), images.vp8l()),
        ],
    )
    def test_an_animation_is_refused(self, data):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(data)

        assert refused.value.code == "animated"

    @pytest.mark.parametrize(
        "data",
        [
            images.png()[:-5],  # cut
            images.png()[:23] + b"\x09" + images.png()[24:],  # a height its CRC does not match
            images.jpeg()[:30],  # no frame, no scan
            b"\xff\xd8\xff\xe0\xff\xff",  # a segment longer than the file
            images.webp(images.webp_chunk(b"VP8L", b"\x00")),  # not a VP8L bitstream
            b"RIFF\xff\xff\xff\x00WEBP",  # a size it does not have
        ],
    )
    def test_a_broken_file_is_refused(self, data):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(data)

        assert refused.value.code == "corrupt"


class TestWhatIsKeptOfIt:
    def test_a_jpeg_loses_its_exif_xmp_iptc_and_comments(self):
        data = images.jpeg(
            segments=[
                images.jpeg_segment(0xE1, images.exif()),
                images.jpeg_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>"),
                images.jpeg_segment(0xED, b"Photoshop 3.0\x00IPTC"),
                images.jpeg_segment(0xFE, b"taken at home"),
            ]
        )

        cleaned, _ = photos.clean_photo(data)

        assert _segments(cleaned) == [0xE0, 0xDB, 0xC0, 0xDA]
        assert b"GPS" not in cleaned and b"home" not in cleaned
        assert cleaned.endswith(images.jpeg()[-9:])

    @pytest.mark.parametrize("little_endian", [False, True])
    def test_a_jpeg_keeps_only_its_orientation(self, little_endian):
        data = images.jpeg(segments=[images.jpeg_segment(0xE1, images.exif(6, little_endian=little_endian))])

        cleaned, _ = photos.clean_photo(data)

        assert _segments(cleaned) == [0xE0, 0xE1, 0xDB, 0xC0, 0xDA]
        assert b"GPS" not in cleaned
        assert photos.exif_orientation(cleaned[cleaned.index(b"Exif") + 6 :]) == 6

    def test_an_upright_jpeg_needs_no_exif(self):
        data = images.jpeg(segments=[images.jpeg_segment(0xE1, images.exif(1))])

        assert _segments(photos.clean_photo(data)[0]) == [0xE0, 0xDB, 0xC0, 0xDA]

    def test_a_jpeg_ends_at_its_end(self):
        """Whatever follows the end marker (a hidden archive, a phone's trailer of metadata) is not kept."""
        cleaned, _ = photos.clean_photo(images.jpeg() + b"PK\x03\x04 an archive with GPS 40.4N 3.7W")

        assert cleaned == images.jpeg()

    def test_a_progressive_jpeg_loses_what_hides_between_its_scans(self):
        data = images.progressive_jpeg(
            between_scans=[
                images.jpeg_segment(0xE1, images.exif(6)),
                images.jpeg_segment(0xFE, b"taken at home"),
                images.jpeg_segment(0xEC, b"Ducky"),
            ]
        )

        cleaned, _ = photos.clean_photo(data)

        assert cleaned == images.progressive_jpeg()
        assert cleaned.count(images.SCAN_DATA) == 2

    def test_a_jpeg_without_its_end_is_refused(self):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.clean_photo(images.progressive_jpeg()[:-2])

        assert refused.value.code == "corrupt"

    def test_a_jpeg_keeps_its_colour_profile(self):
        icc = images.jpeg_segment(0xE2, b"ICC_PROFILE\x00\x01\x01profile")

        assert 0xE2 in _segments(photos.clean_photo(images.jpeg(segments=[icc]))[0])

    def test_a_png_loses_its_texts_exif_and_time(self):
        data = images.png(
            extra=[
                images.png_chunk(b"tEXt", b"Comment\x00at home"),
                images.png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x/>"),
                images.png_chunk(b"eXIf", images.exif()[6:]),
                images.png_chunk(b"tIME", b"\x07\xea\x0a\x0e\x0a\x00\x00"),
                images.png_chunk(b"pHYs", b"\x00\x00\x0b\x13\x00\x00\x0b\x13\x01"),
            ]
        )

        cleaned, _ = photos.clean_photo(data)

        assert _png_chunks(cleaned) == [b"IHDR", b"pHYs", b"IDAT", b"IEND"]

    def test_a_webp_loses_its_exif_and_xmp_and_says_so_in_its_header(self):
        data = images.webp(
            images.vp8x(3, 2, flags=0x08 | 0x04 | 0x10),
            images.vp8l(),
            images.webp_chunk(b"EXIF", images.exif()[6:]),
            images.webp_chunk(b"XMP ", b"<x/>"),
        )

        cleaned, _ = photos.clean_photo(data)

        assert _webp_chunks(cleaned) == [b"VP8X", b"VP8L"]
        assert cleaned[20] == 0x10  # alpha stays; EXIF and XMP flags are gone
        assert struct.unpack("<I", cleaned[4:8])[0] == len(cleaned) - 8


class TestDecodingTheUpload:
    def test_a_data_url_or_plain_base64(self):
        data = images.png()
        encoded = base64.b64encode(data).decode()

        assert photos.decode_upload(f"data:image/png;base64,{encoded}") == data
        assert photos.decode_upload(encoded) == data

    @pytest.mark.parametrize("value", ["not base64!", "data:image/png;base64,***", "data:text/html,<b>x</b>"])
    def test_anything_else_is_corrupt(self, value):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.decode_upload(value)

        assert refused.value.code == "corrupt"

    def test_too_long_is_too_large_before_decoding(self):
        with pytest.raises(photos.PhotoRejected) as refused:
            photos.decode_upload("A" * (photos.MAX_UPLOAD_CHARACTERS + 1))

        assert refused.value.code == "too_large"


def _upload(value: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(value).decode()}"


class TestTheOperations:
    def test_uploading_keeps_the_cleaned_photo_and_the_profile_shows_it(self, ana):
        data = images.png(extra=[images.png_chunk(b"tEXt", b"Comment\x00at home")])

        result = services.photo_upload(ctx_for(ana), PhotoUploadIn(image=_upload(data)))

        photo = ProfilePhoto.objects.get(user=ana)
        assert (photo.content_type, bytes(photo.data)) == ("image/png", images.png())
        assert result.photo == photo.data_url()

    def test_a_new_photo_replaces_the_old_one(self, ana):
        services.photo_upload(ctx_for(ana), PhotoUploadIn(image=_upload(images.png())))
        services.photo_upload(ctx_for(ana), PhotoUploadIn(image=_upload(images.jpeg())))

        assert list(ProfilePhoto.objects.values_list("content_type", flat=True)) == ["image/jpeg"]

    def test_removing_leaves_the_initials(self, ana):
        services.photo_upload(ctx_for(ana), PhotoUploadIn(image=_upload(images.png())))

        result = services.photo_remove(ctx_for(ana), PhotoRemoveIn())

        assert result.photo is None
        assert not ProfilePhoto.objects.exists()

    def test_removing_without_a_photo_is_no_error(self, ana):
        assert services.photo_remove(ctx_for(ana), PhotoRemoveIn()).photo is None

    def test_both_re_run_the_live_profile(self, ana):
        from live.models import OutboxEvent

        services.photo_upload(ctx_for(ana), PhotoUploadIn(image=_upload(images.png())))
        services.photo_remove(ctx_for(ana), PhotoRemoveIn())

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == [events.PROFILE_UPDATED] * 2
        assert "accounts.profile.get" in live_registry.affected([events.PROFILE_UPDATED])


class TestOverHttp:
    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_post(client, UPLOAD, {"image": _upload(images.png())}).status_code == 401
        assert api_post(client, REMOVE).status_code == 401

    def test_upload_then_remove(self, client, ana):
        client.force_login(ana)

        assert api_post(client, UPLOAD, {"image": _upload(images.png())}).json()["photo"].startswith(
            "data:image/png;base64,"
        )
        assert api_get(client, "/api/accounts/profile").json()["photo"]
        assert api_post(client, REMOVE).json()["photo"] is None

    @pytest.mark.parametrize(
        "value, message",
        [
            (_upload(b"GIF89a"), "Upload a JPEG, PNG or WebP image."),
            (_upload(images.png(width=photos.MAX_SIDE + 1)), "The photo is too large: at most 2048 × 2048 pixels."),
            ("x" * (photos.MAX_UPLOAD_CHARACTERS + 1), "The photo is too big: at most 150 KB. Try a smaller one."),
            ("not base64!", "The image could not be read. Try another one."),
        ],
    )
    def test_a_refused_photo_is_a_422_on_the_image_and_nothing_is_kept(self, client, english, value, message):
        ana = english
        client.force_login(ana)

        response = api_post(client, UPLOAD, {"image": value})

        assert response.status_code == 422
        assert response.json()["error"]["fields"] == {"image": message}
        assert not ProfilePhoto.objects.exists()

    def test_the_refusal_speaks_spanish(self, client, ana):
        client.force_login(ana)

        response = client.post(
            UPLOAD, {"image": _upload(b"GIF89a")}, content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es"
        )

        assert response.json()["error"]["fields"] == {"image": "Sube una imagen JPEG, PNG o WebP."}

    def test_uploads_are_rate_limited_per_account(self, client, ana):
        client.force_login(ana)
        for _ in range(photos.UPLOADS_PER_HOUR):
            assert api_post(client, UPLOAD, {"image": _upload(images.png())}).status_code == 200

        response = api_post(client, UPLOAD, {"image": _upload(images.png())})

        assert (response.status_code, response.json()["error"]["code"]) == (429, "accounts.too_many_attempts")
