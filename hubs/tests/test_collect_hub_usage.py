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
import logging
from datetime import UTC, date, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.models import OutboxEvent

from hubs import events, queries, services
from hubs.models import HubUsageDaily
from hubs.schemas import UsagePruneIn, UsageRecordIn, UsageSeriesIn
from hubs.tests.conftest import create_business, ctx_for
from hubs.tests.test_live import channels, notified  # noqa: F401 - the fixture of the notifications
from hubs.tests.test_reconcile_hub_states import run

pytestmark = pytest.mark.django_db

#: The advisory lock a run holds (the SaaS's convention, as ``push_hub_snapshots``).
LOCK_KEY = "hashtext('erplora.saas.collect_hub_usage')"
#: A recent day, never a fixed one: a pass ends by forgetting what is past the retention, so a fixed day would go too
#: once it is 400 days old, and these tests with it.
DAY = datetime.now(UTC).date() - timedelta(days=20)
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
        assert call.path == f"/internal/usage?day={DAY}" and call.signed_v2
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
            f"/internal/usage?day={DAY}",
            f"/internal/usage?day={DAY}&cursor=2",
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

    def test_a_business_the_hub_did_not_measure_is_left_out_and_the_run_passes(
        self, business, owner, make_user, hub_double
    ):
        """HUBS-F21/F22 (PLAN-DB round 2026-10-30, proposal (j)): the nightly measure skips a hub still on the shared
        database of control, so its row is not in the answer. The pass records the rest and ends well; the business
        left out keeps «no data yet» (or its last day), never the size of the control database."""
        measured = create_business(make_user("lola@example.com"), name="Café Lola")
        hub_double.usage[DAY.isoformat()] = [row(measured.id, db_bytes=7 * GIB)]

        output = collect()

        assert figures(measured)[1] == 7 * GIB
        assert not HubUsageDaily.objects.filter(hub=business).exists()
        assert "recorded=1" in output and "invalid=0" in output and "failed=0" in output

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
            {"day": (DAY - timedelta(days=1)).isoformat(), "hubs": [row(business.id)], "next_cursor": None},
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


#: What the Hub measures during the day and adds to each row (hub#603, PLAN-SAAS §28, BASE-F40); for the admin only.
DAY_FIGURES = ("requests", "peak_connections", "busy_requests")


def day_figures(hub):
    sample = HubUsageDaily.objects.get(hub=hub, day=DAY)
    return tuple(getattr(sample, name) for name in DAY_FIGURES)


class TestTheFiguresOfTheDay:
    """The Hub is deployed first, so a row may come without them, and what nobody measured is never a 0."""

    def test_they_are_kept_as_the_hub_measured_them(self, business, hub_double):
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, requests=1200, peak_connections=5, busy_requests=2)
        ]

        output = collect()

        assert day_figures(business) == (1200, 5, 2)
        assert "recorded=1" in output

    def test_a_row_without_them_keeps_them_unknown_not_zero(self, business, hub_double):
        """The row of a Hub that does not send them yet."""
        hub_double.usage[DAY.isoformat()] = [row(business.id, s3_bytes=7)]

        output = collect()

        assert day_figures(business) == (None, None, None)
        assert figures(business)[0] == 7
        assert "recorded=1" in output and "invalid=0" in output

    def test_a_row_saying_not_measured_keeps_them_unknown(self, business, hub_double):
        """A day before the Hub started measuring them, or one of them it could not measure."""
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, requests=None, peak_connections=3, busy_requests=None)
        ]

        output = collect()

        assert day_figures(business) == (None, 3, None)
        assert "invalid=0" in output

    def test_a_measured_zero_stays_a_zero(self, business, hub_double):
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, requests=0, peak_connections=0, busy_requests=0)
        ]

        collect()

        assert day_figures(business) == (0, 0, 0)

    def test_a_figure_this_saas_does_not_know_never_breaks_the_row(
        self, business, hub_double
    ):
        """The Hub may add figures before the SaaS reads them: that is why it can be deployed first."""
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, s3_bytes=7, a_figure_of_tomorrow=3)
        ]

        output = collect()

        assert figures(business)[0] == 7
        assert "recorded=1" in output and "invalid=0" in output

    @pytest.mark.parametrize(
        ("name", "biggest"),
        [
            ("requests", 2**63 - 1),
            ("peak_connections", 2**31 - 1),
            ("busy_requests", 2**63 - 1),
        ],
    )
    def test_the_contract_stops_where_the_column_does(
        self, business, hub_double, name, biggest
    ):
        """Beyond it the row is off the contract (``invalid``), never a crash of the database (``failed``)."""
        hub_double.usage[DAY.isoformat()] = [row(business.id, **{name: biggest})]

        collect()

        assert getattr(HubUsageDaily.objects.get(hub=business, day=DAY), name) == biggest

        hub_double.usage[DAY.isoformat()] = [row(business.id, **{name: biggest + 1})]

        with pytest.raises(CommandError) as failed:
            collect()

        assert "invalid=1" in str(failed.value) and "failed=0" in str(failed.value)

    @pytest.mark.parametrize("name", DAY_FIGURES)
    @pytest.mark.parametrize("broken", [-1, "many", 1.5])
    def test_a_broken_figure_is_a_broken_row(self, business, hub_double, name, broken):
        hub_double.usage[DAY.isoformat()] = [row(business.id, **{name: broken})]

        with pytest.raises(CommandError) as failed:
            collect()

        assert "invalid=1" in str(failed.value)
        assert not HubUsageDaily.objects.filter(hub=business).exists()


