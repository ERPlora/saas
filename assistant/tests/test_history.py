"""ASSISTANT-F12 · The conversation the model reads: the request in progress and the one before whole, the older ones
lighter.

A request is a message of the person and everything that answered it. What an older request's tools returned reaches
the model as a short note, and the older requests that do not fit the budget go, oldest first and whole.
"""

from assistant import history


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def calling(call_id: str, name: str = "inventory_product_list") -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
    }


def result(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def reply(text: str) -> dict:
    return {"role": "assistant", "content": text}


def request(n: int, size: int = 2_000) -> list[dict]:
    """The person's request ``n``, the model's call of a tool, its result of ``size`` characters and its reply."""
    return [user(f"question {n}"), calling(f"call_{n}"), result(f"call_{n}", "r" * size), reply(f"answer {n}")]


def noted(request: list[dict]) -> list[dict]:
    """``request`` with its tool's result as the note."""
    return [{**message, "content": history.CLEARED} if message["role"] == "tool" else message for message in request]


def tokens_of(messages: list[dict]) -> int:
    return sum(history.tokens(message) for message in messages)


class TestWhatGoesWhole:
    def test_the_request_in_progress_and_the_one_before_go_whole_and_an_older_result_as_a_note(self):
        in_progress = request(3)[:3]

        window = history.window([*request(1), *request(2), *in_progress])

        assert window == [*noted(request(1)), *request(2), *in_progress]

    def test_an_answer_to_the_models_question_finds_what_its_request_read(self):
        asked = [user("Raise the cake to 6.50"), calling("call_1"), result("call_1", "c" * 3_000), reply("Which one?")]
        conversation = [*request(0), *asked, user("The cheese one")]

        assert history.window(conversation) == [*noted(request(0)), *asked, user("The cheese one")]

    def test_every_round_of_the_request_in_progress_goes_whole(self):
        in_progress = [*request(3), calling("call_9"), result("call_9", "s" * 3_000)]

        assert history.window([*request(1), *request(2), *in_progress])[8:] == in_progress

    def test_the_result_of_an_answer_to_the_persons_card_belongs_to_its_request(self):
        """A card's yes is not a message of the person: the Hub answers the call with its result, in the same
        request."""
        card = [user("Raise the cheesecake to 6.50"), calling("call_5", "inventory_product_update"), result("call_5", "u" * 500), reply("Done.")]

        window = history.window([*request(1), *card, user("Thanks")])

        assert window == [*noted(request(1)), *card, user("Thanks")]

    def test_what_the_person_and_the_model_wrote_in_an_older_request_stays_as_it_is(self):
        older = [user("Which products " * 20), calling("call_1"), result("call_1", "r" * 2_000), reply("You have these " * 20)]

        window = history.window([*older, *request(2), user("question 3")])

        assert window[:4] == noted(older)

    def test_a_result_no_longer_than_its_note_stays_as_it_is(self):
        short = '{"ok": true}'
        older = [user("question 1"), calling("call_1"), result("call_1", short), reply("Done.")]

        assert history.window([*older, *request(2), user("question 3")])[2]["content"] == short

    def test_a_conversation_without_a_message_of_the_person_goes_as_it_is(self):
        conversation = [reply("Hello"), calling("call_1"), result("call_1", "r" * 500)]

        assert history.window(conversation) == conversation


class TestTheBudget:
    def test_the_older_requests_that_do_not_fit_go_oldest_first_and_whole(self, monkeypatch):
        requests = [request(n, size=400) for n in range(1, 6)]
        monkeypatch.setattr(history, "BUDGET_TOKENS", tokens_of([*noted(requests[2]), *noted(requests[3])]))

        window = history.window([*sum(requests, []), user("now")])

        assert [message["content"] for message in window if message["role"] == "user"] == [
            "question 3",
            "question 4",
            "question 5",
            "now",
        ]

    def test_a_budget_just_short_of_a_request_leaves_it_out(self, monkeypatch):
        requests = [request(n, size=400) for n in range(1, 5)]
        monkeypatch.setattr(history, "BUDGET_TOKENS", tokens_of([*noted(requests[1]), *noted(requests[2])]) - 1)

        window = history.window([*sum(requests, []), user("now")])

        assert window[0] == user("question 3")

    def test_an_older_result_counts_as_its_note(self, monkeypatch):
        """An older request with a result far over the budget still fits once its result is the note."""
        monkeypatch.setattr(history, "BUDGET_TOKENS", 200)

        window = history.window([*request(1, size=50_000), *request(2), user("now")])

        assert window[0] == user("question 1")

    def test_the_request_in_progress_and_the_one_before_go_whole_even_over_the_budget(self, monkeypatch):
        monkeypatch.setattr(history, "BUDGET_TOKENS", 50)
        in_progress = request(3, size=40_000)[:3]

        window = history.window([*request(1), *request(2, size=40_000), *in_progress])

        assert window == [*request(2, size=40_000), *in_progress]

    def test_the_rounds_of_the_request_in_progress_leave_the_older_ones_as_they_were(self, monkeypatch):
        """Its rounds grow its size; the older requests the model reads stay the same, so the provider's cache reads
        them again on the next round."""
        older = [request(n) for n in range(1, 4)]
        monkeypatch.setattr(history, "BUDGET_TOKENS", tokens_of(sum(map(noted, older), [])))
        first_round = [*sum(older, []), *request(4), user("now")]
        later_round = [*first_round, calling("call_9"), result("call_9", "z" * 60_000)]

        assert history.window(later_round)[: len(first_round)] == history.window(first_round)
        assert history.window(later_round)[0] == user("question 1")

    def test_the_older_requests_the_model_reads_are_about_16_000_tokens(self):
        """With the budget as it ships: requests of about 1,000 tokens each, and only the newest that fit stay."""
        older = [[user(f"{n} " + "w" * 4_000), reply(f"answer {n}")] for n in range(40)]
        last = [*request(98), user("now")]

        kept = history.window([*sum(older, []), *last])[: -len(last)]

        assert kept == sum(older[-len(kept) // 2 :], [])
        assert 15_000 <= tokens_of(kept) <= 16_000

    def test_a_long_conversation_of_short_messages_is_not_cut_by_their_number(self):
        conversation = [user(f"message {n}") if n % 2 == 0 else reply(f"answer {n}") for n in range(150)]

        assert history.window(conversation) == conversation


class TestTheEstimate:
    def test_about_four_characters_are_a_token(self):
        assert 1_000 <= history.tokens(user("x" * 4_000)) <= 1_010

    def test_an_attachments_data_does_not_count(self):
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 400_000}}

        assert history.tokens({"role": "user", "content": [{"type": "text", "text": "Look"}, image]}) < 100
