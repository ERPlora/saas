"""«Download the data» of a business (PLAN-DB, round 2026-10-30, proposals (a), (k), (l) and (m); HUBS-F18, HUBS-F20).

The Hub copies a business's database (``pg_dump -Fc``) when it is deleted (``offboarding``) and before a reset
(``reset``), and keeps each copy 90 days. The panel lists them from ``GET /internal/hubs/{id}/dumps``
(``hubs.data_copy.list``: when, how big, which) and asks the Hub for a fresh link of 15 minutes on each click
(``hubs.data_copy.link``), so the link of a mail never expires. Only the owner. The Hub away or without copies yet is
an empty list (the page says the copy is not ready yet), never a 500.
"""

import json
from datetime import UTC, datetime

import pytest
from django.utils import timezone

from hubs import queries
from hubs.models import Hub
from hubs.schemas import ByIdIn, DataCopyLinkIn, DataCopyListIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def copy(hub, kind="offboarding", when="2026-10-30T10:15:00+00:00", size=48_213_504) -> dict:
    """A copy as the Hub lists it, without its link (the double adds one per answer)."""
    stamp = datetime.fromisoformat(when).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return {"id": f"{hub.id.hex}/{stamp}-{kind}.dump", "kind": kind, "created_at": when, "bytes": size}


def deleted(hub):
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())
    return Hub.objects.get(pk=hub.pk)


def listed(user, hub) -> dict:
    return queries.data_copy_list(ctx_for(user), DataCopyListIn(business_id=hub.id)).model_dump()


def link(user, hub, copy_id: str) -> dict:
    return queries.data_copy_link(ctx_for(user), DataCopyLinkIn(business_id=hub.id, copy_id=copy_id)).model_dump()


# --- hubs.data_copy.list ------------------------------------------------------------------------------------


def test_the_owner_of_a_deleted_business_sees_its_copies_newest_first_without_their_links(business, owner, hub_double):
    hub = deleted(business)
    older = copy(hub, "reset", "2026-10-20T08:00:00+00:00", 1_000)
    newer = copy(hub, "offboarding", "2026-10-30T10:15:00+00:00", 2_000)
    hub_double.dumps[str(hub.id)] = [older, newer]

    answer = listed(owner, hub)

    assert (answer["business_id"], answer["available"]) == (hub.id, True)
    assert [row["id"] for row in answer["copies"]] == [newer["id"], older["id"]]
    assert answer["copies"][0] == {
        "id": newer["id"],
        "kind": "offboarding",
        "created_at": datetime(2026, 10, 30, 10, 15, tzinfo=UTC),
        "bytes": 2_000,
    }
    (call,) = hub_double.calls_to("GET", "/dumps")
    assert call.path == f"/internal/hubs/{hub.id}/dumps"


def test_a_live_business_lists_the_copy_made_before_its_reset(business, owner, hub_double):
    hub_double.dumps[str(business.id)] = [copy(business, "reset")]

    (row,) = listed(owner, business)["copies"]

    assert row["kind"] == "reset"


def test_without_copies_yet_the_list_is_empty(business, owner, hub_double):
    hub = deleted(business)
    hub_double.dumps[str(hub.id)] = []

    assert listed(owner, hub)["copies"] == []


def test_a_business_without_its_own_database_has_no_copy_and_never_will(business, owner, hub_double):
    """``available: false`` (ruling 2026-10-30): the Hub never copies a business still on the shared database of
    control, so the page promises nothing."""
    hub = deleted(business)
    hub_double.dumps[str(hub.id)] = []
    hub_double.without_copies.add(str(hub.id))

    answer = listed(owner, hub)

    assert (answer["available"], answer["copies"]) == (False, [])


def test_a_hub_that_does_not_say_whether_copies_exist_is_taken_as_able_to_make_them(business, owner, hub_double):
    hub = deleted(business)
    hub_double.answer("GET", r"/dumps$", 200, {"dumps": []})

    assert (listed(owner, hub)["available"], listed(owner, hub)["copies"]) == (True, [])


@pytest.mark.parametrize("available", ["no", 0, None])
def test_an_availability_off_the_contract_is_logged(business, owner, hub_double, available, caplog):
    hub = deleted(business)
    hub_double.answer("GET", r"/dumps$", 200, {"available": available, "dumps": []})

    assert (listed(owner, hub)["available"], listed(owner, hub)["copies"]) == (True, [])
    assert f"hubs.data_copy.bad_answer hub={hub.id}" in caplog.text


def test_the_hub_away_is_an_empty_list_and_a_log(business, owner, offline_hub, caplog):
    hub = deleted(business)

    assert listed(owner, hub)["copies"] == []
    assert f"hubs.data_copy.hub_unavailable hub={hub.id}" in caplog.text


@pytest.mark.parametrize("refusal", [404, 410])
def test_a_hub_that_no_longer_has_the_business_is_an_empty_list(business, owner, hub_double, refusal, caplog):
    hub = deleted(business)
    hub_double.answer("GET", r"/dumps$", refusal, {"error": {"code": "not_found"}})

    assert listed(owner, hub)["copies"] == []
    assert f"hubs.data_copy.hub_refused hub={hub.id} status={refusal}" in caplog.text