class TestCollectingADayAgainWithTheFiguresOfTheDay:
    """HUBS-F22: a day collected again is replaced only if it changed, and these figures are part of it."""

    MEASURED = {"requests": 1200, "peak_connections": 5, "busy_requests": 2}

    @pytest.mark.parametrize("name", DAY_FIGURES)
    def test_only_one_of_them_changed_replaces_the_day_and_tells_the_page(
        self,
        business,
        owner,
        hub_double,
        notified,
        django_capture_on_commit_callbacks,  # noqa: F811
        name,
    ):
        hub_double.usage[DAY.isoformat()] = [row(business.id, **self.MEASURED)]
        collect()
        first = HubUsageDaily.objects.get(hub=business, day=DAY).collected_at
        notified.clear()
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, **{**self.MEASURED, name: self.MEASURED[name] + 1})
        ]

        with django_capture_on_commit_callbacks(execute=True):
            output = collect()

        sample = HubUsageDaily.objects.get(hub=business, day=DAY)
        assert getattr(sample, name) == self.MEASURED[name] + 1
        assert sample.collected_at > first
        assert "recorded=1" in output and "unchanged=0" in output
        assert channels(notified, events.BUSINESS_USAGE_COLLECTED) == {str(owner.pk)}

    def test_the_same_ones_again_write_nothing_and_tell_nobody(
        self,
        business,
        hub_double,
        notified,
        django_capture_on_commit_callbacks,  # noqa: F811
    ):
        hub_double.usage[DAY.isoformat()] = [row(business.id, **self.MEASURED)]
        collect()
        first = HubUsageDaily.objects.get(hub=business, day=DAY).collected_at
        notified.clear()

        with django_capture_on_commit_callbacks(execute=True):
            output = collect()

        assert HubUsageDaily.objects.get(hub=business, day=DAY).collected_at == first
        assert "unchanged=1" in output and "recorded=0" in output
        assert channels(notified, events.BUSINESS_USAGE_COLLECTED) == set()

    def test_a_day_kept_without_them_takes_them_when_collected_again(
        self, business, hub_double
    ):
        """The backfill (``--day``) of a night collected before the Hub sent them."""
        hub_double.usage[DAY.isoformat()] = [row(business.id)]
        collect()
        hub_double.usage[DAY.isoformat()] = [row(business.id, **self.MEASURED)]

        output = collect()

        assert day_figures(business) == (1200, 5, 2)
        assert "recorded=1" in output

    def test_a_zero_is_not_the_same_as_not_measured(self, business, hub_double):
        hub_double.usage[DAY.isoformat()] = [row(business.id)]
        collect()
        hub_double.usage[DAY.isoformat()] = [
            row(business.id, requests=0, peak_connections=0, busy_requests=0)
        ]

        output = collect()

        assert day_figures(business) == (0, 0, 0)
        assert "recorded=1" in output


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


def days_ago(days: int) -> date:
    return datetime.now(UTC).date() - timedelta(days=days)


def keep_day(hub, day: date) -> None:
    HubUsageDaily.objects.create(hub=hub, day=day, s3_bytes=1, db_bytes=1, active_users_1d=0, active_users_30d=0)


def days_kept(hub) -> set[date]:
    return set(HubUsageDaily.objects.filter(hub=hub).values_list("day", flat=True))


def collect_saying():
    """The run's error, if any, and all it said before it: ``run`` loses what was written when the command fails."""
    out = StringIO()
    try:
        call_command("collect_hub_usage", "--day", DAY.isoformat(), stdout=out)
    except CommandError as failed:
        return str(failed), out.getvalue()
    return "", out.getvalue()


def prune_breaks(monkeypatch) -> None:
    def broken(ctx, data):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(services, "usage_prune", broken)


