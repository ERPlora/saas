"""How ``accounts.photos.clean_photo`` reads each kind of file, byte by byte: what makes a JPEG, a PNG or a WebP
broken (``corrupt``), animated or too large, and what an unusual but valid one keeps.

The common cases (a phone's photo, its metadata, an animation) are in ``test_photos``; these are the structural
rules each reader keeps, one file each.
"""

import struct

import pytest

from accounts import photos
from accounts.tests import images

SOI, EOI = b"\xff\xd8", b"\xff\xd9"
JFIF = images.jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
SCAN = images.jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\xff\x00\x56"


def _frame(width=4, height=3) -> bytes:
    return images.jpeg_segment(0xC0, struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00")


def _refusal(data: bytes) -> str:
    with pytest.raises(photos.PhotoRejected) as refused:
        photos.clean_photo(data)
    return refused.value.code


def _segments(data: bytes) -> list[int]:
    """The markers of a JPEG up to its first scan."""
    markers, i = [], 2
    while data[i + 1] != 0xDA:
        markers.append(data[i + 1])
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return [*markers, 0xDA]


class TestABrokenJpeg:
    @pytest.mark.parametrize(
        "data",
        [
            SOI + JFIF + b"\x00" + _frame()[1:] + SCAN + EOI,  # a segment that does not start with 0xFF
            SOI + JFIF + b"\xff\xff",  # fill bytes up to the end of the file
            SOI + JFIF + _frame() + EOI,  # a frame and no scan: nothing to show
            SOI + JFIF + b"\xff\xd0\x00\x02" + _frame() + SCAN + EOI,  # a restart marker outside a scan
            SOI + JFIF + b"\xff\x01\x00\x02" + _frame() + SCAN + EOI,  # a marker of arithmetic coding's tests
            SOI + JFIF + b"\xff\xe1\x00",  # a marker with no room for its length
            SOI + JFIF + SCAN + EOI,  # a scan before any frame: no size
            SOI + JFIF + images.jpeg_segment(0xC0, b"\x08\x00\x03") + SCAN + EOI,  # a frame too short for its size
        ],
    )
    def test_is_refused_as_corrupt(self, data):
        assert _refusal(data) == "corrupt"

    def test_a_cut_frame_is_corrupt_whatever_size_it_claims(self):
        """The length is checked before the frame is read: a cut file is broken, not too large."""
        cut = _frame(width=1, height=photos.MAX_SIDE + 1)[:-1]

        assert _refusal(SOI + JFIF + cut) == "corrupt"


class TestWhatAJpegKeeps:
    def test_fill_bytes_before_a_marker_are_dropped(self):
        cleaned, _ = photos.clean_photo(SOI + JFIF + b"\xff\xff" + _frame() + SCAN + EOI)

        assert cleaned == SOI + JFIF + _frame() + SCAN + EOI

    def test_only_an_exif_block_says_the_orientation(self):
        """Another APP1 (XMP, say) is dropped unread, whatever its bytes look like."""
        not_exif = images.jpeg_segment(0xE1, b"XMP\x00\x00\x00" + images.exif(6)[6:])

        cleaned, _ = photos.clean_photo(images.jpeg(segments=[not_exif]))

        assert _segments(cleaned) == [0xE0, 0xDB, 0xC0, 0xDA]

    def test_a_later_exif_without_an_orientation_does_not_undo_the_first(self):
        data = images.jpeg(
            segments=[images.jpeg_segment(0xE1, images.exif(6)), images.jpeg_segment(0xE1, images.exif(None))]
        )

        cleaned, _ = photos.clean_photo(data)

        assert photos.exif_orientation(cleaned[cleaned.index(b"Exif") + 6 :]) == 6

    def test_between_scans_even_the_colour_profile_goes(self):
        """The colour profile, JFIF and Adobe's segment belong before the first scan; after it, every application
        segment goes."""
        between = [images.jpeg_segment(marker, b"x") for marker in (0xE0, 0xE2, 0xEE)]

        cleaned, _ = photos.clean_photo(images.progressive_jpeg(between_scans=between))

        assert cleaned == images.progressive_jpeg()

    def test_the_last_application_segment_goes_too(self):
        cleaned, _ = photos.clean_photo(images.jpeg(segments=[images.jpeg_segment(0xEF, b"x")]))

        assert _segments(cleaned) == [0xE0, 0xDB, 0xC0, 0xDA]


def _png_header(body: bytes, kind: bytes = b"IHDR") -> bytes:
    """A PNG whose first chunk is ``kind`` with ``body``, then the image data and its end."""
    return images.PNG_SIGNATURE + images.png_chunk(kind, body) + images.png()[33:]


class TestABrokenPng:
    @pytest.mark.parametrize(
        "data",
        [
            images.png()[:-10],  # cut inside the last chunk's length
            images.png()[:-12] + struct.pack(">I", 4) + images.png()[-8:],  # a chunk longer than the file
            _png_header(struct.pack(">II", 2, 2) + b"\x08\x02\x00\x00"),  # a header of 12 bytes, not 13
            _png_header(b"Comment\x00home!", kind=b"tEXt"),  # 13 bytes first, but no header
            images.png(extra=[images.png_chunk(b"ABCD", b"x")]),  # a critical chunk nobody knows
            images.png()[:33] + images.png_chunk(b"IEND", b""),  # no image data
            images.png()[:-12],  # no end
        ],
    )
    def test_is_refused_as_corrupt(self, data):
        assert _refusal(data) == "corrupt"


class TestWhatAPngKeeps:
    def test_nothing_after_its_end(self):
        cleaned, _ = photos.clean_photo(images.png() + b"PK\x03\x04 an archive with GPS 40.4N 3.7W")

        assert cleaned == images.png()


class TestABrokenWebp:
    @pytest.mark.parametrize(
        "data",
        [
            b"RIFF" + struct.pack("<I", len(images.vp8l()) + 6) + b"WEBP" + images.vp8l(),  # a size it does not have
            images.webp(images.vp8l(), b"EXIF"),  # a chunk cut inside its header
            images.webp(images.vp8l(), b"EXIF" + struct.pack("<I", 100) + b"ab"),  # a chunk longer than the file
            images.webp(images.vp8l(), images.vp8l()),  # two pictures
            images.webp(images.vp8x(3, 2)),  # no picture
            images.webp(images.webp_chunk(b"VP8X", b"\x00" * 6), images.vp8l()),  # an extended header too short
        ],
    )
    def test_is_refused_as_corrupt(self, data):
        assert _refusal(data) == "corrupt"

    @pytest.mark.parametrize(
        "data",
        [
            images.webp(images.vp8x(3, 2), images.webp_chunk(b"ANIM", b"\x00" * 6), images.vp8l()),
            images.webp(images.vp8x(3, 2), images.webp_chunk(b"ANMF", b"\x00" * 16), images.vp8l()),
            images.webp(images.vp8x(3, 2, flags=0x02), images.vp8l()),
        ],
    )
    def test_any_sign_of_an_animation_is_refused(self, data):
        assert _refusal(data) == "animated"

    @pytest.mark.parametrize(
        "data",
        [
            images.webp(images.vp8x(1, photos.MAX_SIDE + 1), images.vp8l()),
            images.webp(images.vp8(width=photos.MAX_SIDE + 1)),
            images.webp(images.vp8(height=photos.MAX_SIDE + 1)),
        ],
    )
    def test_too_many_pixels_are_refused(self, data):
        assert _refusal(data) == "dimensions"


class TestWhatAWebpKeeps:
    def test_a_lossy_webp_is_kept_as_it_is(self):
        data = images.webp(images.vp8())

        assert photos.clean_photo(data) == (data, "image/webp")

    def test_a_chunk_of_an_odd_size_is_read_and_written_with_its_padding(self):
        """RIFF pads every odd chunk to an even size: the next chunk starts after the padding."""
        data = images.webp(images.vp8x(3, 2, flags=0x20), images.webp_chunk(b"ICCP", b"abc"), images.vp8l())

        assert photos.clean_photo(data) == (data, "image/webp")

    def test_an_odd_chunk_that_goes_still_leaves_the_next_one_whole(self):
        cleaned, _ = photos.clean_photo(images.webp(images.webp_chunk(b"EXIF", b"abc"), images.vp8l()))

        assert cleaned == images.webp(images.vp8l())
