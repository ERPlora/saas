"""The assistant of erplora.com's own panel (plan 2026-10-30-asistente-saas §4; PLAN-SAAS §23, PLAN §36): the same
assistant as the Hub's, with the SaaS's own operations as its tools, for the signed-in account.

The mechanics are ``live.assistant``'s, shared with the Hub (its catalogue by ``ai=``, the relevance, the card of a
write and its word, the tool run as the person); this module gives them the panel's own:

- **Its tools** (``catalog``) are the operations of the SaaS's apps (all of them platform apps, always on) whose
  ``ai=`` is an ``AI(...)`` that this account may run; never the assistant's own. Where nothing is sold (the app's
  account surface, ``base.surface``) neither are the store's (``WEB_ONLY``). A turn offers only the few of what was
  asked (``relevant``, in the panel's words: ``SYNONYMS``, ``HOWTO``), the account's businesses and the documentation
  search first (``ALWAYS``). The same tools of a role (``role_catalog``) are what the assistant's QA reads
  (``export_assistant_catalog``), each with what people type to ask for it (its ``asks``,
  ``base/tests/test_assistant_asks.py``).
- **A write never runs without the person's yes**: its card (``card``) names where it happens by the panel's screen
  (``screen``) and a business by its name (``PanelWords``), never by its id.
- **The gateway is in this process** (``assistant.turn``): no ``/internal`` call nor signature. ``turn_frames``
  streams the turn as the Hub's panel reads it (``executed``, ``confirm``, ``text``, ``usage``, ``error``, ``done``);
  what the gateway refuses before the model (the account's allowance, its budget of turns, a conversation too big,
  no model) is the stream's first ``error`` frame, as the Hub's ``_refusal``. The account's messages are its own
  (``Caller(user_id=…)``, ``ASSISTANT_ACCOUNT_MESSAGES``); nothing of the conversation is kept.
"""

import json
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import aclosing
from dataclasses import dataclass, field
from functools import cache
from types import SimpleNamespace
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, StreamingHttpResponse
from django.utils import translation
from django.utils.translation import get_language_info, gettext
from live import assistant as shared
from live.assistant import LEFT_OUT, MAX_ROUNDS, MAX_TOOLS, PlainWords, ToolOutcome, tool_spec  # noqa: F401
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import Operation
from live.operations import get as get_operation

from assistant import queries as gateway_queries
from assistant import turn as gateway
from assistant.schemas import Caller
from base import navigation
from base.operations import ACCOUNT_ROLE
from base.surface import ACCOUNT, account_surface

logger = logging.getLogger(__name__)

#: Always offered when the account may read them: its businesses (the first thing asked of the panel) and the search in
#: ERPlora's documentation, which the instructions send every how-to question to and whose words a question rarely
#: shares (ASSISTANT-F27).
ALWAYS = ("hubs.business.list", "assistant.docs.search")
#: What a word names in the panel and nowhere else (``live.assistant.relevant``'s ``synonyms``), for a turn and the
#: assistant's QA. A person's own, other, new or old «tienda» is one of their businesses, as a «shop» is: the panel's
#: Store is one and is «la tienda» alone (its screen's name, ``app_words``), and the English panel calls it «Store».
#: «Cuenta» needs no group here: it is the Account screen's name, so it already names the person's account.
SYNONYMS = (
    ("negocio", "business", "shop", "mi tienda", "mis tiendas", "nuestra tienda", "otra tienda", "nueva tienda",
     "tienda nueva", "tienda vieja"),
)
#: The tool a how-to question («how do I…?», «¿cómo invito…?») is for (``relevant``'s ``howto``): the search in
#: ERPlora's documentation, which then reaches it on being such a question, not only on being always offered.
HOWTO = ("assistant.docs.search",)
#: The panel's screen where each app's actions are done; the store's of billing are the store's (``screen``).
SCREEN_OF_APP = {"hubs": "businesses", "accounts": "account", "billing": "billing", "apps": "store"}
#: What billing does in the store: the catalogue, its promo codes and changing a plan.
STORE_ENTITIES = frozenset({"store", "promo", "plan"})
#: The panel's roles, as the assistant's QA names them (docs plan 2026-10-31 §4): every signed-in account has the one
#: role ``account``. Who may act on a business is decided inside each operation, so an owner's tools and an
#: employee's are the same.
ROLES = (ACCOUNT_ROLE,)
#: Where the panel is used: the web, and the app's account surface, which sells nothing (``sells_nothing``).
SURFACES = ("web", "app")


