"""Fixtures of base's tests, and those of the server's trusted certificates every app with outgoing calls shares."""

import shutil
import ssl

import certifi
import psycopg
import pytest
from django.db import connections


@pytest.fixture(params=["missing", "not_a_certificate"])
def unreadable_ca(request, tmp_path, monkeypatch):
    """The server's ``SSL_CERT_FILE`` naming a file that is not there (the e2e stack of the Hub starts the SaaS
    before its CA exists, hub#415), or one that holds no certificate: ``httpx`` reads it as each client is made,
    before it connects, even to an ``http://`` address."""
    path = tmp_path / "ca" / "server.pem"
    path.parent.mkdir()
    if request.param == "not_a_certificate":
        path.write_text("not a certificate\n")
    monkeypatch.setenv("SSL_CERT_FILE", str(path))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    return path


@pytest.fixture
def ca_gone_after_one_read(tmp_path, monkeypatch):
    """The server's ``SSL_CERT_FILE``, readable once and gone right after (renewed under a running server): a call
    that read the trusted certificates twice, once in ``base.tls`` and again as its client is made, would crash."""
    path = tmp_path / "server.pem"
    shutil.copyfile(certifi.where(), path)
    monkeypatch.setenv("SSL_CERT_FILE", str(path))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    read = ssl.create_default_context

    def read_then_gone(*args, **kwargs):
        context = read(*args, **kwargs)
        path.unlink(missing_ok=True)
        return context

    monkeypatch.setattr(ssl, "create_default_context", read_then_gone)
    return path


def names_the_file(text: str, path) -> bool:
    """Whether ``text`` names the setting and the file the trusted certificates were read from."""
    return f"SSL_CERT_FILE={path}" in text


@pytest.fixture
def other_session(django_db_setup):
    """A second database session, as a second task (another saas-cron or saas-migrate) would have."""
    params = connections["default"].settings_dict
    session = psycopg.connect(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
        autocommit=True,
    )
    yield session
    session.close()
