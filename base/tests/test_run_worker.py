"""``manage.py run_worker``: the ``saas-worker`` task (saas#305), as the Hub's ``run_worker`` is its ``worker``'s.

SIGTERM (ECS stopping the task on a deploy) and SIGINT (Ctrl-C) only ask the loop to stop and wake its wait: the pass
in course ends, nothing else starts, and the process exits 0; the previous handlers come back. A worker that fails
exits with its code, non-zero (ECS's ``task_failed`` rule reports it).
"""

import os
import signal
import threading
import time
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from base import worker
from base.listener import Listener
from whatsapp import gateway, services

pytestmark = pytest.mark.django_db
NOTHING = dict.fromkeys(gateway.COUNTS, 0)


def run_worker() -> str:
    out = StringIO()
    call_command("run_worker", stdout=out)
    return out.getvalue()


@pytest.fixture
def no_rounds(monkeypatch):
    monkeypatch.setattr(worker, "PERIODIC", ())
    # Inside the test's transaction: ``close_old_connections`` would end it (its autocommit differs).
    monkeypatch.setattr(worker, "close_old_connections", lambda: None)


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_a_stop_signal_during_a_pass_lets_it_end_and_exits_cleanly(monkeypatch, no_rounds, sig):
    passes: list[str] = []

    def deliver_pass(stop=None):
        passes.append("started")
        os.kill(os.getpid(), sig)
        time.sleep(0.05)  # the handler runs here, in the middle of the pass
        passes.append("ended" if stop.is_set() else "not stopped")
        return dict(NOTHING)

    monkeypatch.setattr(gateway, "deliver_pass", deliver_pass)
    before = signal.getsignal(sig)

    output = run_worker()

    assert passes == ["started", "ended"]
    assert output.splitlines() == ["worker: started", "worker: stopped"]
    assert signal.getsignal(sig) is before


def test_sigterm_wakes_the_wait_at_once(monkeypatch, no_rounds):
    monkeypatch.setattr(gateway, "deliver_pass", lambda stop=None: dict(NOTHING))
    timeouts: list[float] = []
    ear = Listener(services.DELIVERY_CHANNEL)

    def wait(timeout):
        timeouts.append(timeout)
        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
        return Listener.wait(ear, timeout)

    ear.wait = wait
    monkeypatch.setattr(worker, "make_listener", lambda: ear)
    monkeypatch.setattr(worker, "next_round", lambda now: now + timedelta(hours=1))
    started = time.monotonic()

    output = run_worker()

    assert time.monotonic() - started < 5
    assert len(timeouts) == 1 and timeouts[0] > 3500
    assert output.endswith("worker: stopped\n")


def test_a_failed_worker_exits_with_its_code(monkeypatch):
    monkeypatch.setattr(worker, "run", lambda stop, listener=None: 1)

    with pytest.raises(CommandError) as failure:
        run_worker()

    assert failure.value.returncode == 1


def test_the_command_hands_the_loop_the_listener_its_signal_handler_wakes(monkeypatch):
    seen = {}

    def fake_run(stop, listener=None):
        seen["listener"] = listener
        return 0

    made = Listener(services.DELIVERY_CHANNEL)
    monkeypatch.setattr(worker, "make_listener", lambda: made)
    monkeypatch.setattr(worker, "run", fake_run)

    run_worker()

    assert seen["listener"] is made
    made.close()
