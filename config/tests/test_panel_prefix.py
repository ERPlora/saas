"""The panel lives under ``/dashboard/`` (FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX; HUBS-F10): Businesses, Store, Billing,
Account and «Report a problem», as the old product's ``apps/dashboard/``. Its addresses at the root before the move
lead there for good (301), with the page under them and the query (``?business=``, ``?surface=account``): bookmarks,
the Hub's links and the mails already sent. The sign-in's pages, the invitations and the launcher stay at the root.
"""

import uuid

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"
SHELL_MARK = '<div id="app"></div>'
BUSINESS = uuid.UUID("01a15ec0-0000-7000-8000-0000000000aa")


def is_shell(response) -> bool:
    return response.status_code == 200 and SHELL_MARK in response.content.decode(errors="replace")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("/businesses", "/dashboard/businesses"),
        (f"/businesses/{BUSINESS}", f"/dashboard/businesses/{BUSINESS}"),
        (f"/businesses/{BUSINESS}/members", f"/dashboard/businesses/{BUSINESS}/members"),
        ("/businesses?create=1", "/dashboard/businesses?create=1"),
        ("/account", "/dashboard/account"),
        ("/account/api-keys", "/dashboard/account/api-keys"),
        ("/account?surface=account", "/dashboard/account?surface=account"),
        ("/billing", "/dashboard/billing"),
        (f"/billing/invoices?business={BUSINESS}", f"/dashboard/billing/invoices?business={BUSINESS}"),
        (f"/billing/invoices/{BUSINESS}", f"/dashboard/billing/invoices/{BUSINESS}"),
        ("/store", "/dashboard/store"),
        (f"/store/plans?business={BUSINESS}", f"/dashboard/store/plans?business={BUSINESS}"),
        (f"/store/modules?business={BUSINESS}&app=sales", f"/dashboard/store/modules?business={BUSINESS}&app=sales"),
        ("/report-a-problem", "/dashboard/report-a-problem"),
    ],
)
def test_an_address_of_the_panel_at_the_root_leads_under_dashboard_for_good(client, old, new):
    response = client.get(old, HTTP_HOST=HOST)

    assert (response.status_code, response["Location"]) == (301, new)


def test_the_moved_page_is_the_panel_in_one_hop(client):
    response = client.get(f"/store/plans?business={BUSINESS}", follow=True, HTTP_HOST=HOST)

    assert response.redirect_chain == [(f"/dashboard/store/plans?business={BUSINESS}", 301)]
    assert is_shell(response)


def test_a_moved_address_never_leaves_the_site(client):
    """A path that starts with ``//`` once moved under ``/dashboard`` is still a path of this site."""
    response = client.get("/store//evil.example/x", HTTP_HOST=HOST)

    assert (response.status_code, response["Location"]) == (301, "/dashboard/store//evil.example/x")


@pytest.mark.parametrize("bare", ["/dashboard", "/dashboard/"])
def test_the_dashboard_itself_is_businesses_in_one_hop(client, bare):
    response = client.get(bare, follow=True, HTTP_HOST=HOST)

    assert response.redirect_chain == [("/dashboard/businesses", 301)]
    assert is_shell(response)


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/businesses",
        f"/dashboard/businesses/{BUSINESS}/summary",
        "/dashboard/account/profile",
        "/dashboard/billing/invoices",
        "/dashboard/store/plans",
        "/dashboard/report-a-problem",
    ],
)
def test_the_panel_under_dashboard_is_the_spa(client, path):
    assert is_shell(client.get(path, HTTP_HOST=HOST))


@pytest.mark.parametrize(
    "path",
    [
        # The entry of erplora.com and of the apps, and the old address of the sign-in's error page.
        "/launch",
        "/login/error",
        # The invitation mail links here, and the launcher's banners to one invitation.
        "/invitation",
        f"/invitations/{BUSINESS}",
        # The pages allauth's mails link to (HEADLESS_FRONTEND_URLS) and the sign-in's steps.
        "/verify-email",
        "/password/reset",
        "/password/reset/key/abc-123",
        "/2fa",
        "/2fa/authenticate",
        "/reauthenticate",
        # A first segment that only starts like a panel's one is not the panel's.
        "/businessesx",
        "/accountsx",
    ],
)
def test_the_sign_in_and_the_invitations_stay_at_the_root(client, path):
    assert is_shell(client.get(path, HTTP_HOST=HOST))


def test_the_old_sign_in_address_under_accounts_is_not_the_panels(client):
    """``/accounts/`` is allauth's old prefix, not ``/account``: it still leads to the launcher."""
    response = client.get("/accounts/login/?next=/x", HTTP_HOST=HOST)

    assert (response.status_code, response["Location"]) == (301, "/launch?next=/x")
