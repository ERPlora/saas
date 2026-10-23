"""ASSISTANT-F18 (ASSISTANT-G51, G50, G05, G29) · Count each business's messages against its plan, and a demo's
against its own few: ``assistant.message.claim`` takes one before the model is called, ``assistant.message.release``
gives it back when the turn failed before answering, ``assistant.usage.record`` adds the tokens and the cost, and
``assistant.usage.show`` (the ``usage`` door) says how many are left and when they come back.

The allowance is the plan's (``Plan.assistant_messages_per_month``, PLAN-SAAS §3.6; 0 = none, never «unlimited»; no
packs: more messages is a plan up), of the plan whose rights the business has now (its trial's while it lasts). A
demo has 10 for its whole life (SAAS_ASSISTANT-F11, saas#2599). Cases of the old product's ``test_quota_signal.py``,
``test_demo_message_limit.py`` and ``test_stateless_bridge.py::TestMeteringPreserved``; the old one checked and
counted apart, so two turns could both pass the last message (SAAS_ASSISTANT-F11): here one ``UPDATE … WHERE
messages < limit`` decides.
"""

import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone
from live.outbox import OutboxEvent

from assistant import queries, services
from assistant.models import AssistantUsage
from assistant.schemas import Caller, MessageReleaseIn, UsageRecordIn
from assistant.services import platform_context
from assistant.tests.conftest import on_plan
from assistant.tests.doors import door
from hubs.models import Plan, Subscription

pytestmark = pytest.mark.django_db


def caller_of(hub) -> Caller:
    return Caller(hub_id=hub.id, slug=hub.slug)


DEMO = Caller(demo="demo-1a2b3c4d", slug="demo-1a2b3c4d")


def claim(caller):
    return services.message_claim(platform_context(), caller)


def used(caller) -> int:
    return queries.usage_show(platform_context(), caller).used


class TestTheAllowanceIsThePlans:
    def test_a_business_on_free_gets_its_thirty_messages(self, business):
        claimed = claim(caller_of(business))

        assert claimed.claimed is True
        assert (claimed.used, claimed.limit, claimed.demo) == (1, 30, False)

    def test_the_message_past_the_allowance_is_refused_and_not_counted(self, business):
        AssistantUsage.objects.create(hub=business, month=queries.month_of(timezone.now()), messages=30)

        claimed = claim(caller_of(business))

        assert claimed.claimed is False
        assert (claimed.used, claimed.limit) == (30, 30)
        assert used(caller_of(business)) == 30

    def test_a_plan_with_no_messages_gets_none(self, business):
        on_plan(business, "free", assistant_messages_per_month=0)

        claimed = claim(caller_of(business))

        assert claimed.claimed is False
        assert (claimed.used, claimed.limit) == (0, 0)

    def test_a_plan_up_gives_its_bigger_allowance_at_once(self, business):
        AssistantUsage.objects.create(hub=business, month=queries.month_of(timezone.now()), messages=30)
        on_plan(business, "standard")

        claimed = claim(caller_of(business))

        assert claimed.claimed is True
        assert (claimed.used, claimed.limit) == (31, 600)

    def test_a_trial_gives_the_trial_plans_allowance_while_it_lasts(self, business):
        Subscription.objects.filter(hub=business).update(
            trial_plan=Plan.objects.get(slug="starter"), trial_end=timezone.now() + timedelta(days=3)
        )

        assert claim(caller_of(business)).limit == 300

    def test_a_trial_that_ended_gives_the_plans_own(self, business):
        Subscription.objects.filter(hub=business).update(
            trial_plan=Plan.objects.get(slug="starter"), trial_end=timezone.now() - timedelta(minutes=1)
        )

        assert claim(caller_of(business)).limit == 30

    def test_one_business_never_spends_another_ones_messages(self, business, make_user):
        from hubs.models import Hub
        from hubs.tests.conftest import create_business

        other = create_business(make_user("pepe@example.com"), name="Bar Pepe")
        Hub.objects.filter(pk=other.pk).update(status=Hub.Status.ACTIVE)

        for _ in range(3):
            claim(caller_of(business))

        assert used(caller_of(business)) == 3
        assert used(caller_of(other)) == 0


class TestTheMonth:
    def test_the_messages_come_back_on_the_first_of_the_next_month_utc(self):
        assert queries.resets_at(date(2026, 10, 1)) == datetime(2026, 11, 1, tzinfo=UTC)

    def test_december_rolls_the_year(self):
        assert queries.resets_at(date(2026, 12, 1)) == datetime(2027, 1, 1, tzinfo=UTC)

    def test_the_month_is_utcs_not_the_servers(self):
        late_in_madrid = datetime(2026, 11, 1, 0, 30, tzinfo=UTC) - timedelta(hours=1)

        assert queries.month_of(late_in_madrid) == date(2026, 10, 1)

    def test_last_months_messages_do_not_count_this_month(self, business):
        last_month = queries.month_of(timezone.now() - timedelta(days=40))
        AssistantUsage.objects.create(hub=business, month=last_month, messages=30)

        claimed = claim(caller_of(business))

        assert (claimed.claimed, claimed.used) == (True, 1)

    def test_the_usage_door_says_when_they_come_back(self, internal, business):
        claim(caller_of(business))

        response = door(Client(), "/internal/assistant/usage", {"hub": business.slug})

        expected = queries.resets_at(queries.month_of(timezone.now())).isoformat().replace("+00:00", "Z")
        assert response.json() == {"used": 1, "limit": 30, "resets_at": expected, "demo": False}


