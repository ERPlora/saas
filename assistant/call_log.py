"""One line in the log for each call of the assistant to a model, to measure what a change to what the model is sent
saves: how many tools went and the characters of their specs, of the instructions, of the conversation and of the
tools' results, and the tokens its provider counted (all the input, of it what its cache read and wrote, and the
output). Numbers only, never a word of what was sent; an attachment's data is not measured.

The model goes by its id in erplora.com, not by its name at the provider: the log's formatter hides a long dated name
as if it were a credential.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from assistant import attachments
from assistant.providers.base import ToolSpec
from assistant.schemas import RouteCandidate
from assistant.usage_cost import Tokens

logger = logging.getLogger(__name__)


def _chars(value: Any) -> int:
    return len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False, default=str))


def _spec_chars(spec: ToolSpec) -> int:
    return _chars({"name": spec.name, "description": spec.description, "parameters": spec.parameters})


@dataclass(frozen=True)
class Sizes:
    """What one call sends the model, in characters."""

    tools: int = 0
    tools_chars: int = 0
    instructions_chars: int = 0
    history_chars: int = 0
    tool_results_chars: int = 0

    @classmethod
    def of(cls, messages: Sequence[dict], tools: Sequence[ToolSpec]) -> "Sizes":
        by_role = {"system": 0, "tool": 0, "history": 0}
        for message in attachments.without_data(list(messages)):
            role = message["role"] if message["role"] in by_role else "history"
            by_role[role] += _chars(message.get("content") or "")
            if message.get("tool_calls"):
                by_role[role] += _chars(message["tool_calls"])
        return cls(
            tools=len(tools),
            tools_chars=sum(map(_spec_chars, tools)),
            instructions_chars=by_role["system"],
            history_chars=by_role["history"],
            tool_results_chars=by_role["tool"],
        )


def record(who: str, answering: RouteCandidate, sizes: Sizes, tokens: Tokens | None) -> None:
    """The line of one call; none for a call that ended before its provider said what it spent."""
    if tokens is None:
        return
    logger.info(
        "assistant.turn.model_call caller=%s provider=%s model=%s tools=%s tools_chars=%s instructions_chars=%s "
        "history_chars=%s tool_results_chars=%s input_tokens=%s output_tokens=%s cache_read_tokens=%s "
        "cache_write_tokens=%s",
        who,
        answering.kind,
        answering.model,
        sizes.tools,
        sizes.tools_chars,
        sizes.instructions_chars,
        sizes.history_chars,
        sizes.tool_results_chars,
        tokens.input,
        tokens.output,
        tokens.cache_read,
        tokens.cache_write,
    )
