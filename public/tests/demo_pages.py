"""What the tests of the demo's door (public/demo.py) share: its addresses, the page they read, the demo they
start in this browser and the calls the Hub double hears.
"""

import re

from django.conf import settings
from django.test import Client

from accounts.queries.hub_links import hub_start_url

DOOR = "/demo/"
START = "/demo/start/"
ENTER = "/demo/enter/"
STATUS = "/demo/status/"
TRY = "/try/"
DEMO_SLUG = re.compile(r"demo-[0-9a-f]{8}")


def page(response) -> str:
    assert response.status_code == 200
    return response.content.decode()


def state_of(html: str) -> str:
    (state,) = re.findall(r'data-testid="demo-state-([a-z_]+)"', html)
    return state


def start(client: Client, double, *, ready: bool = True) -> str:
    """Start a demo in this browser; its slug. The Hub prepares a new one after answering (202 «requested»): unless
    ``ready`` is false, the double finishes it and the browser asks its status as the door's page does, which jumps
    into it."""
    response = client.post(START)
    assert response.status_code == 302, response.content
    slug = client.session["demo"]["slug"]
    if response["Location"] == DOOR and ready:
        double.demos[slug]["status"] = "ready"
        assert status(client) == {"state": "ready", "url": hub_start_url(slug, "/")}
    return slug


def status(client: Client) -> dict:
    """What the door's page hears when it asks how the browser's demo is going (``/demo/status/``)."""
    response = client.get(STATUS, HTTP_ACCEPT="application/json")
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/json"
    return response.json()


def demo_calls(double):
    return double.calls_to("POST", "/internal/demos")


def code_calls(double):
    return double.calls_to("POST", "/codes")


def enter(client: Client, slug: str, **params):
    return client.get(ENTER, {"hub": slug, "next": "/", "state": "the-hubs-state", **params})


def spanish(client: Client) -> Client:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    return client
