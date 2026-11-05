"""The HTTP server of the tests' doubles (``assistant/tests/fake_provider.py``, ``hubs/tests/hub_double.py``).

Importable without Django: the e2e starts the provider's double alone.
"""

import sys
from http.server import ThreadingHTTPServer


class QuietServer(ThreadingHTTPServer):
    """A client that cuts the conversation is what these tests do, not a failure of the double.

    ``socketserver`` prints what a request raises to stderr from a daemon thread, and a daemon thread caught holding
    stderr's lock when the interpreter closes aborts it: code 134 after every test has passed (saas#283). Anything
    else a handler raises is a real failure and is still printed.
    """

    def handle_error(self, request, client_address):
        if isinstance(sys.exception(), ConnectionError):
            return
        super().handle_error(request, client_address)
