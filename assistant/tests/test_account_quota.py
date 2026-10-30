"""ASSISTANT-F27 · Count an account's own messages of the assistant of erplora.com's panel (plan 2026-10-30, §4,
PLAN-SAAS §23): a fixed allowance per account and calendar month (UTC), ``ASSISTANT_ACCOUNT_MESSAGES`` (30), apart
from the plan allowance of each of its businesses. The same claim, release and record as a business's
(``assistant.message.claim`` / ``.release`` / ``assistant.usage.record``), on a row of its own per (account, month).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from live.outbox import OutboxEvent
from pydantic import ValidationError

from assistant import queries, services, turn
from assistant.models import AssistantUsage
from assistant.schemas import Caller, MessageReleaseIn, UsageRecordIn
from assistant.services import platform_context

pytestmark = pytest.mark.django_db


def account_of(user) -> Caller:
    return Caller(user_id=user.pk)


def claim(caller):
    return services.message_claim(platform_context(), caller)


def this_month() -> date:
    return queries.month_of(timezone.now())


@pytest.fixture
def account(owner):
    return owner


class TestTheAccountsAllowance:
    def test_an_account_gets_thirty_messages_a_month_that_come_back_on_the_first(self, account):
        claimed = claim(account_of(account))

        assert claimed.claimed is True
        assert (claimed.used, claimed.limit, claimed.demo) == (1, 30, False)
        assert claimed.resets_at == queries.resets_at(this_month())
        assert AssistantUsage.objects.get(user=account).month == this_month()

    def test_the_thirty_first_message_is_refused_and_not_counted(self, account):
        AssistantUsage.objects.create(user=account, month=this_month(), messages=30)

        claimed = claim(account_of(account))

        assert (claimed.claimed, claimed.used, claimed.limit) == (False, 30, 30)
        assert AssistantUsage.objects.get(user=account).messages == 30

    def test_the_allowance_is_the_settings(self, account, settings):
        settings.ASSISTANT_ACCOUNT_MESSAGES = 2

        assert [claim(account_of(account)).claimed for _ in range(3)] == [True, True, False]

    def test_last_months_messages_do_not_count_this_month(self, account):
        last_month = queries.month_of(timezone.now() - timedelta(days=40))
        AssistantUsage.objects.create(user=account, month=last_month, messages=30)

        claimed = claim(account_of(account))

        assert (claimed.claimed, claimed.used) == (True, 1)
        assert AssistantUsage.objects.filter(user=account).count() == 2

    def test_the_month_turns_on_the_first_at_midnight_utc(self, account, monkeypatch):
        last_second = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
        monkeypatch.setattr(timezone, "now", lambda: last_second)
        for _ in range(30):
            claim(account_of(account))
        assert claim(account_of(account)).claimed is False

        monkeypatch.setattr(timezone, "now", lambda: last_second + timedelta(seconds=1))
        claimed = claim(account_of(account))

        assert (claimed.claimed, claimed.used, claimed.month) == (True, 1, date(2026, 11, 1))
        assert claimed.resets_at == datetime(2026, 12, 1, tzinfo=UTC)

    def test_the_usage_shows_the_accounts_month(self, account):
        claim(account_of(account))
        claim(account_of(account))

        shown = queries.usage_show(platform_context(), account_of(account))

        assert (shown.used, shown.limit, shown.demo) == (2, 30, False)
        assert shown.resets_at == queries.resets_at(this_month())

    def test_an_account_never_used_shows_none_spent(self, account):
        shown = queries.usage_show(platform_context(), account_of(account))

        assert (shown.used, shown.limit) == (0, 30)


class TestAnAccountAndItsBusinessesNeverShare:
    def test_a_business_and_its_owners_account_count_apart(self, account, business):
        claim(account_of(account))
        claim(Caller(hub_id=business.id, slug=business.slug))
        claim(Caller(hub_id=business.id, slug=business.slug))

        assert AssistantUsage.objects.get(user=account, month=this_month()).messages == 1
        assert AssistantUsage.objects.get(hub=business, month=this_month()).messages == 2
        assert AssistantUsage.objects.get(user=account).hub_id is None

    def test_a_spent_business_does_not_spend_its_owners_account(self, account, business):
        AssistantUsage.objects.create(hub=business, month=this_month(), messages=30)

        assert claim(account_of(account)).claimed is True

    def test_one_account_never_spends_anothers(self, account, make_user):
        other = make_user("other@example.com")
        AssistantUsage.objects.create(user=other, month=this_month(), messages=30)

        assert claim(account_of(account)).claimed is True

    def test_a_new_demo_does_not_forget_an_accounts_row(self, account):
        claim(account_of(account))
        AssistantUsage.objects.filter(user=account).update(created_at=timezone.now() - timedelta(days=2))

        claim(Caller(demo="demo-1a2b3c4d", slug="demo-1a2b3c4d"))

        assert AssistantUsage.objects.get(user=account).messages == 1


class TestGivingBackAndRecording:
    def test_a_message_given_back_is_free_again_in_its_month(self, account):
        claimed = claim(account_of(account))

        shown = services.message_release(
            platform_context(), MessageReleaseIn(caller=account_of(account), month=claimed.month)
        )

        assert shown.used == 0
        assert AssistantUsage.objects.get(user=account).messages == 0

    def test_giving_back_touches_only_that_accounts_month(self, account, business, make_user):
        other = make_user("other@example.com")
        AssistantUsage.objects.create(user=other, month=this_month(), messages=5)
        AssistantUsage.objects.create(hub=business, month=this_month(), messages=5)
        last_month = queries.month_of(timezone.now() - timedelta(days=40))
        AssistantUsage.objects.create(user=account, month=last_month, messages=5)
        claimed = claim(account_of(account))

        services.message_release(platform_context(), MessageReleaseIn(caller=account_of(account), month=claimed.month))

        assert AssistantUsage.objects.get(user=account, month=this_month()).messages == 0
        assert AssistantUsage.objects.get(user=account, month=last_month).messages == 5
        assert AssistantUsage.objects.get(user=other).messages == 5
        assert AssistantUsage.objects.get(hub=business).messages == 5

    def test_the_tokens_and_the_cost_go_to_the_accounts_month(self, account):
        record = UsageRecordIn(
            caller=account_of(account), tokens_input=1000, tokens_output=200, cost_usd=Decimal("0.0036")
        )
        services.usage_record(platform_context(), record)

        row = AssistantUsage.objects.get(user=account)
        assert (row.messages, row.tokens_input, row.tokens_output, row.cost_usd) == (0, 1000, 200, Decimal("0.0036"))
        assert row.month == this_month()

    def test_the_outbox_names_the_account_with_numbers_only(self, account):
        claim(account_of(account))

        payload = OutboxEvent.objects.get(name="assistant.message.claimed").payload
        assert payload == {"hub": None, "demo": "", "user": str(account.pk), "used": 1, "limit": 30}


class TestTheReportOfAnAccount:
    def test_an_account_gone_mails_nothing(self, account):
        from django.core import mail
        from live.errors import NotFound

        from assistant.schemas import ReportSendIn

        caller = account_of(account)
        account.delete()

        with pytest.raises(NotFound):
            services.report_send(
                platform_context(), ReportSendIn(caller=caller, message_id="m1", reason="other", answer="a")
            )
        assert not mail.outbox

    def test_the_same_message_id_of_another_account_is_its_own_report(self, account, make_user):
        from django.core import mail

        from assistant.schemas import ReportSendIn

        other = make_user("other@example.com")
        for who in (account, other):
            sent = services.report_send(
                platform_context(), ReportSendIn(caller=account_of(who), message_id="m1", reason="other", answer="a")
            )
            assert (sent.sent, sent.duplicate) == (True, False)

        assert [message.subject for message in mail.outbox] == [
            f"[Assistant report] {account.email} · other",
            "[Assistant report] other@example.com · other",
        ]


class TestWhoACallerIs:
    def test_a_caller_is_exactly_one_of_a_business_a_demo_or_an_account(self, account, business):
        with pytest.raises(ValidationError):
            Caller()
        with pytest.raises(ValidationError):
            Caller(hub_id=business.id, slug=business.slug, user_id=account.pk)
        with pytest.raises(ValidationError):
            Caller(demo="demo-1a2b3c4d", slug="demo-1a2b3c4d", user_id=account.pk)
        assert Caller(user_id=account.pk).slug == ""

    def test_the_rate_limit_and_the_continuations_know_an_account_by_its_id(self, account):
        assert turn.caller_key(account_of(account)) == f"user:{account.pk}"


class TestTheTableRefusesWhatIsNoRow:
    def test_a_row_of_a_business_and_an_account_at_once(self, account, business):
        with pytest.raises(IntegrityError), transaction.atomic():
            AssistantUsage.objects.create(hub=business, user=account, month=this_month())

    def test_a_row_of_a_demo_and_an_account_at_once(self, account):
        with pytest.raises(IntegrityError), transaction.atomic():
            AssistantUsage.objects.create(demo="demo-1a2b3c4d", user=account, month=this_month())

    def test_two_rows_of_one_account_and_month(self, account):
        AssistantUsage.objects.create(user=account, month=this_month())

        with pytest.raises(IntegrityError), transaction.atomic():
            AssistantUsage.objects.create(user=account, month=this_month())

    def test_an_account_deleted_takes_its_rows_with_it(self, account):
        claim(account_of(account))

        account.delete()

        assert not AssistantUsage.objects.exists()


class TestTheMigration:
    def test_going_back_forgets_the_accounts_rows_and_keeps_the_rest(self, account, business):
        from django.core.management import call_command
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        AssistantUsage.objects.create(user=account, month=this_month(), messages=3)
        AssistantUsage.objects.create(hub=business, month=this_month(), messages=4)
        AssistantUsage.objects.create(demo="demo-1a2b3c4d", month=this_month(), messages=5)
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        call_command("migrate", "assistant", "0002", verbosity=0)
        before = MigrationLoader(connection).project_state(("assistant", "0002_usage")).apps
        kept = sorted(before.get_model("assistant", "AssistantUsage").objects.values_list("messages", flat=True))
        call_command("migrate", "assistant", verbosity=0)

        assert kept == [4, 5]
        assert sorted(AssistantUsage.objects.values_list("messages", flat=True)) == [4, 5]

    def test_the_models_and_the_migrations_agree(self):
        from django.core.management import call_command

        call_command("makemigrations", "assistant", "--check", "--dry-run", verbosity=0)
