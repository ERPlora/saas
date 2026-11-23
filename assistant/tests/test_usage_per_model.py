"""ASSISTANT-F24 · What each model of the assistant spent: a row of usage per business (or demo, or account), month and
model, named as its provider names it, with the messages asked of it and the tokens and the cost of what it answered.
The allowance of the month (ASSISTANT-F16) counts the messages of every model: changing the model that answers gives
nobody more messages, and what the Hub sees of it (used, limit, back on) does not change.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.test import Client
from django.utils import timezone

from assistant import queries, services
from assistant.media import EMBEDDING_MODEL, TRANSCRIBE_MODEL
from assistant.models import AIModel, AIRoutingPolicy, AssistantUsage
from assistant.schemas import Caller, ClaimIn, MessageReleaseIn, UsageRecordIn
from assistant.services.platform_actor import platform_context
from assistant.tests.conftest import openai_answer
from assistant.tests.doors import door, frames
from assistant.tests.test_quota import RIVALS, waiting_on_a_lock

STREAM = "/internal/assistant/chat/stream"
COMPLETIONS = "/v1/chat/completions"

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def other_model(answering):
    """A second model of the same provider, dearer: 4 $ in / 16 $ out per 1M."""
    return AIModel.objects.create(
        provider=answering.provider,
        model_id="gpt-other",
        display_name="GPT Other",
        price_input_per_1m=Decimal("4"),
        price_output_per_1m=Decimal("16"),
    )


def this_month():
    return queries.usage.month_of(timezone.now())


def answers_now(model) -> None:
    AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT).update(active_model=model)


def ask(client, business, fake_provider, *, tokens=(1000, 250)) -> list:
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok", tokens=tokens))
    return frames(door(client, STREAM, {"hub": business.slug, "messages": [{"role": "user", "content": "Hello"}]}))


def spent_by_model(**who) -> dict:
    return {
        row.model: (row.messages, row.tokens_input, row.tokens_output, row.cost_usd)
        for row in AssistantUsage.objects.filter(**who)
    }


def caller_of(hub) -> Caller:
    return Caller(hub_id=hub.id, slug=hub.slug)


def claim(caller, model="gpt-test"):
    return services.turn_usage.message_claim(platform_context(), ClaimIn(caller=caller, model=model))


class TestEachModelHasItsRow:
    def test_two_models_in_one_month_give_two_rows_and_the_allowance_counts_both(
        self, client, internal, business, answering, other_model, fake_provider
    ):
        first = ask(client, business, fake_provider)
        answers_now(other_model)
        second = ask(client, business, fake_provider)

        assert spent_by_model(hub=business, month=this_month()) == {
            "gpt-test": (1, 1000, 250, Decimal("0.004")),
            "gpt-other": (1, 1000, 250, Decimal("0.008")),
        }
        assert [frame["used"] for frame in (first[-2], second[-2])] == [1, 2]
        assert second[-2] == {"type": "usage", "used": 2, "limit": 30, "resets_at": second[-2]["resets_at"], "demo": False}

    def test_the_last_message_of_the_month_is_refused_whatever_model_answers(
        self, client, internal, business, answering, other_model, fake_provider
    ):
        AssistantUsage.objects.create(hub=business, month=this_month(), model="gpt-test", messages=20)
        AssistantUsage.objects.create(hub=business, month=this_month(), model="", messages=9)
        answers_now(other_model)

        assert ask(client, business, fake_provider)[-2]["used"] == 30
        response = door(client, STREAM, {"hub": business.slug, "messages": [{"role": "user", "content": "One more"}]})

        assert response.status_code == 429
        assert spent_by_model(hub=business)["gpt-other"][0] == 1

    def test_what_the_fallback_answered_is_the_fallbacks(self, client, internal, business, answering, fake_provider):
        backup = AIModel.objects.create(
            provider=answering.provider,
            model_id="gpt-backup",
            display_name="Backup",
            price_input_per_1m=Decimal("1"),
            price_output_per_1m=Decimal("1"),
        )
        AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT).update(fallback_model=backup)
        fake_provider.reply("POST", COMPLETIONS, status=503, json={"error": {"message": "overloaded"}})

        ask(client, business, fake_provider)

        spent = spent_by_model(hub=business)
        assert spent["gpt-backup"][1:] == (1000, 250, Decimal("0.00125"))
        assert spent["gpt-test"] == (1, 0, 0, Decimal("0"))


class TestTheAllowanceCountsEveryModel:
    def test_a_claim_counts_the_messages_of_the_other_models(self, business):
        AssistantUsage.objects.create(hub=business, month=this_month(), model="gpt-old", messages=29)

        claimed = claim(caller_of(business))

        assert (claimed.claimed, claimed.used, claimed.limit) == (True, 30, 30)
        assert claim(caller_of(business)).claimed is False
        assert spent_by_model(hub=business)["gpt-test"][0] == 1

    def test_a_message_refused_makes_no_row_for_the_model_it_asked(self, business):
        AssistantUsage.objects.create(hub=business, month=this_month(), model="gpt-old", messages=30)

        assert claim(caller_of(business)).claimed is False
        assert list(AssistantUsage.objects.values_list("model", flat=True)) == ["gpt-old"]

    def test_a_message_given_back_goes_back_to_the_model_it_was_asked_of(self, business):
        AssistantUsage.objects.create(hub=business, month=this_month(), model="gpt-old", messages=4)
        claimed = claim(caller_of(business))

        services.turn_usage.message_release(
            platform_context(), MessageReleaseIn(caller=caller_of(business), month=claimed.month, model="gpt-test")
        )

        assert {model: spent[0] for model, spent in spent_by_model(hub=business).items()} == {"gpt-old": 4, "gpt-test": 0}
        assert queries.usage.usage_show(platform_context(), caller_of(business)).used == 4

    def test_a_demos_few_count_every_model(self):
        demo = Caller(demo="demo-1a2b3c4d", slug="demo-1a2b3c4d")
        for _ in range(9):
            claim(demo, "gpt-old")

        assert claim(demo).claimed is True
        assert claim(demo).claimed is False

    def test_an_account_is_mailed_once_a_month_whatever_model_answers(
        self, owner, mailoutbox, settings, django_capture_on_commit_callbacks
    ):
        settings.PUBLIC_HOST = "erplora.com"
        AssistantUsage.objects.create(user=owner, month=this_month(), model="gpt-old", messages=23)
        account = Caller(user_id=owner.pk)

        with django_capture_on_commit_callbacks(execute=True):
            claim(account)
        with django_capture_on_commit_callbacks(execute=True):
            claim(account, "gpt-newer")

        assert len(mailoutbox) == 1


@pytest.mark.django_db(transaction=True)
def test_turns_at_once_asking_different_models_cannot_pass_the_last_message_together(business):
    """With one message left, claims at once, each asking a model with no row yet: one passes, the rest are refused.
    A claim that counted the other models' messages without waiting for the claims in flight would let them all
    through, each onto its own row."""
    hub = business
    AssistantUsage.objects.create(hub=hub, model="gpt-old", month=this_month(), messages=29)
    held, release = threading.Event(), threading.Event()
    answers = []

    def hold_the_old_models_row():
        try:
            with transaction.atomic():
                AssistantUsage.objects.select_for_update().get(hub=hub, model="gpt-old")
                held.set()
                release.wait(10)
        finally:
            connection.close()

    def one(model):
        try:
            answers.append(claim(caller_of(hub), model).claimed)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_old_models_row)
    holder.start()
    assert held.wait(5)
    rivals = [threading.Thread(target=one, args=(f"gpt-{number}",)) for number in range(RIVALS)]
    for thread in rivals:
        thread.start()
    assert waiting_on_a_lock(RIVALS, within=30), "the claims never waited for the other models' rows"
    release.set()
    for thread in (holder, *rivals):
        thread.join(15)

    assert sorted(answers) == [False] * (RIVALS - 1) + [True]
    assert queries.usage.usage_show(platform_context(), caller_of(hub)).used == 30


class TestWhatIsRecordedHasItsModel:
    def test_a_record_goes_to_the_row_of_its_model(self, business):
        record = UsageRecordIn(caller=caller_of(business), model=EMBEDDING_MODEL, tokens_embedding=500, cost_usd="0.00001")

        services.turn_usage.usage_record(platform_context(), record)
        services.turn_usage.usage_record(platform_context(), record.model_copy(update={"model": TRANSCRIBE_MODEL}))

        assert set(spent_by_model(hub=business)) == {EMBEDDING_MODEL, TRANSCRIBE_MODEL}


class TestTheMigration:
    def test_going_back_joins_each_months_models_into_one_row(self, business, owner):
        from datetime import timedelta

        from django.core.management import call_command
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        month, mailed = this_month(), timezone.now()
        AssistantUsage.objects.create(hub=business, month=month, model="gpt-test", messages=3, cost_usd=Decimal("0.5"))
        AssistantUsage.objects.create(hub=business, month=month, model="gpt-other", messages=4, cost_usd=Decimal("0.25"))
        AssistantUsage.objects.create(user=owner, month=month, model="gpt-test", messages=1, near_warned_at=mailed)
        AssistantUsage.objects.create(
            user=owner, month=month, model="gpt-other", messages=2, near_warned_at=mailed - timedelta(days=1)
        )
        AssistantUsage.objects.create(demo="demo-1a2b3c4d", month=month, model="gpt-test", messages=5)
        AssistantUsage.objects.create(demo="demo-1a2b3c4d", month=month, model="gpt-other", messages=1)
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        call_command("migrate", "assistant", "0010", verbosity=0)
        before = MigrationLoader(connection).project_state(("assistant", "0010_haiku_answers")).apps
        joined = {
            (row.hub_id, row.user_id, row.demo): (row.messages, row.cost_usd, row.near_warned_at)
            for row in before.get_model("assistant", "AssistantUsage").objects.all()
        }
        call_command("migrate", "assistant", verbosity=0)

        assert joined == {
            (business.pk, None, ""): (7, Decimal("0.75"), None),
            (None, owner.pk, ""): (3, Decimal("0"), mailed - timedelta(days=1)),
            (None, None, "demo-1a2b3c4d"): (6, Decimal("0"), None),
        }
        assert set(AssistantUsage.objects.values_list("model", flat=True)) == {""}
