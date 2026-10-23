"""Calls to the assistant's doors as the Hub makes them: ``POST /internal/assistant/…`` and ``/internal/speech/…``,
signed with the shared secret (``accounts.signing``: v1 over the body, or v2 over the method, the path and the body).

``door`` posts with Django's test client (the sync doors and the JSON ones); ``frames`` reads a streamed answer
(``text/event-stream``) into its frames, ``[DONE]`` included as the string ``"[DONE]"``.
"""

import asyncio
import contextlib
import json
import time
from typing import Any

from asgiref.sync import async_to_sync

from accounts.signing import sign, signed_headers

SECRET = "test-internal-secret"


def body_of(payload: Any) -> bytes:
    return payload if isinstance(payload, bytes) else json.dumps(payload, separators=(",", ":")).encode()


def headers_for(
    path: str, body: bytes, *, secret: str = SECRET, timestamp: int | None = None, v2: bool = False
) -> dict[str, str]:
    """The signature headers of a call, as Django's test client takes them (``HTTP_…``)."""
    stamp = int(time.time()) if timestamp is None else timestamp
    if v2:
        signed = signed_headers("POST", path, body, stamp, secret)
        return {f"HTTP_{name.upper().replace('-', '_')}": value for name, value in signed.items()}
    return {"HTTP_X_ERPLORA_TIMESTAMP": str(stamp), "HTTP_X_ERPLORA_SIGNATURE": sign(body, stamp, secret)}


def door(client, path: str, payload: Any, *, signed: bool = True, method: str = "post", **signing):
    """A call to ``path`` with ``payload`` (a dict, or raw bytes), signed unless ``signed`` is false."""
    body = body_of(payload)
    headers = headers_for(path, body, **signing) if signed else {}
    call = getattr(client, method)
    if method == "get":
        return call(path, HTTP_HOST="localhost", **headers)
    return call(path, data=body, content_type="application/json", HTTP_HOST="localhost", **headers)


def frames(response) -> list[Any]:
    """The frames of a streamed answer, in order: each ``data:`` line's JSON, or ``"[DONE]"``.

    An async stream (the door's) is read through ``async_to_sync`` from the test's thread, so what the stream does
    with the database after the answer (counting, recording) runs in the test's transaction, as the door's thread
    would under daphne.
    """
    if response.is_async:

        async def collect():
            return [chunk async for chunk in response.streaming_content]

        chunks = async_to_sync(collect)()
    else:
        chunks = list(response.streaming_content)
    return parse_frames(b"".join(chunks).decode())


def parse_frames(raw: str) -> list[Any]:
    found: list[Any] = []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                data = line[len("data: ") :]
                found.append(data if data == "[DONE]" else json.loads(data))
    return found


def error_code(response) -> str:
    return response.json()["error"]["code"]


def hang_up(response, *, after: float) -> None:
    """The Hub closing the connection ``after`` seconds into a streamed answer, as daphne does when the client goes:
    the task reading the stream is cancelled wherever it waits."""

    async def read_then_cancel():
        async def drain():
            async for _chunk in response.streaming_content:
                pass

        reading = asyncio.ensure_future(drain())
        await asyncio.sleep(after)
        reading.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reading

    async_to_sync(read_then_cancel)()