# ── Tools ────────────────────────────────────────────────────────────────────────────────────────────────────────


def screen(op: Operation) -> str:
    """The key of the panel's screen (``base.navigation``) where ``op`` is done: an app's, or the store's; none (``""``)
    for the documentation search, which reads ERPlora's help on no screen of the panel."""
    app, entity, _ = op.name.split(".")
    if app == "assistant":
        return ""
    if app == "billing" and entity in STORE_ENTITIES:
        return "store"
    return SCREEN_OF_APP.get(app, "account")


def screen_name(key: str) -> str:
    """The screen ``key`` as the panel's menu names it, in the active language; the help for no screen."""
    if not key:
        return gettext("Help")
    return next(str(nav.label) for nav in navigation.NAVIGATION if nav.id == key)


def sells_nothing(request: HttpRequest | None) -> bool:
    """Whether ``request`` comes from where nothing is sold (the app's account surface, PLAN-SAAS §3.6 point 6)."""
    return request is not None and hasattr(request, "session") and account_surface(request) == ACCOUNT


def is_tool(op: Operation) -> bool:
    """Whether ``op`` is a tool of the panel's assistant: its ``ai=`` says so and it is not the assistant's own."""
    return shared.is_tool(op) and not op.name.startswith("base.assistant.")


def granted(ctx: OperationContext, *, sells: bool) -> dict[str, Operation]:
    """The tools ``ctx``'s permissions grant, by name, in name order; none of the store's unless where it ``sells``."""
    labels = {config.label for config in all_live_app_configs()}
    tools = shared.catalog(ctx, active_labels=labels)
    return {
        name: op for name, op in tools.items() if is_tool(op) and (sells or screen(op) not in navigation.WEB_ONLY)
    }


def catalog(ctx: OperationContext) -> dict[str, Operation]:
    """The tools of ``ctx``'s account, by name, in name order; where nothing is sold, none of the store's."""
    if ctx.actor is None:
        return {}
    return granted(ctx, sells=not sells_nothing(getattr(ctx, "request", None)))


def role_catalog(role: str, *, surface: str = "web") -> dict[str, Operation]:
    """What ``catalog`` gives every signed-in account of ``role`` (``ROLES``) on ``surface`` (``SURFACES``): the
    catalogue the assistant's QA with the real model reads (``export_assistant_catalog``)."""
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}: the panel's are {', '.join(ROLES)}.")
    if surface not in SURFACES:
        raise ValueError(f"Unknown surface {surface!r}: the panel's are {', '.join(SURFACES)}.")
    ctx = OperationContext(
        scope=Scope("user", role),
        actor=None,
        permissions=permissions_for_role(all_live_app_configs(), role),
        language=settings.LANGUAGE_CODE,
    )
    return granted(ctx, sells=surface == "web")


@cache
def app_words(label: str, language: str) -> frozenset[str]:
    """How a person names the app ``label``: its own words (``live.assistant.app_words``) and the panel's screens
    where its actions are done, in English and in ``language``."""
    words = set(shared.app_words(label, language))
    keys = {key for app, key in SCREEN_OF_APP.items() if app == label} | ({"store"} if label == "billing" else set())
    for lang in ("en", language):
        with translation.override(lang):
            for key in keys:
                words |= shared.stems(screen_name(key))
    return frozenset(words)


def relevant(tools: dict[str, Operation], texts: Iterable[str], language: str) -> list[Operation]:
    """The tools of what ``texts`` ask, best first, at most ``MAX_TOOLS``: ``ALWAYS`` first, in the panel's words
    (``SYNONYMS``) and with how-to questions sent to the documentation search (``HOWTO``)."""
    return shared.relevant(tools, texts, language, always=ALWAYS, app_words=app_words, synonyms=SYNONYMS, howto=HOWTO)


# ── The card of a write in the panel's words ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PanelWords(PlainWords):
    """``live.assistant.PlainWords`` (amounts in euros, moments at UTC) with a business named by its name, as the
    account's own list answers it (``names``: id → name), and where it happens by the panel's screen."""

    names: dict[str, str] = field(default_factory=dict)

    def reference(self, value: Any, prop: dict) -> Any:
        return self.names.get(str(value), LEFT_OUT)

    def app_name(self) -> str:
        return screen_name(screen(self.op))


def business_names(ctx: OperationContext) -> dict[str, str]:
    """The account's businesses by id → name, read as the account (``hubs.business.list``); none if it fails."""
    failure, answer = shared.run(ctx, get_operation("hubs.business.list"), {"limit": 100})
    if failure is not None:
        return {}
    return {str(row.id): row.name for row in answer.rows}


