"""/healthz answers before the Host is validated (the ALB probes each task by its IP) and never
touches the database. Same pattern as hub-next's ``base.health``. /readyz checks the database and
keeps its answer for 10 s in the process."""

import logging

import pytest
from django.conf import settings
from django.db import OperationalError, connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import Client

from base import health


@pytest.fixture(autouse=True)
def _forget_the_last_readiness():
    """Every test starts without a remembered /readyz answer."""
    health.forget_readiness()
    yield
    health.forget_readiness()


@pytest.mark.parametrize(
    "host", ["localhost:8001", "10.0.3.17:8001", "evil.example.com"]
)
def test_healthz_is_ok_on_any_host_without_the_database(client, host):
    # No django_db mark: any query would fail the test.
    response = client.get("/healthz", HTTP_HOST=host)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_other_paths_still_validate_the_host(client):
    assert client.get("/launch/", HTTP_HOST="evil.example.com").status_code == 400


def test_only_the_exact_path_is_answered(client):
    assert client.get("/healthz/extra", HTTP_HOST="evil.example.com").status_code == 400


def test_it_is_the_first_middleware():
    """Before SecurityMiddleware (HTTPS redirect) and CommonMiddleware (ALLOWED_HOSTS)."""
    assert settings.MIDDLEWARE[0] == "base.health.HealthCheckMiddleware"


# /readyz: the database answers and every migration is applied (aws README, «Endpoints»). Route 53
# probes it on `erplora.com` after the cutover and `deploy.yml` waits for it; 503 otherwise.

HOST = "localhost:8001"


@pytest.mark.django_db
def test_readyz_is_ok_with_the_database_up_and_every_migration_applied(client):
    response = client.get("/readyz", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # Never cached by anything between Route 53 and the task.
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_readyz_is_503_when_the_database_does_not_answer(client, monkeypatch, caplog):
    def unreachable(*args, **kwargs):
        raise OperationalError("connection refused")

    # Its own read of the database fails (the rest of the stack may still reach it).
    monkeypatch.setattr(health, "MigrationExecutor", unreachable)

    with caplog.at_level(logging.WARNING, logger="base.health"):
        response = client.get("/readyz", HTTP_HOST=HOST)

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "database"}
    # The reason is logged, never sent.
    assert "connection refused" in caplog.text


@pytest.mark.django_db
def test_readyz_is_503_when_no_connection_to_the_database_opens(
    client, monkeypatch, caplog
):
    """An outage: every query of the request fails, the middleware's included (as hub-next's)."""

    def unreachable(*args, **kwargs):
        raise OperationalError("connection refused")

    monkeypatch.setattr(connection, "ensure_connection", unreachable)

    with caplog.at_level(logging.WARNING, logger="base.health"):
        response = client.get("/readyz", HTTP_HOST=HOST)

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "database"}
    assert "connection refused" in caplog.text
    assert b"connection refused" not in response.content


@pytest.mark.django_db
def test_readyz_is_503_while_a_migration_is_pending():
    leaf = next(
        node
        for node in MigrationLoader(connection).graph.leaf_nodes()
        if node[0] == "accounts"
    )
    MigrationRecorder(connection).record_unapplied(*leaf)

    response = Client().get("/readyz", HTTP_HOST=HOST)

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "migrations"}


def test_readyz_still_validates_the_host(client):
    """Unlike /healthz it is probed by name (`https://erplora.com/readyz`), never by IP."""
    assert client.get("/readyz", HTTP_HOST="evil.example.com").status_code == 400


# The answer is kept 10 s in the process (aws README, «Endpoints»: Route 53 probes it ~30 times a
# minute): the database is read at most once per window. Never in Valkey: if Valkey falls, /readyz
# must not fall with it.


class Clock:
    """``health.monotonic`` under the test's control."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(health, "monotonic", fake)
    return fake


@pytest.fixture
def reads(monkeypatch):
    """How many times /readyz read the migrations of the database."""
    count = {"reads": 0}
    real = health.MigrationExecutor

    def counted(*args, **kwargs):
        count["reads"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(health, "MigrationExecutor", counted)
    return count


@pytest.mark.django_db
def test_readyz_reads_the_database_once_per_ten_seconds(client, clock, reads):
    first = client.get("/readyz", HTTP_HOST=HOST)
    clock.now += 9.9
    second = client.get("/readyz", HTTP_HOST=HOST)

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == {"status": "ok"}
    assert reads["reads"] == 1
    # The kept answer is still never cached by anything in between.
    assert "no-cache" in second["Cache-Control"]


@pytest.mark.django_db
def test_readyz_reads_the_database_again_after_ten_seconds(client, clock, reads):
    client.get("/readyz", HTTP_HOST=HOST)
    clock.now += 10
    client.get("/readyz", HTTP_HOST=HOST)

    assert reads["reads"] == 2


@pytest.mark.django_db
def test_a_503_is_kept_too_and_the_next_window_recovers(client, clock, monkeypatch):
    real = health.MigrationExecutor
    database = {"up": False}

    def executor(*args, **kwargs):
        if not database["up"]:
            raise OperationalError("connection refused")
        return real(*args, **kwargs)

    monkeypatch.setattr(health, "MigrationExecutor", executor)

    down = client.get("/readyz", HTTP_HOST=HOST)
    database["up"] = True
    still_kept = client.get("/readyz", HTTP_HOST=HOST)
    clock.now += 10
    recovered = client.get("/readyz", HTTP_HOST=HOST)

    assert (down.status_code, still_kept.status_code, recovered.status_code) == (
        503,
        503,
        200,
    )
    assert still_kept.json() == {"status": "unavailable", "reason": "database"}


@pytest.mark.django_db
def test_a_kept_answer_still_validates_the_host(client, clock):
    assert client.get("/readyz", HTTP_HOST=HOST).status_code == 200

    assert client.get("/readyz", HTTP_HOST="evil.example.com").status_code == 400


@pytest.mark.django_db
def test_readyz_does_not_depend_on_the_cache(client, clock, settings):
    """A Valkey that is down (the cache backend fails) changes nothing: the answer lives in the
    process."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://127.0.0.1:1",
            "OPTIONS": {"socket_connect_timeout": 0.1, "socket_timeout": 0.1},
        }
    }

    first = client.get("/readyz", HTTP_HOST=HOST)
    second = client.get("/readyz", HTTP_HOST=HOST)

    assert (first.status_code, second.status_code) == (200, 200)
