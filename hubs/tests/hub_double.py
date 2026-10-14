"""A stand-in for hub-next's ``/internal`` (PLAN-SAAS §2, §3.1), for the tests of the SaaS side.

A real HTTP server (stdlib, a thread) that verifies the signature exactly as the Hub will
(``accounts.signing.verify_signed``: v2 over method, path and body when the call carries it, else the
body-only v1), records every call and answers what the test asks for, with the Hub's defaults:

- ``PUT /internal/hubs/{id}`` → 202 (asynchronous sign-up: «requested»), 200 once it is known;
- ``PUT /internal/hubs/{id}/state`` → 200, ``applied`` false for a version not newer than the last
  one applied (the Hub ignores an older snapshot, §2.2);
- ``GET /internal/hubs/{id}`` → 200 with the registry's status, 404 for a hub it never got;
- ``DELETE /internal/hubs/{id}`` → 202; ``POST /internal/hubs/{id}/restore`` → 200;
- ``POST /internal/sessions/revoke`` → 200.

A bad or missing signature answers 401 and is recorded as refused. Only tests use it; the e2e double
of the whole ``/internal`` is ``tests/doubles/hub.py`` (lot L0-G).
"""

import json
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from accounts.signing import SIGNATURE_V2_HEADER, verify_signed

HUB_PATH = re.compile(
    r"^/internal/hubs/(?P<id>[0-9a-f-]{36})(?P<rest>/state|/restore)?$"
)


@dataclass
class Call:
    method: str
    path: str
    body: Any
    signed: bool
    headers: dict[str, str] = field(default_factory=dict)
    raw: bytes = b""

    @property
    def signed_v2(self) -> bool:
        """Signed, and by v2 (method and path included), as every call of the SaaS is."""
        return self.signed and any(key.lower() == SIGNATURE_V2_HEADER.lower() for key in self.headers)

    @property
    def hub_id(self) -> str | None:
        match = HUB_PATH.match(self.path)
        return match["id"] if match else None


class HubDouble:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls: list[Call] = []
        #: (method, path regex) → (status, body), checked before the defaults; the latest wins.
        self._answers: list[tuple[str, re.Pattern, int, Any]] = []
        self.delay = 0.0
        self.registry: dict[str, dict] = {}
        self.versions: dict[str, int] = {}
        self._lock = threading.Lock()
        double = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                status, body = double._dispatch(
                    self.command, self.path, raw, dict(self.headers)
                )
                payload = json.dumps(body).encode()
                if double.delay:
                    time.sleep(double.delay)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_PUT = do_POST = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    # --- lifecycle -------------------------------------------------------------------------------

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "HubDouble":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- what the test asks for ------------------------------------------------------------------

    def answer(
        self, method: str, path_regex: str, status: int, body: Any = None
    ) -> None:
        """Answer ``status``/``body`` to ``method`` on a path matching ``path_regex`` from now on."""
        self._answers.append(
            (
                method.upper(),
                re.compile(path_regex),
                status,
                body if body is not None else {},
            )
        )

    def calls_to(self, method: str, suffix: str = "") -> list[Call]:
        """The signed calls with ``method`` whose path ends with ``suffix``, in order."""
        return [
            c
            for c in self.calls
            if c.signed and c.method == method.upper() and c.path.endswith(suffix)
        ]

    # --- the Hub's behaviour ---------------------------------------------------------------------

    def _dispatch(
        self, method: str, path: str, raw: bytes, headers: dict[str, str]
    ) -> tuple[int, Any]:
        signed = verify_signed(method, path, raw, headers, secrets=[self.secret], now=int(time.time()))
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = raw.decode(errors="replace")
        with self._lock:
            self.calls.append(Call(method, path, body, signed, headers, raw))
            if not signed:
                return 401, {
                    "error": {"code": "unauthorized", "message": "Bad signature."}
                }
            for answer_method, pattern, status, answer_body in reversed(self._answers):
                if answer_method == method and pattern.search(path):
                    return status, answer_body
            return self._default(method, path, body)

    def _default(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        if method == "POST" and path == "/internal/sessions/revoke":
            return 200, {"revoked": 1}
        match = HUB_PATH.match(path)
        if match is None:
            return 404, {"error": {"code": "not_found", "message": "No such route."}}
        hub_id, rest = match["id"], match["rest"]
        if method == "PUT" and rest is None:
            known = hub_id in self.registry
            self.registry[hub_id] = {
                **(body or {}),
                "status": self.registry.get(hub_id, {}).get("status", "requested"),
            }
            return (200 if known else 202), {"status": self.registry[hub_id]["status"]}
        if method == "GET" and rest is None:
            if hub_id not in self.registry:
                return 404, {"error": {"code": "not_found", "message": "Unknown hub."}}
            return 200, {"status": self.registry[hub_id]["status"]}
        if method == "PUT" and rest == "/state":
            version = int((body or {}).get("version", 0))
            applied = version > self.versions.get(hub_id, 0)
            if applied:
                self.versions[hub_id] = version
            return 200, {"applied": applied, "version": self.versions.get(hub_id, 0)}
        if method == "DELETE" and rest is None:
            self.registry.setdefault(hub_id, {})["status"] = "cancelled"
            return 202, {"status": "cancelled"}
        if method == "POST" and rest == "/restore":
            self.registry.setdefault(hub_id, {})["status"] = "ready"
            return 200, {"status": "ready"}
        return 405, {"error": {"code": "method_not_allowed", "message": "Not here."}}
