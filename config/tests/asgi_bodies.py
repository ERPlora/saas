"""Test helpers for the bodies the ASGI application reads (``config.asgi.BodiesInMemory``): a POST through the
application as Daphne sends it, and a watch on every file the process opens to write.

``files_written`` is an audit hook (``sys.addaudithook``): it sees ``open()``, ``os.open`` and ``tempfile`` alike,
whoever imported them and whenever, so a library's temporary file cannot slip past it. Python's own bytecode cache
is left aside, and so is the open of a file descriptor: it makes no new file (``open(fd)`` wraps one already opened
by its path, which the hook saw then). That second rule matters on a cold cache: ``importlib`` writes each ``.pyc``
with ``os.open(<…/__pycache__/…>)`` and then ``FileIO(fd, "wb")``, an ``open`` event whose path is only the number,
and a module imported for the first time inside a watch made the watch see it (an intermittent failure that
followed a deleted ``__pycache__``).
"""

import asyncio
import contextlib
import json
import os
import sys
import time

from asgiref.sync import async_to_sync

from accounts.signing import signed_headers

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_watches: list[list[str]] = []


def _record_writes(event: str, args: tuple) -> None:
    """Audit hook: while a watch is open, note every file this process opens to write."""
    if not _watches or event != "open":
        return
    path, mode, flags = args
    if isinstance(path, int) or "__pycache__" in str(path):
        return
    if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & _WRITE_FLAGS):
        _watches[-1].append(str(path))


sys.addaudithook(_record_writes)


@contextlib.contextmanager
def files_written():
    """The files opened to write while the block runs (none, when nothing touched the disk)."""
    written: list[str] = []
    _watches.append(written)
    try:
        yield written
    finally:
        _watches.remove(written)


def _scope(path: str, headers: list[tuple[bytes, bytes]]) -> dict:
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


def asgi_post(
    path: str, body: bytes, *, secret: str, chunks: int = 1, declared: int | None = None
) -> tuple[int, dict, int]:
    """``POST path`` through ``config.asgi.application`` as Daphne sends it (``chunks`` pieces, its
    ``Content-Length`` or ``declared``), signed with ``secret`` as the Hub signs it: its status, its JSON (``{}`` for
    another answer) and how many pieces of the body it left unread.

    Run in this thread (the test's), so Django's sync parts share the test's transaction: the test also needs Django's
    ``close_old_connections`` unhooked, as ``config/tests/test_asgi.py`` does."""
    from config.asgi import application

    signature = signed_headers("POST", path, body, int(time.time()), secret)
    length = len(body) if declared is None else declared
    headers = [(b"content-length", str(length).encode())]
    headers += [(name.lower().encode(), value.encode()) for name, value in signature.items()]
    size = -(-len(body) // chunks)
    pieces = [body[i : i + size] for i in range(0, len(body), size)] or [b""]

    async def run():
        inbox = asyncio.Queue()
        for index, piece in enumerate(pieces):
            inbox.put_nowait({"type": "http.request", "body": piece, "more_body": index < len(pieces) - 1})
        sent = []

        async def send(message):
            sent.append(message)

        await asyncio.wait_for(application(_scope(path, headers), inbox.get, send), timeout=60)
        start, *rest = sent
        payload = b"".join(message.get("body", b"") for message in rest)
        content_type = {name.lower(): value for name, value in start["headers"]}.get(b"content-type", b"")
        return start["status"], json.loads(payload) if content_type.startswith(b"application/json") else {}, inbox.qsize()

    return async_to_sync(run)()
