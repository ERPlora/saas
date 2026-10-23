"""ASSISTANT-F19 (ASSISTANT-G55), ASSISTANT-F21 (G56) · The server keeps the body of the assistant's doors in memory.

Behind Daphne, Django's handler reads every request's body into a file that moves to disk past
``FILE_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB), before any view runs. A turn with its attachments (up to
``assistant.internal.TURN_BODY_BYTES``) or a dictation is larger, and its documents and audio must never touch the
disk: ``config.asgi`` keeps the body of ``/internal/assistant/*`` and ``/internal/speech/*`` in memory, up to that
ceiling, and drops what passes it (the door then answers 413). The doors are not published on the ALB, so only the
Hub reaches them. Every other path is read as Django reads it.
"""

import asyncio
import json
import time

import pytest
from asgiref.sync import async_to_sync
from django.core.signals import request_finished, request_started
from django.db import close_old_connections

from accounts.signing import signed_headers
from assistant.internal import TURN_BODY_BYTES
from assistant.tests.doors import SECRET, files_written
from config.asgi import application

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("internal", "keep_the_test_connection")]

#: Over Django's 2.5 MB of a body kept in memory.
BIG = 3_000_000


@pytest.fixture
def keep_the_test_connection():
    """Django's real handler closes old connections when a request starts and ends, which would drop the test's own
    transaction; its test client unhooks them the same way."""
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


def scope(path: str, headers: list[tuple[bytes, bytes]]) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"localhost"), (b"content-type", b"application/json"), *headers],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8001),
    }


def post(path: str, body: bytes, *, chunks: int = 1, declared: int | None = None) -> tuple[int, dict, int]:
    """``POST path`` through the ASGI application as Daphne sends it (``chunks`` pieces, its ``Content-Length`` or
    ``declared``), signed as the Hub signs it: its status, its JSON (``{}`` for another answer) and how many pieces it
    left unread."""
    signature = signed_headers("POST", path, body, int(time.time()), SECRET)
    length = len(body) if declared is None else declared
    headers = [(b"content-length", str(length).encode())] + [(k.lower().encode(), v.encode()) for k, v in signature.items()]
    size = -(-len(body) // chunks)
    pieces = [body[i : i + size] for i in range(0, len(body), size)] or [b""]

    async def run():
        inbox = asyncio.Queue()
        for index, piece in enumerate(pieces):
            inbox.put_nowait({"type": "http.request", "body": piece, "more_body": index < len(pieces) - 1})
        sent = []

        async def send(message):
            sent.append(message)

        await asyncio.wait_for(application(scope(path, headers), inbox.get, send), timeout=20)
        start, *rest = sent
        payload = b"".join(message.get("body", b"") for message in rest)
        is_json = {k.lower(): v for k, v in start["headers"]}.get(b"content-type", b"").startswith(b"application/json")
        return start["status"], json.loads(payload) if is_json else {}, inbox.qsize()

    return async_to_sync(run)()


def turn_of(size: int) -> bytes:
    return json.dumps({"hub": "nobody-here", "messages": [{"role": "user", "content": "x" * size}]}).encode()


def test_a_turn_of_several_megabytes_is_read_whole_and_never_touches_the_disk():
    with files_written() as written:
        status, body, _ = post("/internal/assistant/chat", turn_of(BIG), chunks=7)

    # Read whole, signature and contract included: the business it names is the only thing wrong.
    assert (status, body["error"]["code"]) == (404, "hub_unknown")
    assert written == []


def test_a_dictation_door_keeps_its_body_in_memory_too():
    with files_written() as written:
        post("/internal/speech/transcribe", turn_of(BIG), chunks=3)

    assert written == []


def test_any_other_path_is_read_as_django_reads_it():
    """The control catches the positive: past 2.5 MB, Django's own handler opens a file on disk."""
    with files_written() as written:
        post("/internal/elsewhere", turn_of(BIG), chunks=3)

    assert written


def test_a_body_over_the_ceiling_is_dropped_not_kept_and_refused():
    body = b"x" * (TURN_BODY_BYTES + 5)

    with files_written() as written:
        status, answer, unread = post("/internal/assistant/chat", body, chunks=4, declared=None)

    assert (status, answer["error"]["code"]) == (413, "payload_too_large")
    assert written == [] and unread == 0


class TestTheCeiling:
    def test_the_doors_keep_up_to_the_turns_ceiling_and_other_paths_are_djangos(self):
        from config.asgi import body_ceiling

        assert body_ceiling({"path": "/internal/assistant/chat", "headers": [(b"content-length", b"10")]}) == TURN_BODY_BYTES
        assert body_ceiling({"path": "/internal/speech/transcribe", "headers": []}) == TURN_BODY_BYTES
        assert body_ceiling({"path": "/internal/fiscal/documents", "headers": []}) is None
        assert body_ceiling({"path": "/api/assistant/", "headers": []}) is None

    def test_a_declared_length_over_the_ceiling_keeps_nothing(self):
        from config.asgi import body_ceiling

        over = str(TURN_BODY_BYTES + 1).encode()
        assert body_ceiling({"path": "/internal/assistant/chat", "headers": [(b"content-length", over)]}) == 0

    def test_what_passes_the_ceiling_is_received_and_dropped(self):
        from config.asgi import BodiesInMemory, _in_memory_ceiling

        messages = [
            {"type": "http.request", "body": b"x" * 8, "more_body": True},
            {"type": "http.request", "body": b"y" * 8, "more_body": True},
            {"type": "http.request", "body": b"z" * 8, "more_body": False},
        ]

        async def receive():
            return messages.pop(0)

        async def read():
            token = _in_memory_ceiling.set(10)
            try:
                return (await BodiesInMemory().read_body(receive)).getvalue()
            finally:
                _in_memory_ceiling.reset(token)

        assert async_to_sync(read)() == b"x" * 8 + b"yyy"
        assert messages == []
