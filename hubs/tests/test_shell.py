"""The installed app's doors on erplora.com: ``/shell/`` and ``/shell/open/<id>/`` (HUBS-F02, HUBS-F12).

``ERPlora/app`` boots on ``{SaaS}/shell/`` and never changes it (working-rules §12): ``/shell/`` is the launcher
(the SPA's ``/launch`` under the app's address). The app links the till to a hub only when a navigation with
``?shell=1`` leaves an entry page of the SaaS (``hub_link.rs``; PLAN-SAAS bloque 3, PLAN-HUB round 18), so
``/shell/open/<id>/`` runs «Open» (``hubs.business.open``) with the mark and sends the window to the Hub's start.
"""

import re

import pytest
from django.utils import timezone

from hubs.models import Hub, HubMember

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"


def ready(hub):
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ACTIVE, ready_at=timezone.now())


def open_from_the_app(client, hub_id):
    return client.get(f"/shell/open/{hub_id}/", HTTP_HOST=HOST)


def test_the_apps_start_is_the_launcher(client):
    """HUBS-F02 (HUBS-G66): ``/shell/`` answers the SPA, whose router shows the launcher there."""
    response = client.get("/shell/", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert re.search(r'<script id="spa-config" type="application/json"', response.content.decode())


def test_open_sends_the_window_to_the_hub_with_the_shell_mark(client, business, owner):
    """HUBS-F12 (HUBS-G71): the jump starts at the Hub, marked, and the business is remembered as the last
    opened (the launcher lists it first)."""
    ready(business)
    client.force_login(owner)

    response = open_from_the_app(client, business.id)

    assert response.status_code == 302
    assert response["Location"] == "http://bar-manolo.localhost:8000/auth/login?next=/&shell=1"
    assert HubMember.objects.get(hub=business, user=owner).last_opened_at is not None
    assert response["Cache-Control"].startswith("max-age=0")


def test_signed_out_it_signs_in_on_the_apps_start_and_comes_back(client, business):
    response = open_from_the_app(client, business.id)

    assert response.status_code == 302
    assert response["Location"] == f"/shell/?next=/shell/open/{business.id}/"


@pytest.mark.parametrize("who", ["stranger", "invitee"])
def test_a_business_of_someone_else_is_not_found(client, business, team, who):
    """Old saas SAAS_DASHBOARD-F07: «un negocio ajeno, 404»; an invitation is accepted first."""
    ready(business)
    client.force_login(team[who])

    assert open_from_the_app(client, business.id).status_code == 404


def test_one_that_does_not_open_goes_back_to_the_launcher(client, business, owner):
    """Being prepared (or suspended, or deleted): the launcher says why it does not open."""
    client.force_login(owner)

    response = open_from_the_app(client, business.id)

    assert response.status_code == 302
    assert response["Location"] == "/shell/"
    assert HubMember.objects.get(hub=business, user=owner).last_opened_at is None


def test_only_get(client, business, owner):
    ready(business)
    client.force_login(owner)

    response = client.post(f"/shell/open/{business.id}/", HTTP_HOST=HOST)

    assert response.status_code == 405
