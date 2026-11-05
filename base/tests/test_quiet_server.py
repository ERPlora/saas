"""The HTTP server of the tests' doubles: a client that cuts the conversation says nothing (saas#283).

The harm is an interpreter that aborts on its way out, code 134 after every test has passed: ``socketserver`` prints
what a request raises to stderr from a daemon thread, and a daemon thread caught holding stderr's lock at the exit
is fatal. Each scenario runs in a Python of its own and makes that race certain: the client cuts as the interpreter
closes, and its stderr never finishes a write, so whoever writes there keeps the lock.
"""

import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from assistant.tests.fake_provider import FakeProvider

REPO = Path(__file__).resolve().parents[2]
A_SERVER_OF_ITS_OWN = re.compile(r"\b\w*(?:HTTP|TCP)Server\b")

CUT_AS_THE_INTERPRETER_CLOSES = """
import atexit, io, socket, struct, sys, threading, time

caught = threading.Event()

class NeverEnds(io.RawIOBase):
    def writable(self):
        return True

    def write(self, data):
        caught.set()
        threading.Event().wait()

def handlers():
    return [thread for thread in threading.enumerate() if "process_request" in thread.name]

def cut():
    if "client" not in globals():  # the conversation never began: its traceback is on the real stderr
        return
    sys.stderr = io.TextIOWrapper(io.BufferedWriter(NeverEnds()), line_buffering=True)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    client.close()
    deadline = time.monotonic() + 30
    while handlers() and not caught.is_set() and time.monotonic() < deadline:
        time.sleep(0.01)

atexit.register(cut)  # the first in is the last out: after logging has flushed the stderr it knows
"""

STREAM_OF_THE_PROVIDER = """
from assistant.tests.fake_provider import FakeProvider, openai_chunk

fake = FakeProvider()
fake.reply("POST", "/v1/chat/completions", sse=[openai_chunk("piece")] * 50, delay=0.05)
fake.start()
client = socket.create_connection(fake._server.server_address)
client.sendall(b"POST /v1/chat/completions HTTP/1.0\\r\\nContent-Length: 0\\r\\n\\r\\n")
client.recv(1)  # the answer has begun
"""

REQUEST_TO_THE_PROVIDER = """
from assistant.tests.fake_provider import FakeProvider

fake = FakeProvider()
fake.start()
client = socket.create_connection(fake._server.server_address)
client.sendall(b"POST /v1/chat/completions HTTP/1.0\\r\\nContent-Length: 100\\r\\n\\r\\nonly a part of it")
while not handlers():  # the double is reading what will never arrive
    time.sleep(0.01)
"""

SLOW_ANSWER_OF_THE_HUB = """
from hubs.tests.hub_double import HubDouble

double = HubDouble("secret")
double.delay = 1
double.start()
client = socket.create_connection(double.server.server_address)
client.sendall(b"GET /internal/usage HTTP/1.0\\r\\nContent-Length: 0\\r\\n\\r\\n")
while not double.calls:  # it has the call and waits before it answers
    time.sleep(0.01)
"""


@pytest.mark.parametrize(
    "conversation",
    [
        pytest.param(STREAM_OF_THE_PROVIDER, id="provider-mid-stream"),
        pytest.param(REQUEST_TO_THE_PROVIDER, id="provider-mid-request"),
        pytest.param(SLOW_ANSWER_OF_THE_HUB, id="hub-before-the-answer"),
    ],
)
def test_a_client_that_cuts_does_not_abort_the_interpreter(conversation):
    ended = subprocess.run(
        [sys.executable, "-c", CUT_AS_THE_INTERPRETER_CLOSES + conversation],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert ended.returncode == 0, ended.stderr


@pytest.mark.parametrize("error", [ZeroDivisionError, ValueError, OSError])  # OSError: the parent of what it hushes
def test_a_handler_that_breaks_still_says_so(error, capsys):
    def breaks(body):
        raise error("the handler broke")

    fake = FakeProvider()
    fake.reply("POST", "/v1/embeddings", answer=breaks)
    fake.start()
    try:
        with socket.create_connection(fake._server.server_address) as client:
            client.sendall(b"POST /v1/embeddings HTTP/1.0\r\nContent-Length: 0\r\n\r\n")
            assert client.recv(1) == b""  # the double closes only once it has reported
    finally:
        fake.stop()

    assert error.__name__ in capsys.readouterr().err


@pytest.mark.parametrize(
    "source",
    [
        'ThreadingHTTPServer(("127.0.0.1", 0), Handler)',
        'http.server.HTTPServer(("127.0.0.1", 0), Handler)',
        "class Mine(ThreadingHTTPServer):",
        "from http.server import ThreadingHTTPServer as Server",
        'socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)',
    ],
)
def test_the_guard_sees_every_way_of_a_server_of_its_own(source):
    assert A_SERVER_OF_ITS_OWN.search(source)


@pytest.mark.parametrize(
    "source",
    ['QuietServer(("127.0.0.1", 0), Handler)', "from http.server import BaseHTTPRequestHandler"],
)
def test_the_guard_lets_a_double_on_the_quiet_server_be(source):
    assert not A_SERVER_OF_ITS_OWN.search(source)


def test_no_double_starts_a_server_of_its_own():
    allowed = {REPO / "base/tests/quiet_server.py", Path(__file__).resolve()}
    doubles = [path for path in REPO.glob("*/tests/**/*.py") if path not in allowed]

    assert doubles, "the search finds the tests"
    assert [path for path in doubles if A_SERVER_OF_ITS_OWN.search(path.read_text())] == []
