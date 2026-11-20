"""A question of the panel's assistant that carries a file is offered the tools its words ask for: the turn ranks the
text of a message that brings files as it ranks a message of text alone."""

import pytest
from live.operations import get as get_operation

from hubs.tests.conftest import ctx_for, make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

FILE = {"type": "input_file", "filename": "invoice.pdf", "mime_type": "application/pdf", "data": "JVBERi0xLjQK"}
WORDS = "Which invoices do I have? This is the one I got"


@pytest.fixture
def account(make_user, plans):
    return make_user("lena@example.com", first_name="Lena", language="en")


def offered(account, *messages: dict) -> list[str]:
    op = get_operation("base.assistant.turn")
    plan = op(ctx_for(account), op.input(messages=list(messages))).model_dump(mode="json")
    return [tool["name"] for tool in plan["tools"]]


def test_a_question_with_a_file_attached_is_offered_the_tools_its_words_ask_for(account):
    plain = offered(account, {"role": "user", "content": WORDS})
    with_file = offered(account, {"role": "user", "content": [{"type": "text", "text": WORDS}, FILE]})

    assert "billing__invoice__list" in plain
    assert with_file == plain


def test_a_file_sent_alone_keeps_the_tools_of_what_was_asked_before_it(account):
    """An account holds fewer tools than a turn offers, so what counts is the rank: the invoices come as high as when
    they are asked for alone, not where the alphabet puts them."""
    plain = offered(account, {"role": "user", "content": WORDS})
    tools = offered(
        account,
        {"role": "user", "content": WORDS},
        {"role": "assistant", "content": "Send it over."},
        {"role": "user", "content": "Sure, here it comes."},
        {"role": "assistant", "content": "Whenever you are ready."},
        {"role": "user", "content": [FILE]},
    )

    assert tools.index("billing__invoice__list") == plain.index("billing__invoice__list")
