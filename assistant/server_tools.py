"""The tools erplora.com runs itself in a turn (ASSISTANT-G46): their result goes back to the model and the Hub never
sees the call; every other tool of the turn is the Hub's, which runs it.

- ``current_datetime``: today's date, time and weekday in UTC. Always offered.

The web search and the exchange rates of the old product wait for the ERP stage (PLAN §30, round 2026-10-22b): they
are not offered, whatever the environment holds.

``run`` never raises: a tool that fails gives the model an error to answer with (``{"error": …}``), so a turn never
fails because of one of these. They spend no message (they serve the same request of the person); their tokens add
up to the turn's. The model is asked again at most ``MAX_ROUNDS`` times in a turn (``assistant.turn.run``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from assistant.providers.base import ToolSpec

logger = logging.getLogger(__name__)

#: The rounds of our tools a turn may take before the model must answer (the old product's safety cap).
MAX_ROUNDS = 5


@dataclass(frozen=True)
class ServerTool:
    spec: ToolSpec
    call: Callable[[dict], Awaitable[dict]]


def error(message: str) -> dict:
    return {"error": message}


def arguments_of(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --- current_datetime --------------------------------------------------------------------------------------------


async def current_datetime(arguments: dict) -> dict:
    now = datetime.now(UTC).replace(microsecond=0)
    return {"utc": now.isoformat(), "date": now.date().isoformat(), "weekday": now.strftime("%A")}


TOOLS = {
    "current_datetime": ServerTool(
        ToolSpec(
            "current_datetime",
            "Today's date, time and weekday in UTC. Use it for anything that depends on today.",
            {"type": "object", "properties": {}},
        ),
        current_datetime,
    ),
}


def specs() -> list[ToolSpec]:
    """Our tools offered now."""
    return [tool.spec for tool in TOOLS.values()]


def is_server_tool(name: str) -> bool:
    return name in TOOLS


async def run(name: str, arguments: str) -> str:
    """The JSON result of our tool ``name``; never raises (an error is a result the model answers with)."""
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps(error(f"Unknown tool: {name}."))
    try:
        result = await tool.call(arguments_of(arguments))
    except Exception:
        logger.exception("assistant.server_tools.crashed tool=%s", name)
        result = error("The tool failed.")
    return json.dumps(result, ensure_ascii=False)
