"""What a turn of the assistant produced, for the door to answer and record after it: its text, the Hub's tool calls,
the pages erplora.com's own tools brought and what each model that answered spent, with that model's prices."""

from dataclasses import dataclass, field
from decimal import Decimal

from assistant import usage_cost
from assistant.schemas import RouteCandidate
from assistant.usage_cost import Tokens


@dataclass
class Spent:
    """What one model spent in a turn: its tokens and their cost (USD, with its prices)."""

    tokens: Tokens = Tokens()
    cost: Decimal = Decimal("0")


@dataclass
class Outcome:
    """What a turn produced, for the door to answer and record after it."""

    text: str = ""
    calls: list[dict] = field(default_factory=list)
    #: What each model that answered spent, by its name at the provider: a fallback may answer a later round.
    spent: dict[str, Spent] = field(default_factory=dict)
    #: The pages erplora.com's own tools brought, for the line below an answer that names none of them.
    sources: list[str] = field(default_factory=list)
    answered: bool = False
    web: bool = False
    error: dict | None = None

    @property
    def tokens_input(self) -> int:
        return sum(spent.tokens.input for spent in self.spent.values())

    @property
    def tokens_output(self) -> int:
        return sum(spent.tokens.output for spent in self.spent.values())

    def add_usage(self, answering: RouteCandidate, tokens: Tokens) -> None:
        spent = self.spent.setdefault(answering.model_id, Spent())
        spent.tokens += tokens
        spent.cost += usage_cost.cost(answering, tokens)

    def output(self) -> list[dict]:
        items: list[dict] = []
        if self.text:
            items.append({"type": "message", "content": [{"type": "output_text", "text": self.text}]})
        items.extend({"type": "function_call", **call} for call in self.calls)
        return items
