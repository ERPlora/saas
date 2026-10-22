"""The old panel's addresses of the account, for good (301), to Account in the new panel (ACCOUNTS-G113, ACCOUNTS-F30).

The installed app (``ERPlora/app``, copied as it is: working rules §12) opens the account on its own at
``/dashboard/profile/?surface=account`` (``navigation.rs``: ``ACCOUNT_PAGES``), the old SaaS's address; the person's
bookmarks and old mails hold the same ones. Each lands on its tab of Account, keeping the query: ``?surface=account``
is what paints the account without what sells (``base.surface``), and the sign-in that a signed-out visitor meets on
the way keeps it in ``next``.
"""

import json
import re

import pytest

from base.surface import SESSION_KEY as SURFACE_SESSION_KEY

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def _spa_config(response) -> dict:
    assert response.status_code == 200
    found = re.search(
        r'<script id="spa-config" type="application/json"[^>]*>(.*?)</script>', response.content.decode(), re.S
    )
    assert found, "no spa-config block"
    return json.loads(found.group(1))


OLD_ADDRESSES = [
    ("/dashboard/profile/", "/account/profile"),
    ("/dashboard/profile/sessions/", "/account/security"),
    ("/dashboard/settings/", "/account/preferences"),
]


@pytest.mark.parametrize(("old", "new"), OLD_ADDRESSES)
def test_each_old_address_leads_to_its_tab_for_good(client, old, new):
    response = client.get(old)

    assert (response.status_code, response.url) == (301, new)


@pytest.mark.parametrize(("old", "new"), OLD_ADDRESSES)
def test_the_query_survives_so_the_app_keeps_its_account_surface(client, old, new):
    response = client.get(old, {"surface": "account"})

    assert (response.status_code, response.url) == (301, f"{new}?surface=account")


@pytest.mark.usefixtures("spa_manifest")
def test_signed_out_the_app_lands_on_the_account_surface_and_keeps_it_for_the_sign_in(client):
    response = client.get("/dashboard/profile/", {"surface": "account"}, follow=True, HTTP_HOST=HOST)

    assert response.redirect_chain == [("/account/profile?surface=account", 301)]
    assert _spa_config(response)["surface"] == "account"
    assert client.session[SURFACE_SESSION_KEY] == "account"


@pytest.mark.usefixtures("spa_manifest")
def test_signed_in_the_app_opens_the_account_on_its_surface(client, ana):
    client.force_login(ana)

    response = client.get("/dashboard/profile/", {"surface": "account"}, follow=True, HTTP_HOST=HOST)

    assert response.redirect_chain == [("/account/profile?surface=account", 301)]
    assert _spa_config(response)["surface"] == "account"
