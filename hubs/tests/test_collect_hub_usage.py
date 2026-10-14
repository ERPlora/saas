"""``collect_hub_usage`` (``saas-cron``, nightly; lot L4-A, PLAN-SAAS §5): one day's usage of every business.

The Hub measures each business every night (the bytes of its files in S3 and of its database, the people
active that day and in the 30 days up to it) and serves it at ``GET /internal/usage?day=``, in pages. The
SaaS keeps one ``HubUsageDaily`` row per business and day, written by the system command
``hubs.usage.record``; collecting a day again replaces its figures and changes nothing when they are the
same. A changed day is told to the owner and the admins of the business (``hubs.business.usage_collected``),
whose page re-runs. Under the advisory lock ``hashtext('erplora.saas.collect_hub_usage')``; a failure
(the Hub away or refusing, an answer that breaks the contract) never stops the pass and makes the run end
with an error after it (the ``task_failed`` alarm).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.management.base import CommandError
from live.errors import PermissionDenied
from live.live_registry import live_registry

from hubs import events, services
from hubs.models import HubUsageDaily
from hubs.schemas import UsageRecordIn
from hubs.tests.conftest import create_business, ctx_for
from hubs.tests.test_live import channels, notified  # noqa: F401 - the fixture of the notifications
from hubs.tests.test_reconcile_hub_states import run

pytestmark = pytest.mark.django_db

#: The advisory lock a run holds (the SaaS's convention, as ``push_hub_snapshots``).
LOCK_KEY = "hashtext('erplora.saas.collect_hub_usage')"
DAY = date(2026, 10, 13)
GIB = 1024**3


def row(hub_id, **values):
    return {
        "id": str(hub_id),
        "s3_bytes": 0,
        "db_bytes": 0,
        "active_users_1d": 0,
        "active_users_30d": 0,
        **values,
    }


def collect(*args):
    return run("collect_hub_usage", "--day", DAY.isoformat(), *args)


def figures(hub):
    sample = HubUsageDaily.objects.get(hub=hub, day=DAY)
    return (
        sample.s3_bytes,
        sample.db_bytes,
        sample.active_users_1d,
        sample.active_users_30d,
    )


class TestCollect:
    def test_each_business_gets_its_day_as_the_hub_measured_it(
        self, business, hub_double
    ):
        hub_double.usage[DAY.isoformat()] = [
            row(
                business.id,
                s3_bytes=5 * GIB,
                db_bytes=300_000,
                active_users_1d=3,
                active_users_30d=4,
            )
        ]

        output = collect()

        assert figures(business) == (5 * GIB, 300_000, 3, 4)
        (call,) = hub_double.calls_to("GET")
        assert call.path == "/internal/usage?day=2026-10-13" and call.signed_v2
        assert "recorded=1" in output

    def test_by_default_it_collects_yesterday_utc(self, business, hub_double):
        run("collect_hub_usage")

        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        (call,) = hub_double.calls_to("GET")
        assert call.path == f"/internal/usage?day={yesterday.isoformat()}"

    def test_a_day_not_over_yet_is_refused_without_asking(self, hub_double):
        with pytest.raises(CommandError, match="not over"):
            run("collect_hub_usage", "--day", datetime.now(UTC).date().isoformat())

        assert hub_double.calls == []

    def test_running_it_again_changes_nothing(self, business, hub_double):
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, s3_bytes=10, active_users_1d=1, active_users_30d=2)
        ]
        collect()

        output = collect()

        assert HubUsageDaily.objects.filter(hub=business).count() == 1
        assert "recorded=0" in output and "unchanged=1" in output

    def test_a_new_measure_of_the_same_day_replaces_it(self, business, hub_double):
        hub_double.usage[DAY.isoformat()] = [row(business.id, s3_bytes=10)]
        collect()
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, s3_bytes=20, active_users_1d=2, active_users_30d=2)
        ]

        collect()

        assert figures(business) == (20, 0, 2, 2)
        assert HubUsageDaily.objects.filter(hub=business).count() == 1

    def test_it_follows_the_pages_of_the_hub(self, owner, plans, make_user, hub_double):
        hubs = [
            create_business(owner),
            create_business(make_user("lola@example.com"), name="Café Lola"),
            create_business(make_user("pepe@example.com"), name="Bar Pepe"),
        ]
        hub_double.usage[DAY.isoformat()] = [
            row(hub.id, s3_bytes=index) for index, hub in enumerate(hubs, 1)
        ]
        hub_double.usage_page_size = 2

        output = collect()

        assert [figures(hub)[0] for hub in hubs] == [1, 2, 3]
        assert [call.path for call in hub_double.calls_to("GET")] == [
            "/internal/usage?day=2026-10-13",
            "/internal/usage?day=2026-10-13&cursor=2",
        ]
        assert "pages=2" in output and "recorded=3" in output

    def test_a_business_the_saas_does_not_know_is_skipped_not_failed(
        self, business, hub_double
    ):
        """The Hub also runs hubs the panel never sold (ERPlora's own, the templates): not an error."""
        hub_double.usage[DAY.isoformat()] = [row(business.id), row(uuid.uuid7())]

        output = collect()

        assert HubUsageDaily.objects.filter(hub=business).exists()
        assert "unknown=1" in output

    def test_a_broken_row_is_skipped_the_rest_is_kept_and_the_run_fails(
        self, business, hub_double
    ):
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, s3_bytes=7),
            {
                "id": "not-a-uuid",
                "s3_bytes": 1,
                "db_bytes": 1,
                "active_users_1d": 0,
                "active_users_30d": 0,
            },
            row(uuid.uuid7(), s3_bytes=-1),
            # More people in one day than in the 30 days that hold it.
            row(uuid.uuid7(), active_users_1d=5, active_users_30d=4),
            {"id": str(uuid.uuid7())},
        ]

        with pytest.raises(CommandError) as failed:
            collect()

        assert figures(business)[0] == 7
        assert "invalid=4" in str(failed.value)

    def test_an_answer_for_another_day_is_not_stored_and_the_run_fails(
        self, business, hub_double
    ):
        hub_double.answer(
            "GET",
            r"^/internal/usage",
            200,
            {"day": "2026-10-12", "hubs": [row(business.id)], "next_cursor": None},
        )

        with pytest.raises(CommandError) as failed:
            collect()

        assert not HubUsageDaily.objects.exists()
        assert "invalid=1" in str(failed.value)

    def test_a_hub_that_sends_the_same_cursor_again_ends_the_pass_and_the_run_fails(
        self, business, hub_double
    ):
        hub_double.answer(
            "GET",
            r"^/internal/usage",
            200,
            {
                "day": DAY.isoformat(),
                "hubs": [row(business.id)],
                "next_cursor": "again",
            },
        )

        with pytest.raises(CommandError) as failed:
            collect()

        assert len(hub_double.calls_to("GET")) == 2
        assert HubUsageDaily.objects.filter(hub=business).count() == 1
        assert "invalid=1" in str(failed.value)

    def test_with_the_hub_away_nothing_is_stored_and_the_run_fails(
        self, business, offline_hub
    ):
        with pytest.raises(CommandError) as failed:
            collect()

        assert not HubUsageDaily.objects.exists()
        assert "unreachable=1" in str(failed.value)

    def test_a_refusal_of_the_hub_fails_the_run_after_what_it_had(
        self, owner, plans, make_user, hub_double
    ):
        """A page refused after another: the first page's days stay, and the run fails."""
        first, second = (
            create_business(owner),
            create_business(make_user("lola@example.com"), name="Café Lola"),
        )
        hub_double.usage[DAY.isoformat()] = [row(first.id), row(second.id)]
        hub_double.usage_page_size = 1
        hub_double.answer(
            "GET",
            r"cursor=",
            409,
            {"error": {"code": "usage_not_ready", "message": "Not yet."}},
        )

        with pytest.raises(CommandError) as failed:
            collect()

        assert list(HubUsageDaily.objects.values_list("hub_id", flat=True)) == [
            first.id
        ]
        assert "refused=1" in str(failed.value)

    def test_a_second_run_returns_at_once_while_one_holds_the_lock(
        self, business, hub_double, other_session
    ):
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

        output = collect()

        assert hub_double.calls == []
        assert "already running" in output
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

    def test_the_lock_is_released_after_a_run(
        self, business, hub_double, other_session
    ):
        collect()

        assert (
            other_session.execute(
                f"SELECT pg_try_advisory_lock({LOCK_KEY})"
            ).fetchone()[0]
            is True
        )
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")


