"""The server's trusted certificates for its outgoing calls over ``httpx``: one TLS context per call, read where
``httpx`` reads them (the file ``SSL_CERT_FILE`` names when it is set, certifi's bundle otherwise).

``httpx`` loads them as each client is made, before it connects, even to an ``http://`` address, so a server whose
certificates cannot be loaded (``SSL_CERT_FILE`` naming a file that is not there, a folder, or one that holds no
certificate) failed every call with a bare ``FileNotFoundError`` or ``ssl.SSLError``. ``trusted_context`` raises
``TrustStoreUnreadable`` instead, whose message names the setting and its file, and logs it as one ERROR line with
the caller: each caller turns it into its own failure, and the client takes the context (``verify=``), so nothing
reads the certificates twice. It is the server's configuration: no attempt clears it until it is fixed. Nothing is
checked at start, on purpose: the e2e stack of the Hub starts the SaaS before its CA exists (hub#415), and every call
reads the file again, so the next one after the fix goes out.
"""

import logging
import os
import ssl

import httpx

logger = logging.getLogger(__name__)


class TrustStoreUnreadable(Exception):
    """The server's trusted certificates cannot be loaded; ``message`` names where they were read from."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def trusted_context(caller: str) -> ssl.SSLContext:
    """The TLS context of one outgoing call of ``caller`` (named in the log: ``whatsapp.meta``), or
    ``TrustStoreUnreadable``."""
    try:
        return httpx.create_ssl_context()
    except OSError as problem:  # FileNotFoundError, IsADirectoryError, PermissionError, ssl.SSLError (no certificate)
        path = os.environ.get("SSL_CERT_FILE")
        source = f"SSL_CERT_FILE={path}" if path else "the default certificates"
        message = f"The server's trusted certificates cannot be loaded from {source} ({problem.strerror or problem})."
        logger.error("base.tls.trust_store_unreadable caller=%s %s", caller, message)
        raise TrustStoreUnreadable(message) from None
