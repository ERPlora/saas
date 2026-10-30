"""A stand-in for hub-next's ``/internal`` (PLAN-SAAS §2, §3.1), for the tests of the SaaS side.

A real HTTP server (stdlib, a thread) that verifies the signature exactly as the Hub will
(``accounts.signing.verify_signed``: v2 over method, path and body when the call carries it, else the
body-only v1), records every call and answers what the test asks for, with the Hub's defaults:

- ``PUT /internal/hubs/{id}`` → 202 (asynchronous sign-up: «requested»), 200 once it is known;
- ``PUT /internal/hubs/{id}/state`` → 200, ``applied`` false for a version not newer than the last
  one applied (the Hub ignores an older snapshot, §2.2);
- ``GET /internal/hubs/{id}`` → 200 with the registry's status (a demo's too: ``requested`` until the test says
  ``ready``, ``expired`` once it ended), 404 for a hub it never got;
- ``GET /internal/hubs/{id}/dumps`` → 200 ``{"dumps": [...]}``: the copies of ``dumps[id]`` as the test sets them
  (``{id, kind, created_at, bytes}``), newest first, each with a fresh ``url`` (a presigned link of 15 minutes in the
  Hub); ``[]`` for a known hub without any, 404 for a hub it never got;
- ``DELETE /internal/hubs/{id}`` → 202; ``POST /internal/hubs/{id}/restore`` → 200;
- ``POST /internal/sessions/revoke`` → 200;
- ``GET /internal/usage?day=YYYY-MM-DD[&cursor=…]`` → 200 with the rows of ``usage[day]`` (each business's
  usage that day, as the test sets it), ``usage_page_size`` per page and ``next_cursor`` until the last;
  422 without a ``day``;
- ``POST /internal/demos`` (``{session_key, vertical, language}``) → 202 with a new ``demo-<8 hex>`` that ends
  ``DEMO_MINUTES`` later and is ``status: "requested"`` (the Hub prepares its database afterwards), or 200 with the
  live one of that ``session_key`` and its status (``created`` false): one live demo per browser, as the Hub keeps it
  (plan ``docs/plans/2026-10-17-demo-hubs-fase-1.md`` §1.5; the asynchronous demo of the tenancy, 2026-10-30);
- ``POST /internal/demos/{slug}/codes`` (``{session_key, language}``) → 201 ``{code, expires_at}``; 404 for a demo
  it never made, 410 ``base.hub_gone`` once it ended, 403 ``base.demo_not_owner`` for another browser's.

A bad or missing signature answers 401 and is recorded as refused. Only tests use it; the e2e double
of the whole ``/internal`` is ``tests/doubles/hub.py`` (lot L0-G).
"""

import json
import re
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from accounts.signing import SIGNATURE_V2_HEADER, verify_signed