class TestTheyHearOfIt:
    def test_the_owner_and_the_admins_hear_of_a_new_day(
        self,
        business,
        team,
        hub_double,
        notified,
        django_capture_on_commit_callbacks,  # noqa: F811
    ):
        hub_double.usage[DAY.isoformat()] = [row(business.id, s3_bytes=1)]

        with django_capture_on_commit_callbacks(execute=True):
            collect()

        assert channels(notified, events.BUSINESS_USAGE_COLLECTED) == {
            str(team["owner"].pk),
            str(team["admin"].pk),
        }

    def test_the_same_figures_again_tell_nobody(
        self,
        business,
        hub_double,
        notified,
        django_capture_on_commit_callbacks,  # noqa: F811
    ):
        hub_double.usage[DAY.isoformat()] = [row(business.id, s3_bytes=1)]
        collect()

        with django_capture_on_commit_callbacks(execute=True):
            collect()

        assert channels(notified, events.BUSINESS_USAGE_COLLECTED) == set()

    def test_a_new_day_re_runs_the_page_and_the_usage(self):
        assert {
            "hubs.business.get",
            "hubs.usage.get",
            "hubs.usage.series",
        } <= live_registry.affected([events.BUSINESS_USAGE_COLLECTED])
        assert "hubs.business.list" not in live_registry.affected(
            [events.BUSINESS_USAGE_COLLECTED]
        )


class TestOnlyThePlatformRecordsIt:
    def test_an_account_cannot_record_usage(self, business, owner):
        with pytest.raises(PermissionDenied) as refused:
            services.usage_record(
                ctx_for(owner),
                UsageRecordIn(
                    id=business.id,
                    day=DAY,
                    s3_bytes=1,
                    db_bytes=1,
                    active_users_1d=0,
                    active_users_30d=0,
                ),
            )

        assert refused.value.code == "internal_command"
        assert not HubUsageDaily.objects.exists()
