"""What a business's page says of its usage (lot L4-A, PLAN-SAAS §5; mockups ``business.html``, «Uso»).

``hubs.usage.get`` is the last day the Hub measured: the storage of its files against what its plan includes
(the customer sees a percentage, never the database), the people active that day and in the 30 days up to it,
and whether that day is behind (``stale``: not yesterday's). ``hubs.business.get`` carries the same as
``usage`` (``null`` until the first night). ``hubs.usage.series`` is the days of a window, for a chart.

The space a plan includes follows its module tier (``Plan.included_level``), a decision of L4-A flagged for
Ioan (``hubs/README.md``): Free 1 GiB, Basic 5 GiB, Pro 20 GiB, Enterprise 50 GiB.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from live.errors import NotFound, PermissionDenied
from pydantic import ValidationError

from hubs import queries
from hubs.models import HubUsageDaily, Plan, Subscription
from hubs.schemas import ByIdIn, UsageGetIn, UsageSeriesIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db

GIB = 1024**3
HOST = "localhost:8001"


def yesterday():
    return datetime.now(UTC).date() - timedelta(days=1)


def sample(hub, days_ago=1, *, s3=0, db=0, on_day=0, last_30=0):
    return HubUsageDaily.objects.create(
        hub=hub,
        day=datetime.now(UTC).date() - timedelta(days=days_ago),
        s3_bytes=s3,
        db_bytes=db,
        active_users_1d=on_day,
        active_users_30d=last_30,
    )


def on_plan(hub, slug):
    """The business on ``slug``, without the Starter trial it was born with."""
    Subscription.objects.filter(hub=hub).update(
        plan=Plan.objects.get(slug=slug), trial_plan=None, trial_end=None
    )


def usage(user, hub):
    return queries.usage_get(ctx_for(user), UsageGetIn(business_id=hub.id)).model_dump()


class TestUsageGet:
    def test_the_last_day_storage_against_the_plan_and_the_people_active(
        self, business, owner
    ):
        on_plan(business, "free")
        sample(business, 4, s3=GIB, on_day=9, last_30=9)
        sample(business, 1, s3=GIB // 4, db=50 * GIB, on_day=3, last_30=4)

        assert usage(owner, business) == {
            "day": yesterday(),
            "storage": {"used_bytes": GIB // 4, "limit_bytes": GIB, "percent": 25},
            "active_users": {"on_day": 3, "last_30_days": 4},
            "stale": False,
        }

    def test_the_storage_is_the_files_never_the_database(self, business, owner):
        """PLAN-SAAS §5: the customer sees the S3 bytes as a percentage; ``db_bytes`` is the admin's."""
        on_plan(business, "free")
        sample(business, s3=0, db=10 * GIB)

        assert usage(owner, business)["storage"] == {
            "used_bytes": 0,
            "limit_bytes": GIB,
            "percent": 0,
        }

    @pytest.mark.parametrize(
        ("slug", "gib"),
        [
            ("free", 1),
            ("starter", 5),
            ("standard", 5),
            ("pro", 20),
            ("enterprise", 50),
            ("max", 50),
        ],
    )
    def test_the_space_follows_the_module_tier_of_the_plan(
        self, business, owner, slug, gib
    ):
        on_plan(business, slug)
        sample(business, s3=gib * GIB // 10)

        assert usage(owner, business)["storage"] == {
            "used_bytes": gib * GIB // 10,
            "limit_bytes": gib * GIB,
            "percent": 10,
        }

    def test_during_the_trial_the_space_is_the_trial_plans(self, business, owner):
        """Born on Free trying Starter: Starter's space while the trial lasts, as its seats."""
        sample(business, s3=GIB)

        assert usage(owner, business)["storage"]["limit_bytes"] == 5 * GIB

    def test_over_the_space_the_percent_says_so(self, business, owner):
        on_plan(business, "free")
        sample(business, s3=GIB + GIB // 10)

        assert usage(owner, business)["storage"]["percent"] == 110

    def test_a_percent_is_rounded_to_the_nearest(self, business, owner):
        on_plan(business, "free")
        sample(business, s3=GIB * 125 // 1000)  # 12.5 %

        assert usage(owner, business)["storage"]["percent"] == 13

    def test_without_a_plan_there_is_no_space_to_measure_against(self, business, owner):
        Subscription.objects.filter(hub=business).delete()
        sample(business, s3=GIB)

        assert usage(owner, business)["storage"] == {
            "used_bytes": GIB,
            "limit_bytes": None,
            "percent": None,
        }

    def test_a_day_before_yesterday_is_stale(self, business, owner):
        sample(business, 2)

        assert usage(owner, business)["stale"] is True

    def test_before_the_first_night_there_is_nothing_yet(self, business, owner):
        with pytest.raises(NotFound) as missing:
            usage(owner, business)

        assert missing.value.code == "hubs.usage_not_collected"

    def test_the_owner_and_the_admins_read_it_nobody_else(self, business, team):
        sample(business)

        assert usage(team["admin"], business)["day"] == yesterday()
        for role in ("manager", "employee"):
            with pytest.raises(PermissionDenied):
                usage(team[role], business)
        for outsider in ("stranger", "invitee"):
            with pytest.raises(NotFound) as hidden:
                usage(team[outsider], business)
            assert hidden.value.code == "not_found"
        # A visitor holds no ``hubs.view``: refused before the operation runs (over HTTP, the API's 401).
        with pytest.raises(PermissionDenied):
            usage(None, business)


class TestTheBusinessPageCarriesIt:
    def test_usage_is_null_until_the_first_night(self, business, owner):
        assert (
            queries.business_get(ctx_for(owner), ByIdIn(id=business.id)).usage is None
        )

    def test_usage_is_what_hubs_usage_get_says(self, business, owner):
        sample(business, s3=GIB, on_day=2, last_30=5)

        page = queries.business_get(ctx_for(owner), ByIdIn(id=business.id))

        assert page.usage.model_dump() == usage(owner, business)


class TestSeries:
    def test_the_days_of_the_window_oldest_first(self, business, owner):
        on_plan(business, "free")
        for days_ago, s3 in ((41, 1), (30, 2), (11, 3), (1, GIB // 2)):
            sample(business, days_ago, s3=s3, on_day=days_ago, last_30=days_ago)

        out = queries.usage_series(
            ctx_for(owner), UsageSeriesIn(business_id=business.id, days=30)
        ).model_dump()

        assert out["business_id"] == business.id
        assert out["limit_bytes"] == GIB
        assert [
            (point["day"], point["storage"]["used_bytes"]) for point in out["points"]
        ] == [
            (yesterday() - timedelta(days=29), 2),
            (yesterday() - timedelta(days=10), 3),
            (yesterday(), GIB // 2),
        ]
        assert out["points"][-1]["storage"]["percent"] == 50
        assert out["points"][-1]["active_users"] == {"on_day": 1, "last_30_days": 1}

    def test_a_window_is_one_day_to_a_year(self):
        assert (
            UsageSeriesIn(business_id="0192f0c4-0000-7000-8000-000000000000").days == 30
        )
        for days in (0, 366):
            with pytest.raises(ValidationError):
                UsageSeriesIn(
                    business_id="0192f0c4-0000-7000-8000-000000000000", days=days
                )

    def test_without_a_day_measured_the_window_is_empty(self, business, owner):
        out = queries.usage_series(
            ctx_for(owner), UsageSeriesIn(business_id=business.id)
        )

        assert out.points == []

    def test_only_the_owner_and_the_admins_read_it(self, business, team):
        with pytest.raises(PermissionDenied):
            queries.usage_series(
                ctx_for(team["employee"]), UsageSeriesIn(business_id=business.id)
            )


class TestOverHttp:
    def test_the_usage_of_a_business(self, client, business, owner):
        client.force_login(owner)
        sample(business, s3=GIB)

        response = client.get(
            "/api/hubs/usage", {"business_id": str(business.id)}, HTTP_HOST=HOST
        )

        assert response.status_code == 200
        assert response.json()["day"] == yesterday().isoformat()

    def test_before_the_first_night_the_envelope_says_why(
        self, client, business, owner
    ):
        client.force_login(owner)

        response = client.get(
            "/api/hubs/usage", {"business_id": str(business.id)}, HTTP_HOST=HOST
        )

        assert (response.status_code, response.json()["error"]["code"]) == (
            404,
            "hubs.usage_not_collected",
        )

    def test_the_series_of_a_business(self, client, business, owner):
        client.force_login(owner)
        sample(business, s3=1)

        response = client.get(
            "/api/hubs/usage/series",
            {"business_id": str(business.id), "days": 7},
            HTTP_HOST=HOST,
        )

        assert response.status_code == 200
        assert [point["day"] for point in response.json()["points"]] == [
            yesterday().isoformat()
        ]

    def test_a_window_out_of_bounds_is_a_422(self, client, business, owner):
        client.force_login(owner)

        response = client.get(
            "/api/hubs/usage/series",
            {"business_id": str(business.id), "days": 0},
            HTTP_HOST=HOST,
        )

        assert response.status_code == 422
        assert "days" in json.dumps(response.json())

    def test_an_api_key_with_hubs_read_reads_it_as_its_account(self, business, team):
        from hubs.tests.test_api_keys import get as get_with_key
        from hubs.tests.test_api_keys import key_of

        sample(business, s3=GIB)

        admin = get_with_key("/hubs/usage", key_of(team["admin"], "hubs.read"), business_id=str(business.id))
        employee = get_with_key("/hubs/usage", key_of(team["employee"], "hubs.read"), business_id=str(business.id))

        assert (admin.status_code, admin.json()["storage"]["used_bytes"]) == (200, GIB)
        assert employee.status_code == 403
