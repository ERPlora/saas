"""What a document of an authorisation may be: a PDF, recognised by its bytes (never a name or a claimed type),
sent in base64, of ``MAX_DOCUMENT_BYTES`` at most (the contract of plan 2026-10-15).

The old product refused a photo of the signed sheet for the same reason: the AEAT is handed a PDF, and a JPEG
discovered when it asks is discovered months after the customer signed. Nothing here reaches the database.
"""

import base64
import binascii

#: At most this many bytes per document, decoded.
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
#: Base64 of ``MAX_DOCUMENT_BYTES``: anything longer is too large before decoding it.
MAX_DOCUMENT_CHARACTERS = 4 * -(-MAX_DOCUMENT_BYTES // 3)
PDF_MAGIC = b"%PDF"


class DocumentRejected(ValueError):
    """The value is no document the review can keep: ``code`` says why (``too_large``, ``not_pdf``)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def decode_pdf(value: str) -> bytes:
    """The bytes of a PDF sent in base64, or ``DocumentRejected``."""
    value = value.strip()
    if len(value) > MAX_DOCUMENT_CHARACTERS:
        raise DocumentRejected("too_large")
    try:
        data = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        raise DocumentRejected("not_pdf") from None
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentRejected("too_large")
    if not data.startswith(PDF_MAGIC):
        raise DocumentRejected("not_pdf")
    return data
