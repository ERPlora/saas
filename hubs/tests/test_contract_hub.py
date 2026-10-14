"""The contract SaaS ↔ Hub of a business's life, end to end against the Hub double (PLAN-SAAS §2.2, §3.1,
§3.4; round 17 §2.11 and §2.14).

Over HTTP on both sides: the panel's routes with a signed-in account, the SaaS's signed calls to the
double after each COMMIT, and the double's signed ``ready`` callback to ``/internal/hubs/{id}/ready``.
"""

import json
import time

import pytest
from django.contrib.auth import get_user_model

from accounts.signing import sign
from apps.tests.factories import make_app
from hubs import hub_client, queries, services
from hubs.models import BusinessType, Hub
from hubs.schemas import ByIdIn
from hubs.tests.conftest import SECRET, ctx_for

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


@pytest.fixture
def panel(client, owner, plans, hub_double, django_capture_on_commit_callbacks):
    """The owner's panel: each request runs its after-COMMIT pushes, as in production."""
    client.force_login(owner)

    def call(method, path, data=None):
        with django_capture_on_commit_callbacks(execute=True):
            if method == "GET":
                return client.get(f"/api{path}", data or {}, HTTP_HOST=HOST)
            return client.post(
                f"/api{path}",
                json.dumps(data or {}),
                content_type="application/json",
                HTTP_HOST=HOST,
            )

    return call


def hub_reports_ready(client, hub_id):
    """What hub-next does when the business's database is cloned and seeded."""
    body, now = json.dumps({"id": str(hub_id)}).encode(), int(time.time())
    return client.post(
        f"/internal/hubs/{hub_id}/ready",
        body,
        content_type="application/json",
        headers={
            "X-Erplora-Timestamp": str(now),
            "X-Erplora-Signature": sign(body, now, SECRET),
        },
    )


def test_create_then_202_then_ready_then_it_opens(panel, client, hub_double):
    make_app("table", verticals=["restaurant"])
    BusinessType.objects.create(
        code="restaurant", name_en="Restaurant", vertical="restaurant"
    )

    created = panel(
        "POST",
        "/hubs/businesses",
        {"name": "Bar Manolo", "country": "ES", "business_type": "restaurant"},
    ).json()

    registry, state = hub_double.calls
    assert (registry.method, registry.path) == (
        "PUT",
        f"/internal/hubs/{created['id']}",
    )
    assert registry.body["vertical"] == "restaurant"
    assert (
        hub_double.registry[created["id"]]["status"] == "requested"
    )  # the double answered 202
    assert (state.path, state.body["version"]) == (
        f"/internal/hubs/{created['id']}/state",
        1,
    )
    row = panel("GET", "/hubs/businesses").json()["rows"][0]
    assert (row["status"], row["can_open"]) == ("preparing", False)

    assert hub_reports_ready(client, created["id"]).status_code == 200

    row = panel("GET", "/hubs/businesses").json()["rows"][0]
    assert (row["status"], row["can_open"]) == ("active", True)
    assert (
        panel("POST", "/hubs/businesses/open", {"id": created["id"]}).status_code == 200
    )


def test_without_a_type_no_vertical_travels(panel, hub_double):
    panel("POST", "/hubs/businesses", {"name": "Bar Manolo", "country": "ES"})

    assert hub_double.calls[0].body["vertical"] is None


def test_every_change_reaches_the_hub_with_a_newer_version(panel, hub_double):
    created = panel("POST", "/hubs/businesses", {"name": "Bar Manolo", "country": "ES"}).json()
    invited = panel(
        "POST", "/hubs/members/invite", {"hub_id": created["id"], "email": "ana@example.com", "role": "hub_manager"}
    ).json()
    ana = get_user_model().objects.get(email="ana@example.com")

    services.invitation_accept(ctx_for(ana), ByIdIn(id=invited["id"]))  # Ana's own session
    services.sync_hub(created["id"])
    panel("POST", "/hubs/members/change_role", {"id": invited["id"], "role": "hub_employee"})
    panel("POST", "/hubs/members/remove", {"id": invited["id"]})

    snapshots = hub_double.calls_to("PUT", "/state")
    versions = [call.body["version"] for call in snapshots]
    assert versions == [1, 2, 3, 4]
    assert [len(call.body["members"]) for call in snapshots] == [1, 2, 2, 1]
    assert hub_double.versions[created["id"]] == Hub.objects.get(pk=created["id"]).pushed_state_version == 4
    revoked = hub_double.calls_to("POST", "/internal/sessions/revoke")
    # L1-A2: the role travels in the Hub's session, so changing it ends Ana's sessions there too
    # (she signs in again with the new one); removing her ends them for good.
    assert [call.body for call in revoked] == [{"user_id": str(ana.pk), "hub_id": created["id"]}] * 2


def test_an_older_snapshot_never_overwrites_a_newer_one_at_the_hub(panel, hub_double):
    """The Hub's half of §2.2, as the double plays it: our versions only grow, so order never matters."""
    created = panel(
        "POST", "/hubs/businesses", {"name": "Bar Manolo", "country": "ES"}
    ).json()

    newer = {**queries.hub_snapshot(created["id"]), "version": 5}
    older = {**newer, "version": 4}

    assert hub_client.put_state(created["id"], newer).body["applied"] is True
    assert hub_client.put_state(created["id"], older).body["applied"] is False


def test_delete_then_restore_then_purged(panel, hub_double):
    created = panel(
        "POST", "/hubs/businesses", {"name": "Bar Manolo", "country": "ES"}
    ).json()

    panel(
        "POST",
        "/hubs/businesses/delete",
        {"id": created["id"], "confirm_name": "Bar Manolo"},
    )
    assert hub_double.calls_to("DELETE")[0].path == f"/internal/hubs/{created['id']}"
    assert hub_double.registry[created["id"]]["status"] == "cancelled"

    restored = panel("POST", "/hubs/businesses/restore", {"id": created["id"]}).json()
    assert restored["status"] == "preparing"
    assert hub_double.registry[created["id"]]["status"] == "ready"
    assert hub_double.calls_to("PUT", "/state")[-1].body["plan"]["slug"] == "free"

    panel(
        "POST",
        "/hubs/businesses/delete",
        {"id": created["id"], "confirm_name": "Bar Manolo"},
    )
    hub_double.answer(
        "POST", "/restore$", 409, {"error": {"code": "hub_purged", "message": "Gone."}}
    )
    panel("POST", "/hubs/businesses/restore", {"id": created["id"]})

    assert Hub.objects.get(pk=created["id"]).status == "deleted"
    assert panel("GET", "/hubs/businesses").json()["rows"] == []
