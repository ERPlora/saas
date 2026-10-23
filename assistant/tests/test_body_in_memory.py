"""ASSISTANT-F19 (ASSISTANT-G55), ASSISTANT-F21 (G56) · The server keeps the body of the assistant's doors in memory.

Behind Daphne, Django's handler reads every request's body into a file that moves to disk past
``FILE_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB), before any view runs. A turn with its attachments (up to
``assistant.internal.TURN_BODY_BYTES``) or a dictation is larger, and its documents and audio must never touch the
disk: ``config.asgi`` keeps the body of ``/internal/assistant/*`` and ``/internal/speech/*`` in memory, up to that
ceiling, and drops what passes it (the door then answers 413). The doors are not published on the ALB, so only the
Hub reaches them. Every other path is read as Django reads it, but for the fiscal documents' door
(``fiscal/tests/test_internal.py``).
"""

import json

import pytest
from asgiref.sync import async_to_sync
from django.core.signals import request_finished, request_started
from django.db import close_old_connections

from assistant.internal import TURN_BODY_BYTES
from assistant.tests.doors import SECRET
from config.tests.asgi_bodies import asgi_post, files_written

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


def post(path: str, body: bytes, **sent) -> tuple[int, dict, int]:
    return asgi_post(path, body, secret=SECRET, **sent)


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
        status, answer, unread = post("/internal/assistant/chat", body, chunks=4)

    assert (status, answer["error"]["code"]) == (413, "payload_too_large")
    assert written == [] and unread == 0


class TestTheCeiling:
    def test_each_door_keeps_up_to_its_own_ceiling_and_other_paths_are_djangos(self):
        """The fiscal documents' door (``/internal/hubs/<id>/representation``, the customer's signed authorisation and
        identity documents) keeps its body in memory too, up to its own ceiling; any other path, Django's reading."""
        from config.asgi import body_ceiling
        from fiscal.internal import MAX_BODY_BYTES as REPRESENTATION_BYTES

        representation = "/internal/hubs/01a168c1-11ea-73b4-8be3-bbdd5ac322fc/representation"
        assert body_ceiling({"path": "/internal/assistant/chat", "headers": [(b"content-length", b"10")]}) == TURN_BODY_BYTES
        assert body_ceiling({"path": "/internal/speech/transcribe", "headers": []}) == TURN_BODY_BYTES
        assert body_ceiling({"path": representation, "headers": []}) == REPRESENTATION_BYTES
        assert body_ceiling({"path": f"{representation}/x", "headers": []}) is None
        assert body_ceiling({"path": "/internal/whatsapp/send", "headers": []}) is None
        assert body_ceiling({"path": "/api/assistant/", "headers": []}) is None

    def test_the_fiscal_door_follows_its_own_ceiling_not_the_turns(self, monkeypatch):
        from config.asgi import body_ceiling

        monkeypatch.setattr("fiscal.internal.MAX_BODY_BYTES", 1234)
        representation = "/internal/hubs/01a168c1-11ea-73b4-8be3-bbdd5ac322fc/representation"

        assert body_ceiling({"path": representation, "headers": []}) == 1234
        assert body_ceiling({"path": representation, "headers": [(b"content-length", b"1235")]}) == 0

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
