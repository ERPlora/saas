"""ASSISTANT-F29 · Mail an account that the messages of erplora.com's panel assistant are running out: once at 80 %
of the month (24 of 30, where the panel's footer starts saying it: ``usageNote`` of @erplora/ui) and once at the
last one (30 of 30), each a single time per account and month, in the person's language, after the COMMIT of the
``assistant.message.claim`` that reached it. A mail that cannot leave never stops the turn: it is tried again with the
next message of that month, with the figures of that moment. A business's allowance and a demo's mail nobody.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from smtplib import SMTPException

import pytest
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.db import connection
from django.utils import timezone, translation
from django.utils.formats import date_format
from live.outbox import OutboxEvent

from assistant import queries, services
from assistant.models import AssistantUsage
from assistant.schemas import Caller, MessageReleaseIn
from assistant.services import platform_context
from assistant.tests.test_quota import RIVALS, waiting_on_a_lock

pytestmark = pytest.mark.django_db

PANEL = "https://erplora.com/dashboard"
EACH_BUSINESS_ES = (
    "Cada negocio tiene su propio asistente, con sus propios mensajes: abre el negocio para seguir preguntando allí."
)
EACH_BUSINESS_EN = "Each business has its own assistant, with its own messages: open the business to keep asking there."


def this_month() -> date:
    return queries.month_of(timezone.now())


def comes_back(month: date, language: str) -> str:
    """How the mail names the day the allowance of ``month`` comes back («1 de diciembre», «December 1»)."""
    with translation.override(language):
        return date_format(queries.resets_at(month).date(), "MONTH_DAY_FORMAT")


def spent(user, messages: int, *, month: date | None = None, **marks) -> AssistantUsage:
    return AssistantUsage.objects.create(user=user, month=month or this_month(), messages=messages, **marks)


@pytest.fixture(autouse=True)
def public_host(settings):
    settings.PUBLIC_HOST = "erplora.com"


@pytest.fixture
def account(owner):
    """An account that reads its mails in Spanish (``owner``: owner@example.com, ``language="es"``)."""
    return owner


@pytest.fixture
def turn(django_capture_on_commit_callbacks):
    """A message of ``user``'s allowance taken for a turn, as the panel's turn takes it, and its COMMIT."""

    def one(user):
        with django_capture_on_commit_callbacks(execute=True):
            return services.message_claim(platform_context(), Caller(user_id=user.pk))

    return one


@pytest.fixture
def give_back(django_capture_on_commit_callbacks):
    def one(user):
        with django_capture_on_commit_callbacks(execute=True):
            services.message_release(
                platform_context(), MessageReleaseIn(caller=Caller(user_id=user.pk), month=this_month())
            )

    return one


@pytest.fixture
def mail_down(monkeypatch):
    """The mail server refuses every mail until ``up()``."""
    state = {"down": True}
    send = EmailBackend.send_messages

    def refuse(self, messages):
        if state["down"]:
            raise SMTPException("421 try again later")
        return send(self, messages)

    monkeypatch.setattr(EmailBackend, "send_messages", refuse)

    class Switch:
        @staticmethod
        def up():
            state["down"] = False

    return Switch


class TestTheMailAtEightyPercent:
    def test_the_24th_of_30_mails_how_many_are_left_and_when_they_come_back(self, account, turn):
        spent(account, 23)

        assert turn(account).claimed is True

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [account.email]
        assert "Te quedan 6 de 30 mensajes con el asistente este mes." in sent.body
        assert f"Se renuevan el {comes_back(this_month(), 'es')}." in sent.body
        assert PANEL in sent.body
        assert sent.alternatives and sent.alternatives[0][1] == "text/html"
        assert PANEL in sent.alternatives[0][0]

    def test_it_offers_no_plan_nor_messages_to_buy(self, account, turn):
        spent(account, 23)

        turn(account)

        body = mail.outbox[0].body
        assert "/dashboard/store" not in body and "/dashboard/billing" not in body
        assert "plan" not in body.lower()

    def test_it_is_in_the_language_of_the_person(self, make_user, turn):
        reader = make_user("reader@example.com", language="en")
        spent(reader, 23)

        turn(reader)

        body = mail.outbox[0].body
        assert "You have 6 of 30 messages with the assistant left this month." in body
        assert f"They come back on {comes_back(this_month(), 'en')}." in body

    def test_with_one_left_it_says_one_message(self, make_user, turn, mail_down):
        reader = make_user("reader@example.com", language="es")
        spent(reader, 23)
        for _ in range(5):
            turn(reader)

        mail_down.up()
        turn(reader)

        assert "Te queda 1 de 30 mensajes con el asistente este mes." in mail.outbox[0].body
        assert mail.outbox[0].subject == "Te queda 1 mensaje con el asistente este mes"

    def test_the_23rd_mails_nothing(self, account, turn):
        spent(account, 22)

        assert turn(account).used == 23

        assert mail.outbox == []

    def test_the_rest_of_the_month_until_the_last_mails_nothing_more(self, account, turn):
        spent(account, 23)

        used = [turn(account).used for _ in range(6)]

        assert used == [24, 25, 26, 27, 28, 29]
        assert len(mail.outbox) == 1

    def test_it_is_where_the_footer_of_the_panel_starts_with_any_allowance(self, account, turn, settings):
        settings.ASSISTANT_ACCOUNT_MESSAGES = 10
        spent(account, 6)

        turn(account)
        assert mail.outbox == []
        turn(account)

        assert len(mail.outbox) == 1
        assert "Te quedan 2 de 10 mensajes" in mail.outbox[0].body


class TestTheMailAtTheLast:
    def test_the_30th_mails_that_they_are_spent_and_that_each_business_has_its_own(self, account, turn):
        spent(account, 29, near_warned_at=timezone.now())

        assert turn(account).claimed is True

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "Has usado los 30 mensajes con el asistente de este mes." in body
        assert f"Se renuevan el {comes_back(this_month(), 'es')}." in body
        assert EACH_BUSINESS_ES in body
        assert PANEL in body
        assert "Te quedan" not in body
        assert "/dashboard/store" not in body and "plan" not in body.lower()

    def test_in_english(self, make_user, turn):
        reader = make_user("reader@example.com", language="en")
        spent(reader, 29, near_warned_at=timezone.now())

        turn(reader)

        body = mail.outbox[0].body
        assert "You have used all 30 messages with the assistant this month." in body
        assert EACH_BUSINESS_EN in body

    def test_a_refused_turn_after_it_mails_nothing_more(self, account, turn):
        spent(account, 29, near_warned_at=timezone.now())
        turn(account)

        assert turn(account).claimed is False

        assert len(mail.outbox) == 1

    def test_with_the_allowance_spent_only_the_last_one_leaves_never_how_many_are_left(self, account, turn, settings):
        settings.ASSISTANT_ACCOUNT_MESSAGES = 2

        turn(account)
        assert mail.outbox == []
        turn(account)

        assert len(mail.outbox) == 1
        assert "Has usado los 2 mensajes" in mail.outbox[0].body
        assert "Te quedan" not in mail.outbox[0].body
        row = AssistantUsage.objects.get(user=account)
        assert row.near_warned_at is None and row.spent_warned_at is not None


class TestOnceAnAccountAndMonth:
    def test_a_message_given_back_does_not_mail_again_when_it_is_reached_again(self, account, turn, give_back):
        spent(account, 23)
        turn(account)

        give_back(account)
        assert turn(account).used == 24

        assert len(mail.outbox) == 1

    def test_the_last_given_back_does_not_mail_again_either(self, account, turn, give_back):
        spent(account, 29, near_warned_at=timezone.now())
        turn(account)

        give_back(account)
        assert turn(account).used == 30

        assert len(mail.outbox) == 1

    def test_the_next_month_mails_again(self, account, turn, monkeypatch):
        last_second = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
        monkeypatch.setattr(timezone, "now", lambda: last_second)
        spent(account, 23, month=date(2026, 10, 1))
        turn(account)

        monkeypatch.setattr(timezone, "now", lambda: last_second + timedelta(seconds=1))
        spent(account, 23, month=date(2026, 11, 1))
        turn(account)

        assert len(mail.outbox) == 2
        assert f"Se renuevan el {comes_back(date(2026, 10, 1), 'es')}." in mail.outbox[0].body
        assert f"Se renuevan el {comes_back(date(2026, 11, 1), 'es')}." in mail.outbox[1].body

    def test_the_outbox_names_the_account_and_the_figures(self, account, turn):
        spent(account, 23)
        turn(account)
        spent_too = AssistantUsage.objects.get(user=account)
        AssistantUsage.objects.filter(pk=spent_too.pk).update(messages=29)
        turn(account)

        payloads = [event.payload for event in OutboxEvent.objects.filter(name="assistant.usage.warned").order_by("pk")]
        assert payloads == [
            {"user": str(account.pk), "warning": "near", "used": 24, "limit": 30},
            {"user": str(account.pk), "warning": "spent", "used": 30, "limit": 30},
        ]


class TestAMailThatDoesNotLeave:
    def test_the_turn_goes_on_and_the_next_message_tries_again_with_its_figures(self, account, turn, mail_down, caplog):
        spent(account, 23)

        assert turn(account).claimed is True

        assert mail.outbox == []
        assert AssistantUsage.objects.get(user=account).near_warned_at is None
        assert "assistant.mail.not_sent" in caplog.text

        mail_down.up()
        turn(account)

        assert len(mail.outbox) == 1
        assert "Te quedan 5 de 30 mensajes" in mail.outbox[0].body
        assert AssistantUsage.objects.get(user=account).near_warned_at is not None

    def test_failing_until_the_last_sends_only_the_last(self, account, turn, mail_down):
        spent(account, 23)
        for _ in range(6):
            turn(account)

        mail_down.up()
        turn(account)
        turn(account)

        assert len(mail.outbox) == 1
        assert "Has usado los 30 mensajes" in mail.outbox[0].body
        assert AssistantUsage.objects.get(user=account).near_warned_at is None

    def test_a_refused_turn_tries_the_last_one_again(self, account, turn, mail_down):
        spent(account, 29, near_warned_at=timezone.now())
        turn(account)
        assert mail.outbox == []

        mail_down.up()
        assert turn(account).claimed is False

        assert len(mail.outbox) == 1
        assert "Has usado los 30 mensajes" in mail.outbox[0].body


class TestNobodyElseIsMailed:
    def test_a_business_spending_its_plans_messages_mails_nobody(self, account, business, django_capture_on_commit_callbacks):
        AssistantUsage.objects.create(hub=business, month=this_month(), messages=23)

        with django_capture_on_commit_callbacks(execute=True):
            for _ in range(8):
                services.message_claim(platform_context(), Caller(hub_id=business.pk))

        assert AssistantUsage.objects.get(hub=business).messages == 30
        assert mail.outbox == []
        assert not OutboxEvent.objects.filter(name="assistant.usage.warned").exists()

    def test_a_demo_mails_nobody(self, settings, django_capture_on_commit_callbacks):
        settings.ASSISTANT_DEMO_MESSAGES = 5

        with django_capture_on_commit_callbacks(execute=True):
            for _ in range(6):
                services.message_claim(platform_context(), Caller(demo="demo-1a2b3c4d"))

        assert mail.outbox == []

    def test_an_account_gone_before_the_mail_mails_nobody(self, account, turn, monkeypatch):
        spent(account, 23)
        real = services.message_claim

        def claim_then_leave(ctx, caller):
            answer = real(ctx, caller)
            account.delete()
            return answer

        monkeypatch.setattr(services, "message_claim", claim_then_leave)

        turn(account)

        assert mail.outbox == []


class TestTheMigration:
    def test_going_back_drops_the_marks_and_keeps_the_rows(self, account):
        from django.core.management import call_command
        from django.db.migrations.loader import MigrationLoader

        spent(account, 24, near_warned_at=timezone.now())
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        call_command("migrate", "assistant", "0005", verbosity=0)
        before = MigrationLoader(connection).project_state(("assistant", "0005_drop_doc_chunk_hnsw")).apps
        kept = list(before.get_model("assistant", "AssistantUsage").objects.values_list("messages", flat=True))
        call_command("migrate", "assistant", verbosity=0)

        assert kept == [24]
        row = AssistantUsage.objects.get(user=account)
        assert (row.messages, row.near_warned_at, row.spent_warned_at) == (24, None, None)


@pytest.mark.django_db(transaction=True)
def test_turns_at_once_refused_at_the_last_mail_it_once(make_user, settings):
    """The last mail did not leave (its mark is free) and four turns, all refused, come at once: one mail, not four. A
    turn that read the mark and wrote it apart would let the four through (ASSISTANT-F29, paso 3)."""
    from django.db import transaction

    settings.PUBLIC_HOST = "erplora.com"
    account = make_user("race@example.com", language="es")
    month = this_month()
    AssistantUsage.objects.create(user=account, month=month, messages=30, near_warned_at=timezone.now())
    held, release = threading.Event(), threading.Event()
    answers = []

    def hold_the_row():
        try:
            with transaction.atomic():
                AssistantUsage.objects.select_for_update().get(user=account, month=month)
                held.set()
                release.wait(10)
        finally:
            connection.close()

    def one():
        try:
            answers.append(services.message_claim(platform_context(), Caller(user_id=account.pk)).claimed)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_row)
    holder.start()
    assert held.wait(5)
    rivals = [threading.Thread(target=one) for _ in range(RIVALS)]
    for thread in rivals:
        thread.start()
    assert waiting_on_a_lock(RIVALS, within=30), "the turns never met at the month's row"
    release.set()
    for thread in (holder, *rivals):
        thread.join(15)

    assert answers == [False] * RIVALS
    assert len(mail.outbox) == 1
    assert OutboxEvent.objects.filter(name="assistant.usage.warned").count() == 1
