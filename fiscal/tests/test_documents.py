"""What a document of an authorisation may be: a PDF (by its bytes, never a name), in base64, of 5 MB at most
(the contract of plan 2026-10-15; the old product refused a photo of the signed sheet the same way)."""

import base64

import pytest

from fiscal import documents
from fiscal.tests.conftest import PDF


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def rejected(value: str) -> str:
    with pytest.raises(documents.DocumentRejected) as refused:
        documents.decode_pdf(value)
    return refused.value.code


def test_a_pdf_in_base64_is_its_bytes():
    assert documents.decode_pdf(b64(PDF)) == PDF


def test_surrounding_whitespace_is_ignored():
    assert documents.decode_pdf(f"  {b64(PDF)}\n") == PDF


def test_a_jpeg_is_not_a_pdf():
    assert rejected(b64(b"\xff\xd8\xff\xe0 a photo of the sheet")) == "not_pdf"


@pytest.mark.parametrize("value", ["not base64 at all!", "JVBERi0", "%PDF-1.7"])
def test_what_does_not_decode_is_not_a_pdf(value):
    assert rejected(value) == "not_pdf"


def test_five_megabytes_is_the_ceiling():
    at_the_limit = PDF + b"x" * (documents.MAX_DOCUMENT_BYTES - len(PDF))

    assert len(documents.decode_pdf(b64(at_the_limit))) == documents.MAX_DOCUMENT_BYTES
    assert rejected(b64(at_the_limit + b"x")) == "too_large"


def test_a_huge_value_is_refused_before_decoding_it():
    assert rejected("A" * (documents.MAX_DOCUMENT_CHARACTERS + 4)) == "too_large"
