"""The legal notice, ``/legal/legal-notice/``."""

import pytest


# --- Legal notice -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_legal_notice_returns_200(client):
    assert client.get("/legal/legal-notice/").status_code == 200


@pytest.mark.django_db
def test_legal_notice_contains_company_data(client):
    html = client.get("/legal/legal-notice/").content.decode()

    assert "ERPLORA CLOUD S.L." in html
    assert "B27593136" in html


@pytest.mark.django_db
def test_legal_notice_gives_the_legal_contact_address(client):
    html = client.get("/legal/legal-notice/").content.decode()

    assert 'href="mailto:legal@erplora.com"' in html
