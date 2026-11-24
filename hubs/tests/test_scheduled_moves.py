"""The maintenance the Hub schedules for a business's night: at each round the worker asks the Hub whether the move of
each ready business to another server is scheduled (``move_scheduled_for`` of its signed status poll, an instant in
UTC), and the list and the page of the business say when it starts, until the move starts or is cancelled."""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import PermissionDenied
from live.models import OutboxEvent

from hubs import events
from hubs.models import Hub
from hubs.queries import businesses
from hubs.schemas.businesses import BusinessListIn
from hubs.schemas.common import ByIdIn
from hubs.schemas.hub_callbacks import HubScheduledMoveIn
from hubs.services import hub_callbacks, scheduled_moves
from hubs.tests.conftest import create_business, ctx_for

pytestmark = pytest.mark.django_db

#: The advisory lock a pass holds (the SaaS's convention, as ``reconcile_hub_states``).
LOCK_KEY = "hashtext('erplora.saas.check_scheduled_moves')"


def tonight():
    """An instant of the coming night, as the Hub writes it: UTC with a ``Z``, to the second."""
    start = (timezone.now() + timedelta(hours=10)).replace(microsecond=0)
    return start, start.strftime("%Y-%m-%dT%H:%M:%SZ")


def ready(hub, hub_double, status=Hub.Status.ACTIVE, **answer):
    """A business the Hub has ready, whose signed poll answers ``answer`` besides its status."""
    Hub.objects.filter(pk=hub.pk).update(status=status, ready_at=timezone.now() - timedelta(days=3), pending_hub_call="")
    hub_double.registry[str(hub.id)] = {"status": "ready", **answer}
    return hub


@pytest.fixture
def several(settings):
    """Room for more than one free business per account."""
    settings.FREE_HUBS_PER_ACCOUNT = 10


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)


def shown(owner, hub):
    """What the list and the page of the business say of its scheduled move."""
    row = next(row for row in businesses.business_list(ctx_for(owner), BusinessListIn()).rows if row.id == hub.id)
    return row.move_scheduled_for, businesses.business_get(ctx_for(owner), ByIdIn(id=hub.id)).move_scheduled_for