@pytest.mark.parametrize(
    "row",
    [
        {"kind": "nightly"},
        {"created_at": "yesterday"},
        {"created_at": "2026-10-30T10:15:00"},
        {"bytes": -1},
        {"bytes": "12"},
        {"bytes": True},
        {"id": ""},
        {"id": 7},
    ],
)
def test_a_copy_off_the_contract_is_left_out_and_logged(business, owner, hub_double, row, caplog):
    hub = deleted(business)
    good = copy(hub, "reset", "2026-10-20T08:00:00+00:00")
    hub_double.answer("GET", r"/dumps$", 200, {"dumps": [{**copy(hub), "url": "https://s3.example/x", **row}, {**good, "url": "https://s3.example/y"}]})

    assert [row["id"] for row in listed(owner, hub)["copies"]] == [good["id"]]
    assert f"hubs.data_copy.bad_row hub={hub.id}" in caplog.text


@pytest.mark.parametrize("body", [{}, {"dumps": "none"}, ["dumps"], {"dumps": [None]}])
def test_an_answer_off_the_contract_is_an_empty_list_and_a_log(business, owner, hub_double, body, caplog):
    hub = deleted(business)
    hub_double.answer("GET", r"/dumps$", 200, body)

    assert listed(owner, hub)["copies"] == []
    assert f"hub={hub.id}" in caplog.text


# --- hubs.data_copy.link ------------------------------------------------------------------------------------


def test_the_link_is_asked_to_the_hub_on_each_click(business, owner, hub_double):
    """The Hub's link lasts 15 minutes: each click asks for a new one, so a page left open still downloads."""
    hub = deleted(business)
    wanted = copy(hub)
    hub_double.dumps[str(hub.id)] = [copy(hub, "reset", "2026-10-20T08:00:00+00:00"), wanted]

    first = link(owner, hub, wanted["id"])["url"]
    second = link(owner, hub, wanted["id"])["url"]

    assert first.startswith(f"https://dumps.example.test/{wanted['id']}?")
    assert second.startswith(f"https://dumps.example.test/{wanted['id']}?")
    assert first != second
    assert len(hub_double.calls_to("GET", "/dumps")) == 2


def test_a_copy_the_hub_no_longer_keeps_is_gone(business, owner, hub_double):
    from live.errors import NotFound

    hub = deleted(business)
    hub_double.dumps[str(hub.id)] = [copy(hub)]

    with pytest.raises(NotFound) as gone:
        link(owner, hub, f"{hub.id.hex}/20261001T000000Z-reset.dump")

    assert gone.value.code == "hubs.data_copy_gone"


def test_the_link_with_the_hub_away_says_to_try_again(business, owner, offline_hub):
    from live.errors import OperationError

    hub = deleted(business)

    with pytest.raises(OperationError) as away:
        link(owner, hub, f"{hub.id.hex}/20261030T101500Z-offboarding.dump")

    assert (away.value.code, away.value.status) == ("hubs.data_copy_unavailable", 503)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://s3.example/x", "", None])
def test_a_link_that_is_no_web_address_is_never_given(business, owner, hub_double, url, caplog):
    from live.errors import OperationError

    hub = deleted(business)
    wanted = copy(hub)
    hub_double.answer("GET", r"/dumps$", 200, {"dumps": [{**wanted, "url": url}]})

    with pytest.raises(OperationError) as refused:
        link(owner, hub, wanted["id"])

    assert refused.value.code == "hubs.data_copy_unavailable"
    assert f"hubs.data_copy.bad_link hub={hub.id}" in caplog.text


# --- Who, and the API ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "may"), [("owner", True), ("admin", False)])
def test_only_the_owner_is_offered_the_copy(business, team, role, may):
    """The page of a business (its owner and admins): only the owner gets «Download the data» (the rest: the matrix)."""
    can = queries.business_get(ctx_for(team[role]), ByIdIn(id=business.id)).can

    assert can.download_data is may


def test_the_panel_lists_and_downloads_through_the_api(client, business, owner, hub_double):
    hub = deleted(business)
    wanted = copy(hub)
    hub_double.dumps[str(hub.id)] = [wanted]
    client.force_login(owner)

    listing = client.get("/api/hubs/data-copies", {"business_id": str(hub.id)}, HTTP_HOST=HOST)
    download = client.get("/api/hubs/data-copies/link", {"business_id": str(hub.id), "copy_id": wanted["id"]}, HTTP_HOST=HOST)

    assert listing.status_code == 200, listing.content
    assert [row["id"] for row in json.loads(listing.content)["copies"]] == [wanted["id"]]
    assert download.status_code == 200, download.content
    assert json.loads(download.content)["url"].startswith("https://dumps.example.test/")


def test_the_hub_away_never_reaches_the_panel_as_a_500(client, business, owner, offline_hub):
    hub = deleted(business)
    client.force_login(owner)

    listing = client.get("/api/hubs/data-copies", {"business_id": str(hub.id)}, HTTP_HOST=HOST)
    download = client.get(
        "/api/hubs/data-copies/link", {"business_id": str(hub.id), "copy_id": f"{hub.id.hex}/x.dump"}, HTTP_HOST=HOST
    )

    assert (listing.status_code, json.loads(listing.content)["copies"]) == (200, [])
    assert json.loads(listing.content)["available"] is True  # away is «not ready yet», never «no copy»
    assert download.status_code == 503
    assert json.loads(download.content)["error"]["code"] == "hubs.data_copy_unavailable"
