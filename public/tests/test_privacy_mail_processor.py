"""Who handles erplora.com's email, as the legal pages tell it.

Production and pre send through OVH's SMTP server (``smtp.mail.ovh.net``) as a mailbox hosted at OVH, where the
erplora.com mailboxes live. Amazon SES stays declared in the infrastructure only as a way back, so no legal page may
name it, and the privacy policy lists OVH as the email processor and Amazon only for what it hosts.
"""

import re
from html import unescape

import pytest

from public.tests.conftest import without_tokens
from public.tests.test_legal import PAGES, list_items_naming, spanish

LEGAL_PAGES = [*PAGES.values(), "/legal/declaracion-responsable/"]

SES = re.compile(r"\bSES\b|Simple Email Service")

MAIL_PROCESSOR = {
    "en": (
        "OVH Hispano S.L. (Spain) — OVHcloud email:",
        "sending the service's email and hosting the erplora.com mailboxes.",
        "Processing takes place in the European Union.",
    ),
    "es": (
        "OVH Hispano S.L. (España) — correo de OVHcloud:",
        "envío del correo del servicio y alojamiento de los buzones de erplora.com.",
        "El tratamiento se realiza en la Unión Europea.",
    ),
}

EMAIL = {"en": "email", "es": "correo"}


def legal_page(client, path: str, language: str) -> str:
    html = spanish(client, path) if language == "es" else client.get(path).content.decode()
    return unescape(" ".join(without_tokens(html).split()))


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", LEGAL_PAGES)
def test_no_legal_page_names_amazon_ses(client, path, language):
    assert SES.findall(legal_page(client, path, language)) == []


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_names_ovh_as_the_email_processor(client, language):
    [mail] = list_items_naming(legal_page(client, "/legal/privacy/", language), "OVH")

    for promise in MAIL_PROCESSOR[language]:
        assert promise in mail


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_names_amazon_only_for_what_it_hosts(client, language):
    [amazon] = list_items_naming(legal_page(client, "/legal/privacy/", language), "Amazon")

    assert EMAIL[language] not in amazon
