"""A turn of the panel's assistant answers the calls that wait (``pending``) one by one: what runs, what stops at its
card, and what the model hears of what did not run. Only ``base.assistant.turn``: no route, no model."""

import json

import pytest
from django.contrib.auth import get_user_model
from live import assistant as assistant_shared
from live.operations import Operation, registry
from live.operations import get as get_operation
from ninja import Schema

from base.services import NOT_CONFIRMED_CODE
from hubs.tests.conftest import create_business, ctx_for, put_the_catalogue_back

pytestmark = pytest.mark.django_db

STOPPED = ("cancelled", "base.assistant_stopped")
NO = ("cancelled", NOT_CONFIRMED_CODE)
NOT_FROM_THE_CHAT = ("cancelled", "base.assistant_not_from_chat")


@pytest.fixture
def account(db):
    put_the_catalogue_back()
    return get_user_model().objects.create_user(email="lena@example.com", password=None, language="en")


def call(call_id: str, name: str, arguments: str = "{}") -> dict:
    return {"call_id": call_id, "name": name.replace(".", "__"), "arguments": arguments}


def spanish(call_id: str = "c1") -> dict:
    """A write that asks for no word: the account's language."""
    return call(call_id, "accounts.preferences.update", '{"language": "es"}')


def turn(account, *pending: dict, **decision) -> dict:
    op = get_operation("base.assistant.turn")
    asked = {"messages": [{"role": "user", "content": "Go on"}], "pending": list(pending)}
    if decision:
        asked["decision"] = {"call_id": "c1", **decision}
    return op(ctx_for(account), op.input.model_validate(asked)).model_dump(mode="json")


def outcomes(got: dict) -> list[tuple[str, str]]:
    return [(ran["outcome"], ran["code"]) for ran in got["executed"]]


def language_of(account) -> str:
    account.refresh_from_db()
    return account.language


class TestCancelAll:
    def test_neither_the_write_it_answers_nor_the_rest_of_the_calls_run(self, account):
        rest = [call("c2", "hubs.business.list"), spanish("c3")]

        got = turn(account, spanish(), *rest, accepted=False, stop=True)

        assert outcomes(got) == [STOPPED] * 3
        assert (got["confirm"], got["pending"]) == (None, [])
        assert {told["content"] for told in got["append"]} == {assistant_shared.stopped().content}
        assert language_of(account) == "en"

    def test_a_tool_not_offered_is_still_told_so(self, account):
        got = turn(account, spanish(), call("c2", "accounts.apikey.create"), accepted=False, stop=True)

        assert outcomes(got) == [STOPPED, ("refused", "not_available")]

    def test_it_stops_the_write_even_with_a_yes(self, account):
        got = turn(account, spanish(), accepted=True, stop=True)

        assert outcomes(got) == [STOPPED]
        assert language_of(account) == "en"


class TestTheAnswerToACard:
    def test_a_yes_runs_a_write_that_asks_for_no_word(self, account):
        got = turn(account, spanish(), accepted=True)

        assert outcomes(got) == [("ok", "")]
        assert (got["confirm"], got["pending"]) == (None, [])
        assert language_of(account) == "es"

    def test_a_no_runs_nothing_even_when_it_asks_for_no_word(self, account):
        got = turn(account, spanish(), accepted=False)

        assert outcomes(got) == [NO]
        assert language_of(account) == "en"

    def test_the_answer_to_another_card_is_no_answer_to_this_one(self, account):
        got = turn(account, spanish("c2"), accepted=True)

        assert got["executed"] == []
        assert got["confirm"]["operation"] == "accounts.preferences.update"
        assert got["pending"] == [spanish("c2")]
        assert language_of(account) == "en"


class TestWhatTheModelWroteOfAWrite:
    def test_a_write_the_model_sent_no_data_of_waits_for_its_card(self, account):
        got = turn(account, call("c1", "accounts.preferences.update", ""))

        assert got["executed"] == []
        assert got["confirm"]["operation"] == "accounts.preferences.update"

    @pytest.mark.parametrize("arguments", ['{"language": "es"', "[]", '"es"', "7", "null"])
    def test_data_that_are_no_object_show_no_card_and_the_model_hears_so(self, account, arguments):
        got = turn(account, call("c1", "accounts.preferences.update", arguments))

        assert outcomes(got) == [("error", "invalid_payload")]
        assert (got["confirm"], got["pending"]) == (None, [])
        assert json.loads(got["append"][0]["content"])["error"]["code"] == "invalid_payload"


class RecordsIn(Schema):
    ids: list[str]


class TestADangerousWriteThatNamesNoRecord:
    """No write of the panel goes over records by their ``ids`` today: this one, test-only, is the shape of the first
    that will. One that names none is not done from the chat: its card says so and no answer to it runs anything."""

    CLOSE = call("c1", "hubs.business.close_several", '{"ids": []}')

    @pytest.fixture(autouse=True)
    def ran(self, monkeypatch) -> list:
        ran: list = []
        operation = Operation(
            name="hubs.business.close_several",
            kind="command",
            permission="hubs.manage",
            input=RecordsIn,
            output=RecordsIn,
            expose_api=False,
            ai={
                "description": "Closes several businesses.",
                "risk": "high",
                "preview": {"operation": "hubs.business.list", "fields": ["rows"]},
            },
            fn=lambda ctx, data: ran.append(data) or data,
        )
        monkeypatch.setitem(registry, operation.name, operation)
        return ran

    def test_its_card_says_it_is_not_done_from_the_chat_and_asks_for_no_preview(self, account):
        got = turn(account, self.CLOSE)

        assert got["executed"] == []
        assert (got["confirm"]["blocked"], got["confirm"]["preview"]) == (True, None)
        assert got["pending"] == [self.CLOSE]

    def test_one_that_names_its_records_shows_what_it_will_do(self, account):
        create_business(account, name="Bar Lena")

        got = turn(account, {**self.CLOSE, "arguments": '{"ids": ["one"]}'})

        assert (got["confirm"]["blocked"], got["confirm"]["count"]) == (False, 1)
        assert [shown["name"] for shown in got["confirm"]["preview"]] == ["rows"]

    @pytest.mark.parametrize(
        "answer",
        [{"accepted": True, "typed": "CONFIRM"}, {"accepted": False}, {"accepted": False, "stop": True}],
    )
    def test_no_answer_to_its_card_runs_it(self, account, ran, answer):
        got = turn(account, self.CLOSE, **answer)

        assert outcomes(got) == [NOT_FROM_THE_CHAT]
        assert (got["confirm"], got["pending"], ran) == (None, [], [])

    def test_cancel_all_on_its_card_stops_the_rest_of_the_calls(self, account):
        got = turn(account, self.CLOSE, spanish("c2"), accepted=False, stop=True)

        assert outcomes(got) == [NOT_FROM_THE_CHAT, STOPPED]
