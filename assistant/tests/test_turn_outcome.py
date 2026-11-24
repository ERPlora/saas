"""What a turn produced and what each model that answered it spent, with that model's prices."""

from decimal import Decimal
from uuid import uuid4

from assistant.schemas import RouteCandidate
from assistant.turn_outcome import Outcome, Spent
from assistant.usage_cost import Tokens


def candidate(model_id: str, price_in: str, price_out: str) -> RouteCandidate:
    return RouteCandidate(
        model=uuid4(),
        model_id=model_id,
        display_name=model_id,
        provider="openai",
        kind="openai",
        base_url="",
        api_key="sk-test",
        price_input_per_1m=Decimal(price_in),
        price_output_per_1m=Decimal(price_out),
        supports_tools=True,
        supports_vision=False,
    )


def test_each_model_keeps_its_tokens_and_their_cost_at_its_prices():
    outcome = Outcome()
    first, fallback = candidate("gpt-test", "2", "8"), candidate("gpt-backup", "1", "1")

    outcome.add_usage(first, Tokens(input=1000, output=250))
    outcome.add_usage(fallback, Tokens(input=1000, output=250))
    outcome.add_usage(first, Tokens(input=500, output=0, cache_read=400))

    assert outcome.spent == {
        "gpt-test": Spent(tokens=Tokens(input=1500, output=250, cache_read=400), cost=Decimal("0.005")),
        "gpt-backup": Spent(tokens=Tokens(input=1000, output=250), cost=Decimal("0.00125")),
    }
    assert (outcome.tokens_input, outcome.tokens_output) == (2500, 500)


def test_a_turn_with_no_usage_spent_nothing():
    outcome = Outcome()

    assert (outcome.spent, outcome.tokens_input, outcome.tokens_output) == ({}, 0, 0)
