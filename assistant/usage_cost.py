"""What a call to a model spent: its tokens as every provider's client counts them (``Tokens``) and their cost at the
model's prices (``cost``).

The input counts all the model was sent, the provider's cache included: of it, ``cache_read`` was read from the cache
and ``cache_write`` written to it, each at its own price, and the rest at the input price. A model without a price of
its cache pays it as input.
"""

from dataclasses import dataclass
from decimal import Decimal

from assistant.models import estimate_cost
from assistant.schemas import RouteCandidate


@dataclass(frozen=True)
class Tokens:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @classmethod
    def of(cls, usage: dict) -> "Tokens":
        """The tokens of a provider's ``usage`` event (``assistant.providers.base``): an API that says nothing of its
        cache read and wrote none of it."""
        return cls(
            input=int(usage["input_tokens"]),
            output=int(usage["output_tokens"]),
            cache_read=int(usage.get("cache_read_tokens") or 0),
            cache_write=int(usage.get("cache_write_tokens") or 0),
        )

    def __add__(self, other: "Tokens") -> "Tokens":
        return Tokens(
            self.input + other.input,
            self.output + other.output,
            self.cache_read + other.cache_read,
            self.cache_write + other.cache_write,
        )


def cost(prices: RouteCandidate, tokens: Tokens) -> Decimal:
    """USD of ``tokens`` at the prices of the model that spent them (USD per million tokens), exact."""
    read = prices.price_input_per_1m if prices.price_cache_read_per_1m is None else prices.price_cache_read_per_1m
    write = prices.price_input_per_1m if prices.price_cache_write_per_1m is None else prices.price_cache_write_per_1m
    fresh = tokens.input - tokens.cache_read - tokens.cache_write
    cached = (read * tokens.cache_read + write * tokens.cache_write) / Decimal(1_000_000)
    return estimate_cost(prices.price_input_per_1m, prices.price_output_per_1m, fresh, tokens.output) + cached
