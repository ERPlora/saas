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

#: At most this many bytes (decoded). Shown as a data URL in ``accounts.profile.get``, whose live result must
#: stay under 256 KB (PLAN §16.2).
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


def _clean_jpeg(data: bytes) -> bytes:
    """The frame's segments before the first scan (``head``), then the scans with what goes between them
    (``body``) up to the end marker; nothing after it. Application segments and comments go, wherever they are."""
    head: list[bytes] = []
    body: list[bytes] = []
    orientation = None
    size = None
    scanned = False
    i = 2
    while True:
        if i + 1 >= len(data) or data[i] != 0xFF:
            raise PhotoRejected("corrupt")
        while data[i + 1] == 0xFF:  # fill bytes before a marker
            i += 1
            if i + 1 >= len(data):
                raise PhotoRejected("corrupt")
        marker = data[i + 1]
        if marker == _EOI:
            if not scanned:
                raise PhotoRejected("corrupt")  # no scan: nothing to show
            body.append(b"\xff\xd9")
            break  # whatever follows (a trailer, an archive) is not the picture
        if 0xD0 <= marker <= 0xD7 or marker == 0x01 or i + 4 > len(data):
            raise PhotoRejected("corrupt")
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        end = i + 2 + length
        if length < 2 or end > len(data):
            raise PhotoRejected("corrupt")
        payload = data[i + 4 : end]
        if marker == _SOS:
            if size is None:
                raise PhotoRejected("corrupt")
            scanned = True
            stop = _entropy_end(data, end)
            body.append(data[i:stop])
            i = stop
            continue
        if marker in _SOF:
            if len(payload) < 5:
                raise PhotoRejected("corrupt")
            height, width = struct.unpack(">HH", payload[1:5])
            size = (width, height)
            _check_side(width, height)
        if marker == _APP1 and payload.startswith(b"Exif\x00\x00") and not scanned:
            orientation = exif_orientation(payload[6:]) or orientation
        dropped = marker == _COM or (0xE0 <= marker <= 0xEF and (scanned or marker not in _KEPT_APP))
        if not dropped:  # EXIF, XMP, IPTC and the rest of what a camera writes go, and comments
            (body if scanned else head).append(data[i:end])
        i = end
    if orientation not in (None, 1):
        first_is_jfif = bool(head) and head[0][1] == 0xE0
        head.insert(1 if first_is_jfif else 0, _orientation_segment(orientation))
    return b"\xff\xd8" + b"".join(head) + b"".join(body)


# --- PNG ------------------------------------------------------------------------------------------

#: Chunks kept: the image, its palette and transparency, and how its colours are meant to look.
_PNG_KEPT = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs", b"bKGD"}
_PNG_ANIMATION = {b"acTL", b"fcTL", b"fdAT"}


def _clean_png(data: bytes) -> bytes:
    kept = [data[:8]]
    i = 8
    kinds = []
    while i < len(data):
        if i + 12 > len(data):
            raise PhotoRejected("corrupt")
        (length,) = struct.unpack(">I", data[i : i + 4])
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > len(data):
            raise PhotoRejected("corrupt")
        body = data[i + 8 : i + 8 + length]
        if struct.unpack(">I", data[i + 8 + length : end])[0] != zlib.crc32(kind + body):
            raise PhotoRejected("corrupt")
        if not kinds:
            if kind != b"IHDR" or length != 13:
                raise PhotoRejected("corrupt")
            _check_side(*struct.unpack(">II", body[:8]))
        if kind in _PNG_ANIMATION:
            raise PhotoRejected("animated")
        if kind in _PNG_KEPT:
            kept.append(data[i:end])
        elif kind[:1].isupper():
            raise PhotoRejected("corrupt")  # a critical chunk nobody knows: no browser would show it
        kinds.append(kind)
        i = end
        if kind == b"IEND":
            break
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


def _clean_webp(data: bytes) -> bytes:
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
        end = i + 8 + size + (size % 2)
        if end > len(data):
            raise PhotoRejected("corrupt")
        chunks.append((kind, data[i + 8 : i + 8 + size]))
        i = end
    kinds = [kind for kind, _ in chunks]
    if b"ANIM" in kinds or b"ANMF" in kinds:
        raise PhotoRejected("animated")
    images = [(kind, body) for kind, body in chunks if kind in (b"VP8 ", b"VP8L")]
    if len(images) != 1:
        raise PhotoRejected("corrupt")
    kind, body = images[0]
    _check_side(*(_vp8_size(body) if kind == b"VP8 " else _vp8l_size(body)))
    out = []
    for kind, body in chunks:
        if kind == b"VP8X":
            if len(body) < 10:
                raise PhotoRejected("corrupt")
            if body[0] & _VP8X_ANIMATION:
                raise PhotoRejected("animated")
            width = int.from_bytes(body[4:7], "little") + 1
            height = int.from_bytes(body[7:10], "little") + 1
            _check_side(width, height)
            body = bytes([body[0] & ~(_VP8X_EXIF | _VP8X_XMP)]) + body[1:]
        if kind in _WEBP_KEPT:
            out.append(kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) % 2 else b""))
    payload = b"WEBP" + b"".join(out)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload
