"""ASSISTANT-F25 · The panel's frames of a turn through the gateway (``base.assistant.gateway_frames``).

The gateway (``assistant.turn``) is replaced here by a script of the frames it yields, so each of them is read on its
own: what the panel sees (``text``, ``usage``, ``error``), what only the closing ``done`` carries (the tools the model
asked for, the continuation, pages from the web) and how a refused or broken start ends the stream with a lone
``error``. The frames are compared as JSON text, so the order of their keys, which reaches the browser, counts too.
"""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from django.conf import settings

from assistant import turn as gateway
from base import assistant

CALLER = SimpleNamespace(user_id="account")
REQUEST = SimpleNamespace(name="request")
PLAN = {
    "messages": [{"role": "user", "content": "How much do I pay?"}],
    "instructions": "You are the assistant of the panel.",
    "tools": [{"name": "hubs__business__list"}],
    "continuation": "previous-token",
    "executed": [],
    "confirm": None,
    "stop": None,
    "append": [],
    "pending": [],
}
USAGE = {"type": "usage", "used": 3, "limit": 30, "resets_at": "2026-12-01T00:00:00Z", "demo": False}
CALL = {"type": "function_call", "call_id": "c1", "name": "hubs__business__list", "arguments": '{"limit": 5}'}
KEPT_CALL = {"call_id": "c1", "name": "hubs__business__list", "arguments": '{"limit": 5}'}


class Gateway:
    """The gateway's three steps, scripted: the turn's budget, its start and its frames."""

    def __init__(self, frames=(), *, refuse_at=None, broken=False):
        self.script = list(frames)
        self.refuse_at = refuse_at
        self.broken = broken
        self.spent = []
        self.started = []
        self.closed = False

    def spend(self, request, bucket, rate, caller):
        self.spent.append((request, bucket, rate, caller))
        if self.refuse_at == "spend":
            raise gateway.Refused(429, "rate_limited", "Too many.", retry_after=7)

    async def start(self, caller, data, *, answer_kept):
        self.started.append((caller, vars(data), answer_kept))
        if self.refuse_at == "start":
            raise gateway.Refused(413, "too_large", "Too big.")
        if self.broken:
            raise RuntimeError("the database is gone")
        return "the started turn"

    async def frames(self, started):
        assert started == "the started turn"
        try:
            for frame in self.script:
                yield frame
        finally:
            self.closed = True


@pytest.fixture
def scripted(monkeypatch):
    def install(*frames, **how):
        fake = Gateway(frames, **how)
        monkeypatch.setattr(gateway, "spend", fake.spend)
        monkeypatch.setattr(gateway, "start", fake.start)
        monkeypatch.setattr(gateway, "frames", fake.frames)
        return fake

    return install


def turn(plan: dict = PLAN) -> list[dict]:
    async def collect():
        return [frame async for frame in assistant.gateway_frames(REQUEST, CALLER, plan)]

    return asyncio.run(collect())


def as_sent(frames: list[dict]) -> list[str]:
    return [json.dumps(frame) for frame in frames]


def done(append, pending=(), continuation=None, web=False) -> dict:
    return {"type": "done", "append": append, "pending": list(pending), "continuation": continuation, "web": web}


def said(text: str, calls=()) -> dict:
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": call["call_id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
            for call in calls
        ]
    return message


class TestTheStart:
    def test_it_spends_one_turn_of_the_accounts_budget_and_starts_with_the_plan(self, scripted):
        fake = scripted("[DONE]")
        turn()
        assert fake.spent == [(REQUEST, "turn", settings.ASSISTANT_TURN_RATELIMIT, CALLER)]
        data = {key: PLAN[key] for key in ("messages", "instructions", "tools", "continuation")}
        assert fake.started == [(CALLER, data, False)]

    def test_a_budget_spent_is_a_lone_error_and_the_turn_never_starts(self, scripted):
        fake = scripted("[DONE]", refuse_at="spend")
        expected = {"type": "error", "code": "assistant.rate_limited", "retry_after": 7}
        assert as_sent(turn()) == as_sent([expected])
        assert fake.started == []

    def test_a_start_the_gateway_refuses_is_a_lone_error(self, scripted):
        scripted("[DONE]", refuse_at="start")
        assert as_sent(turn()) == as_sent([{"type": "error", "code": "assistant.too_large"}])

    def test_a_start_that_breaks_is_a_lone_retriable_error_and_is_logged(self, scripted, caplog):
        scripted("[DONE]", broken=True)
        with caplog.at_level(logging.ERROR, logger="base.assistant"):
            got = turn()
        assert as_sent(got) == as_sent([{"type": "error", "code": "assistant.unavailable", "retriable": True}])
        assert [record.getMessage() for record in caplog.records] == ["base.assistant.turn_not_started"]


class TestWhatThePanelSees:
    def test_the_text_comes_piece_by_piece_and_the_done_keeps_it_whole(self, scripted):
        scripted({"type": "text_delta", "text": "You pay "}, {"type": "text_delta", "text": "20 €."}, "[DONE]")
        expected = [{"type": "text", "text": "You pay "}, {"type": "text", "text": "20 €."}, done([said("You pay 20 €.")])]
        assert as_sent(turn()) == as_sent(expected)

    def test_an_empty_piece_of_text_shows_nothing(self, scripted):
        scripted({"type": "text_delta", "text": ""}, {"type": "text_delta"}, "[DONE]")
        assert as_sent(turn()) == as_sent([done([said("")])])

    def test_the_usage_shows_only_the_accounts_allowance(self, scripted):
        scripted({**USAGE, "tokens": 120}, "[DONE]")
        assert as_sent(turn()) == as_sent([USAGE, done([said("")])])

    def test_a_frame_it_does_not_know_shows_nothing(self, scripted):
        scripted({"type": "reasoning", "text": "hmm"}, {"text": "no type"}, "[DONE]")
        assert as_sent(turn()) == as_sent([done([said("")])])

    def test_nothing_after_the_end_is_lost(self, scripted):
        scripted("[DONE]", {"type": "text_delta", "text": "late"})
        assert as_sent(turn()) == as_sent([{"type": "text", "text": "late"}, done([said("late")])])


class TestWhatTheDoneCarries:
    def test_the_tools_the_model_asked_for_wait_with_their_continuation(self, scripted):
        scripted({"type": "text_delta", "text": "Let me look."}, CALL, {"type": "response", "continuation": "t1"}, "[DONE]")
        expected = done([said("Let me look.", [KEPT_CALL])], [KEPT_CALL], "t1")
        assert as_sent(turn()) == as_sent([{"type": "text", "text": "Let me look."}, expected])

    def test_a_call_is_kept_as_text_and_without_arguments_it_asks_with_none(self, scripted):
        scripted({"type": "function_call", "call_id": 7, "name": None, "arguments": None}, "[DONE]")
        kept = {"call_id": "7", "name": "None", "arguments": "{}"}
        assert as_sent(turn()) == as_sent([done([said("", [kept])], [kept])])

    def test_an_empty_continuation_is_none(self, scripted):
        scripted(CALL, {"type": "response", "continuation": ""}, "[DONE]")
        assert as_sent(turn()) == as_sent([done([said("", [KEPT_CALL])], [KEPT_CALL], None)])

    def test_pages_from_the_web_are_told_to_the_browser(self, scripted):
        scripted({"type": "text_delta", "text": "1 € = 1.08 $"}, {"type": "web"}, "[DONE]")
        expected = [{"type": "text", "text": "1 € = 1.08 $"}, done([said("1 € = 1.08 $")], web=True)]
        assert as_sent(turn()) == as_sent(expected)


class TestATurnThatDoesNotEnd:
    def test_a_failure_of_the_provider_keeps_what_was_said_and_drops_the_tools(self, scripted):
        scripted(
            {"type": "text_delta", "text": "Half"},
            CALL,
            {"type": "response", "continuation": "t1"},
            {"type": "web"},
            {"type": "error", "code": "assistant.provider_unavailable", "retriable": 1},
            "[DONE]",
        )
        expected = [
            {"type": "text", "text": "Half"},
            {"type": "error", "code": "assistant.provider_failed", "retriable": True},
            done([said("Half")], web=True),
        ]
        assert as_sent(turn()) == as_sent(expected)

    def test_a_failure_that_cannot_be_retried_says_so(self, scripted):
        scripted({"type": "error", "code": "assistant.provider_rejected"}, "[DONE]")
        expected = [{"type": "error", "code": "assistant.provider_failed", "retriable": False}, done([])]
        assert as_sent(turn()) == as_sent(expected)

    def test_frames_that_stop_before_the_end_keep_only_what_was_said(self, scripted):
        scripted({"type": "text_delta", "text": "Cut"}, CALL, {"type": "response", "continuation": "t1"})
        assert as_sent(turn()) == as_sent([{"type": "text", "text": "Cut"}, done([said("Cut")])])

    def test_with_nothing_said_the_done_keeps_nothing(self, scripted):
        scripted(CALL)
        assert as_sent(turn()) == as_sent([done([])])

    def test_the_browser_leaving_closes_the_gateways_frames_at_once(self, scripted):
        fake = scripted({"type": "text_delta", "text": "One"}, {"type": "text_delta", "text": "Two"}, "[DONE]")

        async def leave_after_the_first():
            frames = assistant.gateway_frames(REQUEST, CALLER, PLAN)
            first = await anext(frames)
            await frames.aclose()
            return first, fake.closed

        assert asyncio.run(leave_after_the_first()) == ({"type": "text", "text": "One"}, True)
