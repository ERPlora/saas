"""The account's photo: what an upload may be and what is kept of it (Account → Profile, «Change photo»).

Only JPEG, PNG or WebP, recognised by their bytes (never by a name or a claimed type), at most
``MAX_PHOTO_BYTES`` and ``MAX_SIDE`` pixels a side, and still (no APNG nor animated WebP). What a camera writes
inside a photo (where it was taken, the device, comments: EXIF, XMP, IPTC, texts) is dropped; a JPEG keeps its
orientation in a minimal EXIF, so the photo does not turn sideways. The picture itself is copied byte for byte:
nothing here decodes it, which is also why the size and the pixels are read from the headers.

The panel shrinks a photo before sending it (an avatar is shown at a few dozen pixels), so the limits only
stop what did not come through it. No image library: the SaaS has none, and none is needed to read headers.
"""

import base64
import binascii
import re
import struct
import zlib
from collections.abc import Iterator

#: At most this many bytes (decoded). Shown as a data URL in ``accounts.profile.get``, whose live result must
#: stay under 256 KB.
MAX_PHOTO_BYTES = 150_000
#: Base64 of ``MAX_PHOTO_BYTES`` and a data URL's prefix: anything longer is too large before decoding it.
MAX_UPLOAD_CHARACTERS = 4 * -(-MAX_PHOTO_BYTES // 3) + len("data:image/webp;base64,")
#: At most this many pixels a side: a small file can unfold into a huge picture in every browser showing it.
MAX_SIDE = 2048
#: Uploads an account may make in an hour.
UPLOADS_PER_HOUR = 20

JPEG, PNG, WEBP = "image/jpeg", "image/png", "image/webp"
_DATA_URL = re.compile(r"^data:image/(?:jpeg|png|webp);base64,(?P<data>.*)$", re.DOTALL)


class PhotoRejected(ValueError):
    """The upload is no photo the account can keep: ``code`` says why (``unsupported``, ``too_large``,
    ``dimensions``, ``animated``, ``corrupt``)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def decode_upload(value: str) -> bytes:
    """The bytes of an upload: a ``data:image/…;base64,`` URL (what a browser's file reader gives) or plain base64."""
    value = value.strip()
    if len(value) > MAX_UPLOAD_CHARACTERS:
        raise PhotoRejected("too_large")
    if value.startswith("data:"):
        match = _DATA_URL.match(value)
        if match is None:
            raise PhotoRejected("corrupt")
        value = match.group("data")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise PhotoRejected("corrupt") from None


def clean_photo(data: bytes) -> tuple[bytes, str]:
    """``(bytes to keep, content type)`` of an uploaded photo, or ``PhotoRejected``."""
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoRejected("too_large")
    if data.startswith(b"\xff\xd8\xff"):
        return _clean_jpeg(data), JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _clean_png(data), PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _clean_webp(data), WEBP
    raise PhotoRejected("unsupported")


def _check_side(width: int, height: int) -> None:
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise PhotoRejected("dimensions")


# --- JPEG -----------------------------------------------------------------------------------------

#: Start-of-frame markers (baseline, progressive, lossless, arithmetic): their header holds the size.
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
#: Application segments kept: JFIF (APP0), the colour profile (APP2) and Adobe's colour transform (APP14).
_KEPT_APP = {0xE0, 0xE2, 0xEE}
_SOS, _EOI, _COM, _APP1 = 0xDA, 0xD9, 0xFE, 0xE1
_ORIENTATION_TAG = 0x0112


def exif_orientation(tiff: bytes) -> int | None:
    """The orientation (1–8) in the IFD0 of an EXIF block (its TIFF part, after ``Exif\\0\\0``), if any."""
    if tiff[:4] == b"II*\x00":
        order = "<"
    elif tiff[:4] == b"MM\x00*":
        order = ">"
    else:
        return None
    try:
        (offset,) = struct.unpack(order + "I", tiff[4:8])
        (count,) = struct.unpack(order + "H", tiff[offset : offset + 2])
        for index in range(count):
            entry = tiff[offset + 2 + 12 * index : offset + 14 + 12 * index]
            tag, kind, _ = struct.unpack(order + "HHI", entry[:8])
            if tag == _ORIENTATION_TAG and kind == 3:
                (value,) = struct.unpack(order + "H", entry[8:10])
                return value if 1 <= value <= 8 else None
    except struct.error:
        return None
    return None


def _orientation_segment(orientation: int) -> bytes:
    """An APP1 with a minimal EXIF: IFD0 holding only the orientation."""
    tiff = b"MM\x00*" + struct.pack(">I", 8) + struct.pack(">HHHIHH", 1, _ORIENTATION_TAG, 3, 1, orientation, 0)
    payload = b"Exif\x00\x00" + tiff + struct.pack(">I", 0)
    return bytes([0xFF, _APP1]) + struct.pack(">H", len(payload) + 2) + payload


def _entropy_end(data: bytes, start: int) -> int:
    """Where the entropy-coded data of a scan that starts at ``start`` ends: the position of the next marker
    (a stuffed ``0xFF00``, a restart marker and fill bytes are part of the data)."""
    i = start
    while True:
        j = data.find(b"\xff", i)
        if j == -1 or j + 1 >= len(data):
            raise PhotoRejected("corrupt")
        following = data[j + 1]
        if following == 0x00 or 0xD0 <= following <= 0xD7:
            i = j + 2
        elif following == 0xFF:
            i = j + 1
        else:
            return j


def _marker_at(data: bytes, i: int) -> int:
    """Where the marker that should start at ``i`` starts: past the fill bytes (``0xFF``) a marker may have before it."""
    if i + 1 >= len(data) or data[i] != 0xFF:
        raise PhotoRejected("corrupt")
    while data[i + 1] == 0xFF:
        i += 1
        if i + 1 >= len(data):
            raise PhotoRejected("corrupt")
    return i


def _segment_end(data: bytes, i: int, marker: int) -> int:
    """Where the segment of ``marker`` at ``i`` ends, by the length in its header. A restart marker or ``TEM`` carries
    no length and has no place outside a scan."""
    if 0xD0 <= marker <= 0xD7 or marker == 0x01 or i + 4 > len(data):
        raise PhotoRejected("corrupt")
    (length,) = struct.unpack(">H", data[i + 2 : i + 4])
    end = i + 2 + length
    if length < 2 or end > len(data):
        raise PhotoRejected("corrupt")
    return end


def _check_frame(payload: bytes) -> None:
    if len(payload) < 5:
        raise PhotoRejected("corrupt")
    height, width = struct.unpack(">HH", payload[1:5])
    _check_side(width, height)


def _jpeg_segments(data: bytes) -> Iterator[tuple[int, bytes]]:
    """Each segment after the start marker as ``(marker, its bytes)``, up to the end marker; nothing after it is
    read. A scan runs to the end of its entropy-coded data, and a frame's size is checked. A scan before any frame,
    or an end before any scan, is no picture."""
    framed = scanned = False
    i = 2
    while True:
        i = _marker_at(data, i)
        marker = data[i + 1]
        if marker == _EOI:
            if not scanned:
                raise PhotoRejected("corrupt")
            yield marker, data[i : i + 2]
            return
        end = _segment_end(data, i, marker)
        if marker in _SOF:
            _check_frame(data[i + 4 : end])
            framed = True
        if marker == _SOS:
            if not framed:
                raise PhotoRejected("corrupt")
            scanned = True
            end = _entropy_end(data, end)
        yield marker, data[i:end]
        i = end


def _dropped(marker: int, scanned: bool) -> bool:
    """Comments and application segments go: EXIF, XMP, IPTC and the rest of what a camera writes. Before the first
    scan, JFIF, the colour profile and Adobe's colour transform stay."""
    return marker == _COM or (0xE0 <= marker <= 0xEF and (scanned or marker not in _KEPT_APP))


def _clean_jpeg(data: bytes) -> bytes:
    """Its segments up to the end marker, without comments nor what a camera writes; a JPEG turned by its EXIF keeps
    that orientation in a minimal one."""
    kept: list[bytes] = []
    orientation = None
    scanned = False
    for marker, segment in _jpeg_segments(data):
        scanned = scanned or marker == _SOS
        if marker == _APP1 and not scanned and segment[4:].startswith(b"Exif\x00\x00"):
            orientation = exif_orientation(segment[10:]) or orientation
        if not _dropped(marker, scanned):
            kept.append(segment)
    return b"\xff\xd8" + b"".join(_with_orientation(kept, orientation))


def _with_orientation(segments: list[bytes], orientation: int | None) -> list[bytes]:
    """``segments`` with a minimal EXIF that holds ``orientation``, right after JFIF (which has to come first); an
    upright photo needs none."""
    if orientation in (None, 1):
        return segments
    at = 1 if segments and segments[0][1] == 0xE0 else 0
    return [*segments[:at], _orientation_segment(orientation), *segments[at:]]


# --- PNG ------------------------------------------------------------------------------------------

#: Chunks kept: the image, its palette and transparency, and how its colours are meant to look.
_PNG_KEPT = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs", b"bKGD"}
_PNG_ANIMATION = {b"acTL", b"fcTL", b"fdAT"}


def _png_chunks(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    """Each chunk after the signature as ``(kind, its bytes)``, its CRC checked, up to ``IEND``; nothing after it is
    read."""
    i = 8
    while i < len(data):
        if i + 12 > len(data):
            raise PhotoRejected("corrupt")
        (length,) = struct.unpack(">I", data[i : i + 4])
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > len(data):
            raise PhotoRejected("corrupt")
        if struct.unpack(">I", data[end - 4 : end])[0] != zlib.crc32(data[i + 4 : end - 4]):
            raise PhotoRejected("corrupt")
        yield kind, data[i:end]
        if kind == b"IEND":
            return
        i = end


def _check_png_header(kind: bytes, chunk: bytes) -> None:
    """The first chunk is the header, 13 bytes that start with the size."""
    if kind != b"IHDR" or len(chunk) != 12 + 13:
        raise PhotoRejected("corrupt")
    _check_side(*struct.unpack(">II", chunk[8:16]))


def _clean_png(data: bytes) -> bytes:
    kept = [data[:8]]
    kinds = []
    for kind, chunk in _png_chunks(data):
        if not kinds:
            _check_png_header(kind, chunk)
        if kind in _PNG_ANIMATION:
            raise PhotoRejected("animated")
        if kind in _PNG_KEPT:
            kept.append(chunk)
        elif kind[:1].isupper():
            raise PhotoRejected("corrupt")  # a critical chunk nobody knows: no browser would show it
        kinds.append(kind)
    if b"IDAT" not in kinds or kinds[-1:] != [b"IEND"]:
        raise PhotoRejected("corrupt")
    return b"".join(kept)


# --- WebP -----------------------------------------------------------------------------------------

_VP8X_EXIF, _VP8X_XMP, _VP8X_ANIMATION = 0x08, 0x04, 0x02
_WEBP_KEPT = {b"VP8X", b"VP8 ", b"VP8L", b"ALPH", b"ICCP"}


def _vp8_size(body: bytes) -> tuple[int, int]:
    """Width and height of a lossy (``VP8 ``) or lossless (``VP8L``) bitstream's key frame."""
    if len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
        width, height = struct.unpack("<HH", body[6:10])
        return width & 0x3FFF, height & 0x3FFF
    raise PhotoRejected("corrupt")


def _vp8l_size(body: bytes) -> tuple[int, int]:
    if len(body) >= 5 and body[0] == 0x2F:
        (bits,) = struct.unpack("<I", body[1:5])
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise PhotoRejected("corrupt")


def _webp_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Every chunk after the RIFF header as ``(kind, its data)``; the RIFF size has to be the file's."""
    (riff_size,) = struct.unpack("<I", data[4:8])
    if riff_size + 8 != len(data) or riff_size < 4:
        raise PhotoRejected("corrupt")
    chunks: list[tuple[bytes, bytes]] = []
    i = 12
    while i < len(data):
        if i + 8 > len(data):
            raise PhotoRejected("corrupt")
        kind = data[i : i + 4]
        (size,) = struct.unpack("<I", data[i + 4 : i + 8])
        end = i + 8 + size + (size % 2)  # an odd chunk is padded to an even size
        if end > len(data):
            raise PhotoRejected("corrupt")
        chunks.append((kind, data[i + 8 : i + 8 + size]))
        i = end
    return chunks


def _check_one_still_picture(chunks: list[tuple[bytes, bytes]]) -> None:
    kinds = [kind for kind, _ in chunks]
    if b"ANIM" in kinds or b"ANMF" in kinds:
        raise PhotoRejected("animated")
    images = [(kind, body) for kind, body in chunks if kind in (b"VP8 ", b"VP8L")]
    if len(images) != 1:
        raise PhotoRejected("corrupt")
    kind, body = images[0]
    _check_side(*(_vp8_size(body) if kind == b"VP8 " else _vp8l_size(body)))


def _vp8x_without_metadata(body: bytes) -> bytes:
    """The extended header, checked (no animation, a canvas within the limits), saying it holds no EXIF nor XMP."""
    if len(body) < 10:
        raise PhotoRejected("corrupt")
    if body[0] & _VP8X_ANIMATION:
        raise PhotoRejected("animated")
    width = int.from_bytes(body[4:7], "little") + 1
    height = int.from_bytes(body[7:10], "little") + 1
    _check_side(width, height)
    return bytes([body[0] & ~(_VP8X_EXIF | _VP8X_XMP)]) + body[1:]


def _clean_webp(data: bytes) -> bytes:
    chunks = _webp_chunks(data)
    _check_one_still_picture(chunks)
    out = []
    for kind, body in chunks:
        if kind == b"VP8X":
            body = _vp8x_without_metadata(body)
        if kind in _WEBP_KEPT:
            out.append(kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) % 2 else b""))
    payload = b"WEBP" + b"".join(out)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload
