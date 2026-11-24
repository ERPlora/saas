"""What a call to a model spent: its tokens as every provider's client counts them (all of the input, of which some
read from the provider's cache and some written to it, and the output) and their cost at the model's prices."""

from decimal import Decimal
from uuid import uuid4

from assistant.schemas import RouteCandidate
from assistant.usage_cost import Tokens, cost


def prices(read: str | None = None, write: str | None = None) -> RouteCandidate:
    return RouteCandidate(
        model=uuid4(),
        model_id="claude-haiku-5-5",
        display_name="Claude Haiku 5.5",
        provider="anthropic",
        kind="anthropic",
        base_url="",
        api_key="sk-test",
        price_input_per_1m=Decimal("0.10"),
        price_output_per_1m=Decimal("0.50"),
        price_cache_read_per_1m=None if read is None else Decimal(read),
        price_cache_write_per_1m=None if write is None else Decimal(write),
        supports_tools=True,
        supports_vision=False,
    )


class TestTheTokens:
    def test_a_providers_usage_without_the_cache_reads_none_of_it(self):
        assert Tokens.of({"input_tokens": 120, "output_tokens": 30}) == Tokens(input=120, output=30)

    def test_a_providers_usage_says_what_the_cache_read_and_wrote(self):
        usage = {"input_tokens": 6420, "output_tokens": 30, "cache_read_tokens": 3000, "cache_write_tokens": 3200}

        assert Tokens.of(usage) == Tokens(input=6420, output=30, cache_read=3000, cache_write=3200)

    def test_two_calls_add_up(self):
        assert Tokens(100, 20, 0, 3000) + Tokens(3320, 10, 3000, 200) == Tokens(3420, 30, 3000, 3200)


class TestTheirCost:
    def test_the_cache_is_paid_at_its_own_prices_and_the_rest_of_the_input_at_the_inputs(self):
        spent = Tokens(input=6420, output=30, cache_read=3000, cache_write=3200)

        # 220 fresh at 0.10, 3000 read at 0.01, 3200 written at 0.125 and 30 out at 0.50, per million.
        assert cost(prices(read="0.01", write="0.125"), spent) == Decimal("0.000467")

    def test_a_model_without_prices_of_the_cache_pays_it_as_input(self):
        spent = Tokens(input=6420, output=30, cache_read=3000, cache_write=3200)

        assert cost(prices(), spent) == Decimal("0.000657")

    def test_a_call_without_cache_costs_its_input_and_its_output(self):
        assert cost(prices(read="0.01", write="0.125"), Tokens(input=1000, output=250)) == Decimal("0.000225")