HUB_PATH = re.compile(
    r"^/internal/hubs/(?P<id>[0-9a-f-]{36})(?P<rest>/state|/restore|/dumps)?$"
)
DEMO_CODES_PATH = re.compile(r"^/internal/demos/(?P<slug>[a-z0-9-]+)/codes$")
#: How long a demo of the double lives, as the Hub's ``DEMO_TTL_MINUTES``.
DEMO_MINUTES = 60


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
        #: ``GET /internal/usage``: the rows of each day (``"2026-10-13"`` → ``[{id, s3_bytes, …}]``), in pages.
        self.usage: dict[str, list[dict]] = {}
        self.usage_page_size = 500
        #: ``POST /internal/demos``: the demos it made, by slug (``{id, slug, session_key, expires_at}``,
        #: ``expires_at`` a datetime a test may move to the past).
        self.demos: dict[str, dict] = {}
        #: ``GET /internal/hubs/{id}/dumps``: the copies of each hub's data (``{id, kind, created_at, bytes}``).
        self.dumps: dict[str, list[dict]] = {}
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
        if method == "GET" and urlsplit(path).path == "/internal/usage":
            return self._usage(parse_qs(urlsplit(path).query))
        if method == "POST" and path == "/internal/demos":
            return self._create_demo(body or {})
        codes = DEMO_CODES_PATH.match(path)
        if method == "POST" and codes is not None:
            return self._create_demo_code(codes["slug"], body or {})
        match = HUB_PATH.match(path)
        if match is None:
            return 404, {"error": {"code": "not_found", "message": "No such route."}}
        hub_id, rest = match["id"], match["rest"]
        demo = self._demo_by_id(hub_id)
        if method == "GET" and rest is None and demo is not None:
            ended = demo["expires_at"] <= datetime.now(UTC)
            return 200, {"status": "expired" if ended else demo["status"]}
        if method == "GET" and rest == "/dumps":
            return self._dumps(hub_id)
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

    def _usage(self, query: dict[str, list[str]]) -> tuple[int, Any]:
        """One page of a day's usage; the cursor is the offset of the next page."""
        if not query.get("day"):
            return 422, {"error": {"code": "invalid_payload", "message": "Which day?"}}
        day, cursor = query["day"][0], query.get("cursor", ["0"])[0]
        if not cursor.isdigit():
            return 422, {"error": {"code": "invalid_cursor", "message": "Not a cursor of mine."}}
        start = int(cursor)
        rows = self.usage.get(day, [])
        end = start + self.usage_page_size
        return 200, {"day": day, "hubs": rows[start:end], "next_cursor": str(end) if end < len(rows) else None}

    def _create_demo(self, body: dict) -> tuple[int, Any]:
        """The browser's live demo (200) or a new one (201): one live demo per ``session_key``."""
        now = datetime.now(UTC)
        for demo in self.demos.values():
            if demo["session_key"] == body.get("session_key") and demo["expires_at"] > now:
                return 200, {**self._demo_out(demo), "created": False}
        slug = f"demo-{uuid.uuid4().hex[:8]}"
        self.demos[slug] = {
            "id": str(uuid.uuid7()),
            "slug": slug,
            "session_key": body.get("session_key"),
            "expires_at": now + timedelta(minutes=DEMO_MINUTES),
            "status": "requested",
        }
        return 202, {**self._demo_out(self.demos[slug]), "created": True}

    def _demo_by_id(self, hub_id: str) -> dict | None:
        return next((demo for demo in self.demos.values() if demo["id"] == hub_id), None)

    def _dumps(self, hub_id: str) -> tuple[int, Any]:
        """The hub's copies, newest first, each with a link made now (``url``)."""
        if hub_id not in self.registry and hub_id not in self.dumps:
            return 404, {"error": {"code": "not_found", "message": "Unknown hub."}}
        copies = sorted(self.dumps.get(hub_id, []), key=lambda copy: copy["created_at"], reverse=True)
        return 200, {
            "dumps": [
                {**copy, "url": f"https://dumps.example.test/{copy['id']}?X-Amz-Expires=900&X-Amz-Signature={secrets.token_hex(8)}"}
                for copy in copies
            ]
        }

    def _create_demo_code(self, slug: str, body: dict) -> tuple[int, Any]:
        demo = self.demos.get(slug)
        if demo is None:
            return 404, {"error": {"code": "not_found", "message": "Unknown demo."}}
        if demo["expires_at"] <= datetime.now(UTC):
            return 410, {"error": {"code": "base.hub_gone", "message": "This demo has ended."}}
        if demo["session_key"] != body.get("session_key"):
            return 403, {"error": {"code": "base.demo_not_owner", "message": "Not your demo."}}
        expires_at = datetime.now(UTC) + timedelta(seconds=60)
        return 201, {"code": secrets.token_urlsafe(32), "expires_at": expires_at.isoformat()}

    @staticmethod
    def _demo_out(demo: dict) -> dict:
        return {
            "id": demo["id"],
            "slug": demo["slug"],
            "status": demo["status"],
            "expires_at": demo["expires_at"].isoformat(),
        }
