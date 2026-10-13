"""``GET /api/v1/app/release/``: the public web's ninja route, bound to ``public.app.release``.

Same address and same answer as the old view (``{"version": str | null}``, hub#400): the installed
app's runtime asks it anonymously. The behaviour of the reading itself is in ``test_appdist.py``.
"""

import pytest
from live.ninja import ensure_api_parity, operation_ids

from config.api import api

pytestmark = pytest.mark.django_db

RELEASE_URL = "/api/v1/app/release/"


def test_the_route_is_bound_to_its_operation():
    assert ensure_api_parity(api) == []
    assert "public.app.release" in operation_ids(api)


def test_the_openapi_names_it_by_its_operation(client):
    paths = client.get("/api/openapi.json").json()["paths"]

    assert paths[RELEASE_URL]["get"]["operationId"] == "public.app.release"


def test_an_anonymous_get_answers_the_version(client, monkeypatch):
    from public import appdist

    monkeypatch.setattr(appdist, "published_release", lambda bucket: "2.0.1")

    response = client.get(RELEASE_URL)

    assert response.status_code == 200
    assert response.json() == {"version": "2.0.1"}


def test_it_is_a_get(client):
    assert client.post(RELEASE_URL).status_code == 405