class TestTheDemo:
    def test_saas_2599_a_demo_has_ten_messages_for_its_whole_life(self):
        answers = [claim(DEMO).claimed for _ in range(11)]

        assert answers == [True] * 10 + [False]
        shown = queries.usage_show(platform_context(), DEMO)
        assert (shown.used, shown.limit, shown.resets_at, shown.demo) == (10, 10, None, True)

    def test_saas_2599_the_demos_count_spans_a_new_month(self, monkeypatch):
        for _ in range(9):
            claim(DEMO)
        next_month = timezone.now() + timedelta(days=40)
        monkeypatch.setattr(timezone, "now", lambda: next_month)

        assert [claim(DEMO).claimed for _ in range(2)] == [True, False]

    def test_another_demo_starts_with_its_own_ten(self):
        for _ in range(10):
            claim(DEMO)

        assert claim(Caller(demo="demo-ffffffff", slug="demo-ffffffff")).claimed is True

    def test_the_rows_of_demos_gone_for_a_day_are_forgotten_when_a_new_demo_starts(self):
        claim(DEMO)
        AssistantUsage.objects.filter(demo=DEMO.demo).update(created_at=timezone.now() - timedelta(days=2))

        claim(Caller(demo="demo-ffffffff", slug="demo-ffffffff"))

        assert list(AssistantUsage.objects.values_list("demo", flat=True)) == ["demo-ffffffff"]


class TestGivingBackAndRecording:
    def test_a_message_given_back_is_free_again(self, business):
        claimed = claim(caller_of(business))

        services.message_release(platform_context(), MessageReleaseIn(caller=caller_of(business), month=claimed.month))

        assert used(caller_of(business)) == 0

    def test_giving_back_never_goes_below_zero(self, business):
        month = queries.month_of(timezone.now())

        services.message_release(platform_context(), MessageReleaseIn(caller=caller_of(business), month=month))

        assert used(caller_of(business)) == 0

    def test_a_message_given_back_after_the_month_turned_goes_back_to_its_month(self, business):
        last_month = queries.month_of(timezone.now() - timedelta(days=40))
        AssistantUsage.objects.create(hub=business, month=last_month, messages=5)
        claim(caller_of(business))

        services.message_release(platform_context(), MessageReleaseIn(caller=caller_of(business), month=last_month))

        assert AssistantUsage.objects.get(hub=business, month=last_month).messages == 4
        assert used(caller_of(business)) == 1

    def test_the_tokens_and_the_cost_add_up_without_counting_a_message(self, business):
        record = UsageRecordIn(caller=caller_of(business), tokens_input=1000, tokens_output=200, cost_usd=Decimal("0.0036"))
        services.usage_record(platform_context(), record)
        services.usage_record(platform_context(), record)

        row = AssistantUsage.objects.get(hub=business)
        assert (row.messages, row.tokens_input, row.tokens_output, row.cost_usd) == (0, 2000, 400, Decimal("0.0072"))

    def test_each_write_says_so_in_the_outbox_with_numbers_only(self, business):
        claimed = claim(caller_of(business))
        services.usage_record(platform_context(), UsageRecordIn(caller=caller_of(business), tokens_input=10))
        services.message_release(platform_context(), MessageReleaseIn(caller=caller_of(business), month=claimed.month))

        recorded = list(
            OutboxEvent.objects.filter(name__startswith="assistant.").order_by("created_at").values_list("name", "payload")
        )
        assert [name for name, _ in recorded] == [
            "assistant.message.claimed",
            "assistant.usage.recorded",
            "assistant.message.released",
        ]
        assert recorded[0][1] == {"hub": str(business.id), "demo": "", "used": 1, "limit": 30}

    def test_only_the_platform_counts(self, ai_admin, business):
        from live.errors import PermissionDenied

        from assistant.tests.conftest import staff_ctx

        with pytest.raises(PermissionDenied):
            services.message_claim(staff_ctx(ai_admin), caller_of(business))


#: The turns that race for the last message of the month.
RIVALS = 4


def waiting_on_a_lock(count: int, *, within: float) -> bool:
    """Whether ``count`` other sessions of this test database wait on a lock, before ``within`` seconds."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0] >= count:
                return True
        time.sleep(0.05)
    return False


@pytest.mark.django_db(transaction=True)
def test_turns_at_once_cannot_pass_the_last_message_together(make_user):
    """With one message left, four claims at once: one passes, three are refused. A claim that read the count and
    wrote it apart would let the four through (SAAS_ASSISTANT-F11 «dos turnos a la vez»)."""
    from django.db import transaction

    from hubs.models import Hub
    from hubs.tests.conftest import create_business, put_the_catalogue_back

    put_the_catalogue_back()
    hub = create_business(make_user("race@example.com"))
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ACTIVE)
    month = queries.month_of(timezone.now())
    AssistantUsage.objects.create(hub=hub, month=month, messages=29)
    held, release = threading.Event(), threading.Event()
    answers = []

    def hold_the_counter():
        try:
            with transaction.atomic():
                AssistantUsage.objects.select_for_update().get(hub=hub, month=month)
                held.set()
                release.wait(10)
        finally:
            connection.close()

    def one():
        try:
            answers.append(claim(caller_of(hub)).claimed)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_counter)
    holder.start()
    assert held.wait(5)
    rivals = [threading.Thread(target=one) for _ in range(RIVALS)]
    for thread in rivals:
        thread.start()
    assert waiting_on_a_lock(RIVALS, within=30), "the claims never met at the month's counter"
    release.set()
    for thread in (holder, *rivals):
        thread.join(15)

    assert sorted(answers) == [False] * (RIVALS - 1) + [True]
    assert AssistantUsage.objects.get(hub=hub, month=month).messages == 30