class TestThePass:
    def test_a_move_for_tonight_is_saved_and_said_in_the_list_and_the_page(self, business, owner, hub_double):
        start, written = tonight()
        ready(business, hub_double, move_scheduled_for=written)
        version = fresh(business).state_version

        counts = scheduled_moves.check_scheduled_moves()

        assert (counts["checked"], counts["scheduled"]) == (1, 1)
        assert fresh(business).move_scheduled_for == start
        assert fresh(business).state_version == version
        assert shown(owner, business) == (start, start)

    def test_the_row_carries_the_time_zone_the_moment_is_said_in(self, business, owner, hub_double):
        Hub.objects.filter(pk=business.pk).update(timezone="Atlantic/Canary")

        row = businesses.business_list(ctx_for(owner), BusinessListIn()).rows[0]

        assert row.timezone == "Atlantic/Canary"

    def test_once_the_hub_says_none_it_is_no_longer_said(self, business, owner, hub_double):
        """The move started, or the staff cancelled it."""
        _, written = tonight()
        ready(business, hub_double, move_scheduled_for=written)
        scheduled_moves.check_scheduled_moves()

        hub_double.registry[str(business.id)]["move_scheduled_for"] = None
        counts = scheduled_moves.check_scheduled_moves()

        assert (counts["checked"], counts["scheduled"]) == (1, 0)
        assert fresh(business).move_scheduled_for is None
        assert shown(owner, business) == (None, None)

    def test_a_hub_that_does_not_say_it_has_none_to_say(self, business, owner, hub_double):
        """The field is optional: a Hub of before answers only its status."""
        ready(business, hub_double)
        Hub.objects.filter(pk=business.pk).update(move_scheduled_for=tonight()[0])

        scheduled_moves.check_scheduled_moves()

        assert fresh(business).move_scheduled_for is None

    @pytest.mark.usefixtures("several")
    def test_only_the_ready_businesses_that_still_live_are_asked(self, business, owner, hub_double):
        for status in (Hub.Status.ACTIVE, Hub.Status.PAST_DUE, Hub.Status.SUSPENDED):
            ready(create_business(owner, name=f"Bar {status}"), hub_double, status=status)
        ready(create_business(owner, name="Bar deleted"), hub_double, status=Hub.Status.DELETING)
        hub_double.calls.clear()

        counts = scheduled_moves.check_scheduled_moves()

        asked = {call.path for call in hub_double.calls_to("GET")}
        assert counts["checked"] == 3
        assert f"/internal/hubs/{business.id}" not in asked
        assert len(asked) == 3

    def test_the_hub_away_keeps_what_it_said_and_fails_the_pass(self, business, hub_double):
        start, written = tonight()
        ready(business, hub_double, move_scheduled_for=written)
        scheduled_moves.check_scheduled_moves()
        hub_double.answer("GET", rf"^/internal/hubs/{business.id}$", 503, {"error": {"code": "unavailable"}})

        counts = scheduled_moves.check_scheduled_moves()

        assert counts["unreachable"] == 1
        assert scheduled_moves.run_failed(counts) is True
        assert fresh(business).move_scheduled_for == start

    @pytest.mark.usefixtures("several")
    def test_an_answer_off_the_contract_never_stops_the_others(self, business, owner, hub_double):
        start, written = tonight()
        ready(business, hub_double, move_scheduled_for="not an instant")
        other = ready(create_business(owner, name="Bar Paco"), hub_double, move_scheduled_for=written)

        counts = scheduled_moves.check_scheduled_moves()

        assert (counts["failed"], counts["scheduled"]) == (1, 1)
        assert scheduled_moves.run_failed(counts) is True
        assert fresh(other).move_scheduled_for == start

    def test_a_pass_with_nothing_wrong_does_not_fail(self, business, hub_double):
        ready(business, hub_double, move_scheduled_for=tonight()[1])

        assert scheduled_moves.run_failed(scheduled_moves.check_scheduled_moves()) is False

    @pytest.mark.usefixtures("several")
    def test_go_on_ends_it_before_the_next_business(self, business, owner, hub_double):
        ready(business, hub_double)
        ready(create_business(owner, name="Bar Paco"), hub_double)
        hub_double.calls.clear()

        counts = scheduled_moves.check_scheduled_moves(go_on=lambda: False)

        assert (counts["checked"], counts["cut_short"]) == (0, 1)
        assert hub_double.calls == []

    @pytest.mark.usefixtures("several")
    def test_a_pass_cut_short_asks_first_about_the_moves_it_knows(self, business, owner, hub_double):
        """Their start or their cancellation is what must not wait for another round."""
        ready(create_business(owner, name="Bar Alfa"), hub_double)
        known = ready(create_business(owner, name="Bar Zeta"), hub_double)
        Hub.objects.filter(pk=known.pk).update(move_scheduled_for=tonight()[0])
        hub_double.calls.clear()
        allowed = iter([True, False])

        scheduled_moves.check_scheduled_moves(go_on=lambda: next(allowed))

        assert [call.path for call in hub_double.calls_to("GET")] == [f"/internal/hubs/{known.id}"]
        assert fresh(known).move_scheduled_for is None

    def test_a_second_pass_does_nothing_while_one_holds_the_lock(self, business, hub_double, other_session):
        ready(business, hub_double)
        hub_double.calls.clear()
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            assert scheduled_moves.check_scheduled_moves_exclusively() is None
        finally:
            other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert hub_double.calls == []
        assert scheduled_moves.check_scheduled_moves_exclusively()["checked"] == 1


class TestWhatIsSaid:
    def test_an_instant_already_reached_is_not_said(self, business, owner):
        """From its start the move is under way: the business is in maintenance, no longer about to be."""
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.ACTIVE, move_scheduled_for=timezone.now() - timedelta(minutes=1)
        )

        assert shown(owner, business) == (None, None)


class TestTheRecord:
    def system(self, hub):
        return hub_callbacks.system_ctx_for(hub.id)

    def test_a_change_tells_the_owners_live_pages_and_the_same_answer_records_nothing(self, business, owner):
        start, _ = tonight()

        hub_callbacks.business_record_scheduled_move(
            self.system(business), HubScheduledMoveIn(id=business.id, move_scheduled_for=start)
        )
        hub_callbacks.business_record_scheduled_move(
            self.system(business), HubScheduledMoveIn(id=business.id, move_scheduled_for=start)
        )

        told = OutboxEvent.objects.filter(name=events.BUSINESS_MOVE_SCHEDULED_CHANGED)
        assert told.count() == 1
        assert told.get().scope_key == str(owner.pk)

    def test_only_the_platform_records_it(self, business, owner):
        with pytest.raises(PermissionDenied):
            hub_callbacks.business_record_scheduled_move(
                ctx_for(owner), HubScheduledMoveIn(id=business.id, move_scheduled_for=tonight()[0])
            )
