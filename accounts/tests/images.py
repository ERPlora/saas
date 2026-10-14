"""Small images built byte by byte for the photo tests (the project has no image library)."""

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(width=2, height=2, *, extra=(), before_idat=()) -> bytes:
    """A valid RGB PNG; ``extra`` chunks go after IHDR, ``before_idat`` right before the image data."""
    header = png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        PNG_SIGNATURE
        + header
        + b"".join(extra)
        + b"".join(before_idat)
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def exif(orientation: int | None = None, *, little_endian=False, gps=True) -> bytes:
    """An APP1 Exif payload with IFD0 holding the orientation and (as phones do) a GPS pointer."""
    order = "<" if little_endian else ">"
    entries = []
    if orientation is not None:
        entries.append(struct.pack(order + "HHI", 0x0112, 3, 1) + struct.pack(order + "H", orientation) + b"\x00\x00")
    if gps:
        entries.append(struct.pack(order + "HHII", 0x8825, 4, 1, 26))
    ifd = struct.pack(order + "H", len(entries)) + b"".join(entries) + struct.pack(order + "I", 0)
    header = (b"II*\x00" if little_endian else b"MM\x00*") + struct.pack(order + "I", 8)
    return b"Exif\x00\x00" + header + ifd + b"GPS 40.4168N 3.7038W"


def jpeg(width=4, height=3, *, segments=()) -> bytes:
    """A JPEG's structure: SOI, JFIF, ``segments``, a quantisation table, SOF0, SOS with its data, EOI."""
    jfif = jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    dqt = jpeg_segment(0xDB, b"\x00" + bytes(range(64)))
    sof = jpeg_segment(0xC0, struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00")
    sos = jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return b"\xff\xd8" + jfif + b"".join(segments) + dqt + sof + sos + b"\x12\x34\xff\x00\x56" + b"\xff\xd9"


def webp_chunk(kind: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) % 2 else b""
    return kind + struct.pack("<I", len(data)) + data + pad


def vp8l(width=3, height=2) -> bytes:
    bits = (width - 1) | ((height - 1) << 14)
    return webp_chunk(b"VP8L", b"\x2f" + struct.pack("<I", bits) + b"\x00\x00\x00")


def vp8x(width, height, flags=0) -> bytes:
    canvas = (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return webp_chunk(b"VP8X", bytes([flags, 0, 0, 0]) + canvas)


def webp(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


SCAN_DATA = b"\x12\x34\xff\x00\x56\xff\xd0\x78"  # entropy-coded data: a stuffed 0xFF and a restart marker


def progressive_jpeg(width=4, height=3, *, between_scans=()) -> bytes:
    """A progressive JPEG's structure: SOF2, a Huffman table and a scan, ``between_scans``, another table and
    scan, EOI."""
    jfif = jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    dqt = jpeg_segment(0xDB, b"\x00" + bytes(range(64)))
    sof = jpeg_segment(0xC2, struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00")
    dht = jpeg_segment(0xC4, b"\x00" + b"\x01" + b"\x00" * 15 + b"\x05")
    sos = jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return (
        b"\xff\xd8" + jfif + dqt + sof
        + dht + sos + SCAN_DATA
        + b"".join(between_scans)
        + dht + sos + SCAN_DATA
        + b"\xff\xd9"
    )
