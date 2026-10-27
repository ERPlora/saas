"""The old panel's addresses of the businesses lead, for good (301), to the new panel (PLAN-SAAS §1, «Redirecciones
de URLs viejas … SE PORTAN (301): … /dashboard/*»): bookmarks, old mails and the page contracts of the old SaaS
(``pc:cloud/dashboard/overview``, ``…/hubs-active``, ``…/hubs-inactive``). Round 17 (§3.6): the panel's home is
Businesses, one list (the deleted ones in it, with «Recover»), «Create business» is its dialog and the old QR page is
«On your devices» of the business's Summary. The new panel lives under ``/dashboard/`` too
(FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX): each old address lands on its page there in one hop, never through the root.
"""

import uuid

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"
HUB = uuid.UUID("01a15ec0-0000-7000-8000-000000000001")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # HUBS-F10 (HUBS-G114, HUBS-G84, HUBS-G14): the old overview.
        ("/dashboard/", "/dashboard/businesses"),
        # HUBS-F09 (HUBS-G111, HUBS-G113, HUBS-G17, HUBS-G18): the old lists, active and inactive.
        ("/dashboard/hubs/", "/dashboard/businesses"),
        ("/dashboard/hubs/active/", "/dashboard/businesses"),
        ("/dashboard/hubs/inactive/", "/dashboard/businesses"),
        # HUBS-F03 (HUBS-G67, HUBS-G09): «Create Terminal».
        ("/dashboard/hubs/create/", "/dashboard/businesses?create=1"),
        # HUBS-F13 (HUBS-G72, HUBS-G12): the QR page.
        (f"/dashboard/hubs/{HUB}/qr/", f"/dashboard/businesses/{HUB}/summary"),
    ],
)
def test_an_old_address_leads_to_its_page_for_good(client, old, new):
    response = client.get(old, HTTP_HOST=HOST)

    assert response.status_code == 301
    assert response["Location"] == new


def test_a_query_of_the_old_list_is_not_carried_over(client):
    """The old filters (``?status=``, ``?plan=``) have no meaning in the new list."""
    assert client.get("/dashboard/hubs/active/?status=active", HTTP_HOST=HOST)["Location"] == "/dashboard/businesses"


@pytest.mark.parametrize("old", ["/dashboard/", "/dashboard/hubs/create/", f"/dashboard/hubs/{HUB}/qr/"])
def test_an_old_address_reaches_the_panel_in_one_hop(client, old):
    response = client.get(old, follow=True, HTTP_HOST=HOST)

    assert len(response.redirect_chain) == 1
    assert response.status_code == 200