def card(op: Operation, arguments: dict, ctx: OperationContext) -> dict:
    """What the account sees before the write ``op`` runs with ``arguments`` (``live.assistant.card``)."""
    return shared.card(op, arguments, ctx.language, PanelWords(op, ctx.language, names=business_names(ctx)))


# ── The instructions of a turn ───────────────────────────────────────────────────────────────────────────────────


def account_label(user: Any) -> str:
    """The account as the instructions name it: its name and email, or its email."""
    name = user.get_full_name()
    return f"{name} ({user.email})" if name else user.email


def screens(ctx: OperationContext, request: HttpRequest | None = None) -> dict[str, str]:
    """The panel's screens the assistant may link, by path, as its menu names them in ``ctx``'s language; where
    nothing is sold, not the store."""
    request = request if request is not None else getattr(ctx, "request", None)
    unsold = sells_nothing(request)
    with translation.override(ctx.language):
        return {
            nav.path: str(nav.label) for nav in navigation.NAVIGATION if not (unsold and nav.id in navigation.WEB_ONLY)
        }


def instructions(*, language: str, account: str, screens: dict[str, str], docs: bool = False) -> str:
    """The system message of every turn (the gateway's only one): who it serves, in which language, the rules of its
    tools and money, and the screens it may link. ``docs``: the documentation search is among its tools."""
    try:
        language_name = get_language_info(language)["name"]
    except KeyError:
        language_name = language
    links = "\n".join(f"- [{name}]({path})" for path, name in screens.items())
    how_to = (
        "- For how-to questions about ERPlora, search its documentation with `assistant__docs__search` and cite it.\n"
        if docs
        else ""
    )
    return f"""You are the assistant of erplora.com's panel for the account «{account}»: its businesses, what it pays
ERPlora and its account. Answer in {language_name}, short and plain. Use Markdown: bold, lists and tables.

- Only help with this account, its businesses as erplora.com manages them, and ERPlora. For anything that happens
  inside a business (sales, products, people on the till), say to open the business and ask its assistant there.
  To anything else, say kindly that you only help with ERPlora, in one sentence, and do not answer it.
- Read before you answer: use the tools to look up businesses, plans, invoices and ids. Never invent a record, an
  id or a date, and never invent a plan, a price or an invoice: if no tool returned it, say you do not know.
{how_to}- To change something, call its tool: the person sees a card and confirms it before it runs. If the tool comes back
  «not confirmed» or with an error, nothing changed: say so, and never say it was done.
- Amounts: a datum whose name ends in `_cents` is in cents of its currency (euros unless it says another): write it
  in that currency with two decimals. Plan prices are net, VAT excluded.
- When the person should go to a screen, link it with its path, only one of these:
{links}
- If something cannot be done from here (you have no tool for it), say on which screen it is done."""


# ── What the tools wait on the network for, before the turn's transaction ───────────────────────────────────────


#: The documentation search: the fingerprint of its question comes from the provider (ASSISTANT-F27).
DOCS_SEARCH = "assistant.docs.search"


def searched_questions(pending: Iterable[Any]) -> list[str]:
    """The questions of the documentation searches among the tools the model asked for (their ``query``)."""
    name = shared.tool_name(DOCS_SEARCH)
    questions = []
    for call in pending:
        if call.name != name:
            continue
        try:
            arguments = json.loads(call.arguments or "{}")
        except ValueError:
            continue
        query = arguments.get("query") if isinstance(arguments, dict) else None
        if isinstance(query, str):
            questions.append(query)
    return questions


async def prepare(data: Any) -> None:
    """What the turn's tools wait on the network for, done before ``base.assistant.turn`` opens its transaction: the
    fingerprints of the documentation searches the model asked for. A connection never waits on the provider inside
    a transaction; what cannot be prepared, the search itself refuses."""
    await gateway_queries.prepare_questions(searched_questions(data.pending))


# ── The turn, through the gateway in this process ────────────────────────────────────────────────────────────────


def sse(frame: dict) -> bytes:
    """One frame of the panel's turn as a server-sent event."""
    return gateway.sse(frame).encode()


