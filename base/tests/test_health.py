"""/healthz answers before the Host is validated (the ALB probes each task by its IP) and never
touches the database. Same pattern as hub-next's ``base.health``."""

import pytest
from django.conf import settings


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