class TestAPassForgetsWhatIsPastTheRetention:
    """HUBS-F22; PLAN-SAAS §1.1, «Limpiezas y podas diarias», and §27: 400 days, as the old product."""

    def test_the_day_400_stays_and_the_day_401_goes(self, business, hub_double):
        keep_day(business, days_ago(30))
        keep_day(business, days_ago(400))
        keep_day(business, days_ago(401))

        output = collect()

        assert days_kept(business) == {days_ago(30), days_ago(400)}
        assert f"pruned=1 before={days_ago(400)}" in output

    def test_it_forgets_the_old_days_of_every_business(self, owner, plans, make_user, hub_double):
        hubs = [create_business(owner), create_business(make_user("lola@example.com"), name="Café Lola")]
        for hub in hubs:
            keep_day(hub, days_ago(401))

        output = collect()

        assert not HubUsageDaily.objects.exists()
        assert "pruned=2" in output

    def test_the_longest_window_of_a_series_is_still_whole(self, business, owner, hub_double):
        """``hubs.usage.series`` reads up to 365 days: no prune can take a day of that window."""
        first_read = days_ago(1) - timedelta(days=364)
        keep_day(business, first_read)
        keep_day(business, days_ago(1))
        window = UsageSeriesIn(business_id=business.id, days=365)
        before = [point.day for point in queries.usage_series(ctx_for(owner), window).points]

        collect()

        assert before == [first_read, days_ago(1)]
        assert [point.day for point in queries.usage_series(ctx_for(owner), window).points] == before

    def test_the_retention_outlasts_whatever_a_series_may_read(self):
        """Holds the two numbers together: a longer window has to raise the retention with it."""
        longest = UsageSeriesIn.model_json_schema()["properties"]["days"]["maximum"]

        assert services.USAGE_RETENTION_DAYS > longest

    def test_a_day_collected_by_hand_past_the_retention_goes_at_the_end_of_its_pass(self, business, hub_double):
        old = days_ago(401)
        hub_double.usage[old.isoformat()] = [row(business.id)]

        output = run("collect_hub_usage", "--day", old.isoformat())

        assert "recorded=1" in output and "pruned=1" in output
        assert not HubUsageDaily.objects.exists()

    def test_a_run_that_did_not_take_the_lock_forgets_nothing(self, business, hub_double, other_session):
        keep_day(business, days_ago(401))
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

        output = collect()

        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert "already running" in output
        assert days_kept(business) == {days_ago(401)}


class TestAPruneThatFailsNeverEatsTheCollection:
    def test_what_was_collected_stays_said_and_the_run_ends_with_an_error(
        self, business, hub_double, monkeypatch, caplog
    ):
        hub_double.usage[DAY.isoformat()] = [row(business.id, s3_bytes=7)]
        prune_breaks(monkeypatch)

        with caplog.at_level(logging.ERROR, logger="hubs.services"):
            failed, said = collect_saying()

        assert figures(business)[0] == 7
        assert "recorded=1" in said
        assert "did not forget" in failed and "did not get every business" not in failed
        assert "hubs.usage.prune_failed" in caplog.text

    def test_the_collection_that_failed_is_still_the_one_that_says_so(self, business, offline_hub, monkeypatch):
        prune_breaks(monkeypatch)

        failed, _ = collect_saying()

        assert "unreachable=1" in failed and "did not get every business" in failed
        assert "did not forget" in failed

    def test_the_hub_away_does_not_stop_the_prune(self, business, offline_hub):
        keep_day(business, days_ago(401))

        failed, said = collect_saying()

        assert "unreachable=1" in failed and "did not forget" not in failed
        assert "pruned=1" in said
        assert not HubUsageDaily.objects.exists()


class TestThePruneOperation:
    def test_only_the_platform_runs_it(self, business, owner):
        keep_day(business, days_ago(401))

        with pytest.raises(PermissionDenied) as refused:
            services.usage_prune(ctx_for(owner), UsagePruneIn())

        assert refused.value.code == "internal_command"
        assert days_kept(business) == {days_ago(401)}

    def test_what_it_forgets_leaves_its_event(self, business, hub_double):
        keep_day(business, days_ago(401))

        collect()

        (event,) = OutboxEvent.objects.filter(name=events.USAGE_PRUNED)
        assert event.payload == {"before": days_ago(400).isoformat(), "deleted": 1}

    def test_with_nothing_to_forget_it_leaves_no_event(self, business, hub_double):
        keep_day(business, days_ago(400))

        output = collect()

        assert "pruned=0" in output
        assert not OutboxEvent.objects.filter(name="hubs.usage.pruned").exists()
