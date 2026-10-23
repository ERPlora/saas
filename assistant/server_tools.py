"""The tools erplora.com runs itself in a turn (ASSISTANT-G46): the Hub never reaches the internet, so what needs it
(a web search, an exchange rate) is done here and its result goes back to the model; the Hub never sees the call.

- ``current_datetime``: today's date, time and weekday in UTC. Always offered.
- ``currency_rate``: the ECB's reference rate between two currencies, through Frankfurter (no key), kept an hour.
- ``web_search``: five results of the public web through Tavily, offered only with ``TAVILY_API_KEY``; the
  instructions then ask the model to cite source and date.

``run`` never raises: a tool that fails gives the model an error to answer with (``{"error": …}``), so a turn never
fails because of one of these. They spend no message (they serve the same request of the person); their tokens add
up to the turn's. The model is asked again at most ``MAX_ROUNDS`` times in a turn (``assistant.turn.run``).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.core.cache import cache

from assistant.providers.base import ToolSpec

logger = logging.getLogger(__name__)

#: The rounds of our tools a turn may take before the model must answer (the old product's safety cap).
MAX_ROUNDS = 5
TIMEOUT = httpx.Timeout(10.0)
WEB_SEARCH_RESULTS = 5
CURRENCY_CACHE_SECONDS = 60 * 60
CURRENCY = re.compile(r"[A-Z]{3}")

WEB_SEARCH_RULE = (
    "For facts that change over time (laws, prices, dates, news), use web_search and cite the source URL and its "
    "date; if you cannot verify a time-sensitive fact, say so instead of guessing."
)


@dataclass(frozen=True)
class ServerTool:
    spec: ToolSpec
    call: Callable[[dict], Awaitable[dict]]
    offered: Callable[[], bool] = lambda: True


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


# --- currency_rate -----------------------------------------------------------------------------------------------


def currency(value) -> str | None:
    code = str(value or "").strip().upper()
    return code if CURRENCY.fullmatch(code) else None


async def currency_rate(arguments: dict) -> dict:
    base, target = currency(arguments.get("from")), currency(arguments.get("to"))
    if base is None or target is None:
        return error("Give 'from' and 'to' as three-letter currency codes, e.g. EUR and USD.")
    try:
        amount = Decimal(str(arguments.get("amount", 1)))
    except InvalidOperation:
        return error("'amount' must be a number.")
    if base == target:
        rate, date = Decimal(1), datetime.now(UTC).date().isoformat()
    else:
        key = f"assistant:currency:{base}:{target}"
        found = await cache.aget(key)
        if found is None:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    response = await client.get(f"{settings.ASSISTANT_CURRENCY_URL}/latest", params={"from": base, "to": target})
                response.raise_for_status()
                body = response.json()
                found = {"rate": str(body["rates"][target]), "date": str(body["date"])}
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as problem:
                logger.warning("assistant.server_tools.currency_failed kind=%s", type(problem).__name__)
                return error("The exchange rate could not be read now.")
            await cache.aset(key, found, CURRENCY_CACHE_SECONDS)
        rate, date = Decimal(found["rate"]), found["date"]
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "from": base,
        "to": target,
        "rate": float(rate),
        "amount": float(amount) if amount != amount.to_integral_value() else int(amount),
        "converted": float(converted),
        "date": date,
        "source": "ECB",
    }


# --- web_search --------------------------------------------------------------------------------------------------


async def web_search(arguments: dict) -> dict:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return error("Give the 'query' to search for.")
    key = settings.TAVILY_API_KEY
    if not key:
        return error("The web search is not available.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{settings.ASSISTANT_WEB_SEARCH_URL}/search",
                json={"query": query, "max_results": WEB_SEARCH_RESULTS},
                headers={"Authorization": f"Bearer {key}"},
            )
        response.raise_for_status()
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError, AttributeError) as problem:
        status = getattr(getattr(problem, "response", None), "status_code", None)
        logger.warning("assistant.server_tools.web_search_failed kind=%s status=%s", type(problem).__name__, status)
        return error("The web search failed now.")
    return {
        "query": query,
        "results": [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "content": str(item.get("content") or ""),
                "published_date": str(item.get("published_date") or ""),
            }
            for item in results[:WEB_SEARCH_RESULTS]
            if isinstance(item, dict)
        ],
    }


TOOLS = {
    "current_datetime": ServerTool(
        ToolSpec(
            "current_datetime",
            "Today's date, time and weekday in UTC. Use it for anything that depends on today.",
            {"type": "object", "properties": {}},
        ),
        current_datetime,
    ),
    "currency_rate": ServerTool(
        ToolSpec(
            "currency_rate",
            "Convert an amount between two currencies with the ECB's reference rate of the day.",
            {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "description": "Three-letter code, e.g. EUR."},
                    "to": {"type": "string", "description": "Three-letter code, e.g. USD."},
                    "amount": {"type": "number", "description": "The amount to convert (1 if not given)."},
                },
                "required": ["from", "to"],
            },
        ),
        currency_rate,
    ),
    "web_search": ServerTool(
        ToolSpec(
            "web_search",
            "Search the public web for facts that change over time and you cannot answer from the conversation or the "
            "business's tools: current laws, prices, dates, news. Never for the business's own data.",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for."}},
                "required": ["query"],
            },
        ),
        web_search,
        offered=lambda: bool(settings.TAVILY_API_KEY),
    ),
}


def specs() -> list[ToolSpec]:
    """Our tools offered now (the search only with its key)."""
    return [tool.spec for tool in TOOLS.values() if tool.offered()]


def is_server_tool(name: str) -> bool:
    return name in TOOLS


def search_offered() -> bool:
    return TOOLS["web_search"].offered()


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
