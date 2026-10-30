"""FIX-SAAS-WHATSAPP-HTTP-CALLS-CRASH-WHEN-SSL-CERT-FILE-MISSING · ``base.tls``: the server's trusted certificates for
its outgoing calls, read where ``httpx`` reads them (``SSL_CERT_FILE`` when it is set, certifi's bundle otherwise).

Unreadable (``SSL_CERT_FILE`` naming a file that is not there, or one that holds no certificate) is
``TrustStoreUnreadable``, whose message names the setting and its file, also in one ERROR line naming the caller;
never a bare ``FileNotFoundError`` or ``ssl.SSLError``."""

import logging
import ssl

import certifi
import pytest

from base import tls
from base.tests.conftest import names_the_file


def test_an_unreadable_trust_store_names_the_setting_and_its_file(unreadable_ca, caplog):
    with caplog.at_level(logging.ERROR, logger="base.tls"), pytest.raises(tls.TrustStoreUnreadable) as raised:
        tls.trusted_context("whatsapp.meta")

    assert names_the_file(raised.value.message, unreadable_ca)
    assert str(raised.value) == raised.value.message
    (line,) = [record for record in caplog.records if record.name == "base.tls"]
    assert line.levelno == logging.ERROR
    assert names_the_file(line.getMessage(), unreadable_ca)
    assert "caller=whatsapp.meta" in line.getMessage()


def test_a_file_that_is_a_folder_is_unreadable_too(tmp_path, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path))

    with pytest.raises(tls.TrustStoreUnreadable) as raised:
        tls.trusted_context("whatsapp.hub_client")

    assert names_the_file(raised.value.message, tmp_path)


def test_the_file_the_setting_names_is_the_trust_store(tmp_path, monkeypatch):
    """One certificate in the file: the context trusts that one, not certifi's whole bundle."""
    bundle = open(certifi.where(), encoding="ascii").read()
    end = "-----END CERTIFICATE-----"
    one = tmp_path / "one.pem"
    one.write_text(bundle[bundle.index("-----BEGIN CERTIFICATE-----") : bundle.index(end) + len(end)] + "\n")
    monkeypatch.setenv("SSL_CERT_FILE", str(one))

    context = tls.trusted_context("whatsapp.meta")

    assert context.cert_store_stats()["x509_ca"] == 1


def test_without_the_setting_the_trust_store_is_certifis_and_verifies(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    context = tls.trusted_context("whatsapp.meta")

    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.cert_store_stats()["x509_ca"] > 1


def test_unreadable_default_certificates_say_so_without_naming_the_setting(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(tmp_path / "gone.pem"))

    with caplog.at_level(logging.ERROR, logger="base.tls"), pytest.raises(tls.TrustStoreUnreadable) as raised:
        tls.trusted_context("whatsapp.meta")

    assert "the default certificates" in raised.value.message
    assert "SSL_CERT_FILE" not in raised.value.message
    assert any("the default certificates" in record.getMessage() for record in caplog.records)
