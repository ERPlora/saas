"""A provider's API on ``127.0.0.1``, for the tests of the assistant (and the e2e's seed, which starts it alone).

The clients of ``assistant.providers`` talk to it with their real network code: nothing of ours is patched. A test
scripts what each request gets (``FakeProvider.reply``) in the provider's own wire format and reads back what our
client sent (``FakeProvider.requests``). Answers are served in the order they were scripted for their method and
path; a request nothing was scripted for gets a 404 in OpenAI's error shape.

``python -m assistant.tests.fake_provider --port 8949`` serves an OpenAI-compatible API with two chat models and a
streamed answer, for the e2e (``tests/e2e/panel/assistant-admin.spec.ts``).
"""

import argparse
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Reply:
    status: int = 200
    json: Any = None
    sse: list[Any] | None = None
    body: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict)
    #: Seconds between two server-sent events (a stream that arrives piece by piece).
    delay: float = 0.0


@dataclass
class Seen:
    method: str
    path: str
    headers: dict[str, str]
    body: Any


def sse_line(event: Any) -> bytes:
    """One server-sent event: ``data: <json>`` (or the literal ``[DONE]``), or ``(name, data)`` with its ``event:``."""
    if isinstance(event, tuple):
        name, data = event
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    if isinstance(event, str):
        return f"data: {event}\n\n".encode()
    return f"data: {json.dumps(event)}\n\n".encode()


class FakeProvider:
    def __init__(self, port: int = 0):
        self._replies: dict[tuple[str, str], list[Reply]] = {}
        self._fallback: dict[tuple[str, str], Reply] = {}
        self.requests: list[Seen] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def reply(self, method: str, path: str, *, always: bool = False, **reply) -> None:
        """Script the answer to ``method path`` (the path without the query); ``always`` answers every request."""
        key = (method.upper(), path)
        with self._lock:
            if always:
                self._fallback[key] = Reply(**reply)
            else:
                self._replies.setdefault(key, []).append(Reply(**reply))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _next(self, method: str, path: str) -> Reply | None:
        key = (method, path)
        with self._lock:
            queued = self._replies.get(key)
            if queued:
                return queued.pop(0)
            return self._fallback.get(key)

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            # HTTP/1.0: the end of a body is the end of the connection, as a stream's is.
            protocol_version = "HTTP/1.0"

            def log_message(self, format, *args):  # noqa: A002 - the stdlib's name
                return

            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = raw.decode(errors="replace")
                path = self.path.split("?", 1)[0]
                with fake._lock:
                    fake.requests.append(
                        Seen(self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body)
                    )
                reply = fake._next(self.command, path)
                if reply is None:
                    reply = Reply(status=404, json={"error": {"message": f"No route {self.command} {path}"}})
                self.send_response(reply.status)
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                if reply.sse is not None:
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for event in reply.sse:
                        self.wfile.write(sse_line(event))
                        self.wfile.flush()
                        if reply.delay:
                            time.sleep(reply.delay)
                    return
                payload = reply.body if reply.body is not None else json.dumps(reply.json).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _serve
            do_POST = _serve

        return Handler


def openai_chunk(content: str | None = None, *, finish: str | None = None, tool_calls=None, usage=None) -> dict:
    """One chunk of OpenAI's streamed Chat Completions."""
    delta: dict = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    chunk: dict = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage is not None:
        chunk = {"object": "chat.completion.chunk", "choices": [], "usage": usage}
    return chunk


def serve_e2e(port: int) -> None:
    """The e2e's provider: an OpenAI-compatible API under ``/v1`` with two chat models, an embeddings model it
    leaves out, and an answer streamed in three pieces with its usage."""
    fake = FakeProvider(port)
    fake.reply(
        "GET",
        "/v1/models",
        always=True,
        json={
            "object": "list",
            "data": [
                {"id": "gpt-e2e-large", "object": "model"},
                {"id": "gpt-e2e-mini", "object": "model"},
                {"id": "text-embedding-e2e", "object": "model"},
            ],
        },
    )
    fake.reply(
        "POST",
        "/v1/chat/completions",
        always=True,
        delay=0.05,
        sse=[
            openai_chunk("Hello"),
            openai_chunk(" from the"),
            openai_chunk(" test model.", finish="stop"),
            openai_chunk(usage={"prompt_tokens": 1200, "completion_tokens": 300}),
            "[DONE]",
        ],
    )
    fake._server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8949)
    serve_e2e(parser.parse_args().port)