def refusal(refused: gateway.Refused) -> dict:
    """A turn the gateway did not take, as the Hub's panel reads it (the Hub's ``_refusal``)."""
    if refused.code == "assistant.quota_exceeded":
        return {
            "type": "error",
            "code": refused.code,
            **{key: refused.extra.get(key) for key in ("used", "limit", "resets_at", "demo")},
        }
    if refused.status == 429:
        return {"type": "error", "code": "assistant.rate_limited", "retry_after": int(refused.retry_after or 60)}
    if refused.status == 413:
        return {"type": "error", "code": "assistant.too_large"}
    return {"type": "error", "code": "assistant.unavailable", "retriable": True}


def _assistant_message(text: str, calls: list[dict]) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {
                "id": call["call_id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": call["arguments"]},
            }
            for call in calls
        ]
    return message


async def gateway_frames(request: HttpRequest, caller: Caller, plan: dict) -> AsyncIterator[dict]:
    """A turn through the gateway, as the panel's frames: ``text`` piece by piece, ``usage``, an ``error``, and
    ``done`` with what the browser keeps (``append``), the tools the model asked for (``pending``) and their
    ``continuation``. One turn of the account's budget (the Hub's door's, ``ASSISTANT_TURN_RATELIMIT``) and, unless it
    answers the tools the model asked for, one message of its allowance. A refusal is a lone ``error``."""
    data = SimpleNamespace(
        messages=plan["messages"],
        instructions=plan["instructions"],
        tools=plan["tools"],
        continuation=plan["continuation"],
    )
    try:
        await sync_to_async(gateway.spend)(request, "turn", settings.ASSISTANT_TURN_RATELIMIT, caller)
        started = await gateway.start(caller, data)
    except gateway.Refused as refused:
        yield refusal(refused)
        return
    except Exception:
        logger.exception("base.assistant.turn_not_started")
        yield {"type": "error", "code": "assistant.unavailable", "retriable": True}
        return
    text: list[str] = []
    calls: list[dict] = []
    token: str | None = None
    finished = failed = False
    async with aclosing(gateway.frames(started)) as framed:
        async for frame in framed:
            if frame == "[DONE]":
                finished = True
                continue
            kind = frame.get("type")
            if kind == "text_delta" and frame.get("text"):
                text.append(str(frame["text"]))
                yield {"type": "text", "text": str(frame["text"])}
            elif kind == "function_call":
                calls.append(
                    {
                        "call_id": str(frame.get("call_id")),
                        "name": str(frame.get("name")),
                        "arguments": str(frame.get("arguments") or "{}"),
                    }
                )
            elif kind == "response":
                token = frame.get("continuation") or None
            elif kind == "usage":
                yield {"type": "usage", **{key: frame.get(key) for key in ("used", "limit", "resets_at", "demo")}}
            elif kind == "error":
                failed = True
                yield {"type": "error", "code": "assistant.provider_failed", "retriable": bool(frame.get("retriable"))}
    said = "".join(text)
    if failed or not finished:
        yield {
            "type": "done",
            "append": [_assistant_message(said, [])] if said else [],
            "pending": [],
            "continuation": None,
        }
        return
    yield {"type": "done", "append": [_assistant_message(said, calls)], "pending": calls, "continuation": token}


async def turn_frames(request: HttpRequest, caller: Caller, plan: dict) -> AsyncIterator[bytes]:
    """The answer of ``base.assistant.turn`` (``plan``, the operation's output) as the panel reads it: what ran
    (``executed``), then the card of a write that waits (``confirm``), why it stops (``assistant.too_many_steps``) or
    the gateway's turn; the closing ``done`` always carries the tools' results to keep before the model's message."""
    for row in plan["executed"]:
        yield sse({"type": "executed", **row})
    if plan["confirm"] is not None:
        yield sse({"type": "confirm", "card": plan["confirm"], "call": plan["pending"][0]})
        yield sse(
            {"type": "done", "append": plan["append"], "pending": plan["pending"], "continuation": plan["continuation"]}
        )
        return
    if plan["stop"]:
        yield sse({"type": "error", "code": plan["stop"]})
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None})
        return
    closed = False
    async with aclosing(gateway_frames(request, caller, plan)) as framed:
        async for frame in framed:
            if frame["type"] == "done":
                closed = True
                frame = {**frame, "append": [*plan["append"], *frame["append"]]}
            yield sse(frame)
    if not closed:
        yield sse({"type": "done", "append": plan["append"], "pending": [], "continuation": None})


def turn_response(request: HttpRequest, plan: dict) -> StreamingHttpResponse:
    """The streamed answer of a turn of the session's account: never cached nor held by a proxy."""
    caller = Caller(user_id=request.user.pk)
    response = StreamingHttpResponse(
        turn_frames(request, caller, plan), content_type="text/event-stream; charset=utf-8"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
