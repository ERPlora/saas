"""Schemas of base's operations. ``SessionMeOut`` mirrors ``SessionMe`` of packages/ui (shell/session.ts)
and hub-next's: one shell for both SPAs."""

from typing import Any, Literal

from ninja import Schema
from pydantic import Field


class SessionMeIn(Schema):
    pass


class SessionUser(Schema):
    id: str
    label: str
    # Shown under the name in the user menu; every SaaS account has one (it signs in with it).
    email: str


class SessionScope(Schema):
    kind: str
    key: str


class MenuItem(Schema):
    path: str
    label: str
    icon: str
    # The shell's own name (``SessionMenuItem.webOnly``): the entry sells, so the app surfaces leave
    # it out (PLAN-SAAS §3.6 point 6).
    webOnly: bool


class MenuGroup(Schema):
    id: str
    label: str
    items: list[MenuItem]


class AppState(Schema):
    label: str
    state: Literal["on", "activating", "off"]


class SessionPreferences(Schema):
    """What the account chose in Cuenta → Preferencias that the shell paints with (packages/ui
    ``ThemeMode``, shell/theme.ts; ``accounts.UserPreferences``)."""

    theme_mode: Literal["system", "light", "dark"]


class SessionMeOut(Schema):
    user: SessionUser | None
    scope: SessionScope
    permissions: list[str]
    menu: list[MenuGroup]
    apps: list[AppState]
    #: The language this answer speaks (the request's; on the panel, the account's: ``base.language``).
    language: str
    #: ``None`` without an account.
    preferences: SessionPreferences | None
    #: ``User.language``, the account's own; ``None`` without an account.
    account_language: str | None


# --- The panel's assistant (PLAN-SAAS §23; the Hub's ``base/schemas.py``, the same contract) -----------------------


class AssistantCallIn(Schema):
    """A tool the model asked for, as the gateway gave it: its id, its name (``hubs__business__create``) and its
    arguments as the model wrote them (JSON text)."""

    call_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    arguments: str = Field(default="{}", max_length=1_000_000)


class AssistantDecisionIn(Schema):
    """The person's answer to the card of the first pending write: ``accepted``, what it typed when the card asks to
    type (a word, or how many) and ``stop`` («Cancel all»: this write and the rest of the turn)."""

    call_id: str = Field(min_length=1, max_length=200)
    accepted: bool
    typed: str = Field(default="", max_length=200)
    stop: bool = False


class AssistantTurnIn(Schema):
    """A turn of the assistant: the whole conversation (the person's browser keeps it), the tools the model asked for
    that still wait (``pending``) with their ``continuation`` and the person's answer to the first one's card."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    continuation: str | None = Field(default=None, max_length=4096)
    pending: list[AssistantCallIn] = Field(default_factory=list, max_length=64)
    decision: AssistantDecisionIn | None = None


class AssistantExecutedOut(Schema):
    call_id: str
    name: str = Field(description="The operation («hubs.business.create»), or the tool's name when there was none.")
    app: str
    app_name: str = Field(
        description="Where it happened, in the person's language, as its card says it: the panel's screen "
        "(«Businesses»); empty when there was no operation."
    )
    screen: str = Field(
        default="",
        description="The panel's screen it happened on, by its key («businesses»), for the receipt to name it in the "
        "language it is read in.",
    )
    kind: Literal["query", "command", ""]
    outcome: Literal["ok", "error", "refused", "cancelled"]
    code: str


class AssistantMoneyOut(Schema):
    currency: str
    decimals: int


class AssistantFieldOut(Schema):
    name: str
    label: str
    kind: Literal["text", "money", "bool", "list", "object", "empty"]
    value: Any = None
    titled: bool = Field(
        default=False,
        description="Its label is the title its app wrote (a check, a table): the card calls it so over its own word "
        "for a datum it knows by its name.",
    )
    signed: bool = Field(
        default=False,
        description="An amount its app declares signed (a difference): written with its sign, «+» over.",
    )
    named: bool = Field(
        default=False,
        description="A list whose every item the server said in words (a record by its name, a moment, a value by its "
        "label, an amount): the card says its items; without it, how many it carries (`live.assistant.NAMED`).",
    )
    money: AssistantMoneyOut | None = Field(
        default=None,
        description="The currency of an amount of a preview, as its read answers it (an invoice's); none = the "
        "business's, the card's own.",
    )


class AssistantCardOut(Schema):
    operation: str
    app: str
    app_name: str
    action: str
    risk: Literal["normal", "high"]
    fields: list[AssistantFieldOut]
    count: int | None = None
    confirm_word: str = Field(description="What to type to confirm a dangerous write; empty for a normal one.")
    blocked: bool = Field(description="A dangerous write that names no record: not done from the chat.")
    money: AssistantMoneyOut | None = Field(default=None, description="The currency of its amounts (ERPlora's, euros).")
    preview: list[AssistantFieldOut] | None = Field(
        default=None,
        description="What a dangerous write will do, as the read its app declares answers it for this person; none "
        "when its app declares no preview.",
    )


class AssistantTurnOut(Schema):
    """The turn made ready (the route streams it, ``text/event-stream``): the tools' results to keep (``append``),
    what ran (``executed``), the card of the write that waits (``confirm``) with what still waits (``pending``), and
    what goes to the gateway (``messages``, ``tools``, ``instructions``, ``continuation``); ``stop``, why it goes no
    further (``assistant.too_many_steps``)."""

    messages: list[dict[str, Any]]
    append: list[dict[str, Any]]
    executed: list[AssistantExecutedOut]
    confirm: AssistantCardOut | None = None
    pending: list[AssistantCallIn]
    tools: list[dict[str, Any]]
    instructions: str
    continuation: str | None = None
    stop: str = ""


class AssistantUsageIn(Schema):
    """No input: the account's allowance of the month (the session's account)."""


class AssistantUsageOut(Schema):
    used: int
    limit: int = Field(description="Messages of the month of the account (``ASSISTANT_ACCOUNT_MESSAGES``).")
    resets_at: str | None = Field(None, description="When the allowance comes back (UTC): the first of next month.")
    #: Always false here: the panel's assistant is never a demo's (the Hub's reads the same shape).
    demo: bool


class AssistantReportIn(Schema):
    """A bad answer the person reports to ERPlora's team, with the limits of the gateway's ``report``: a long answer is
    reported whole."""

    message_id: str = Field(min_length=1, max_length=128)
    reason: Literal["incorrect", "harmful", "instructions", "other"]
    comment: str = Field(default="", max_length=20_000)
    question: str = Field(default="", max_length=200_000)
    answer: str = Field(min_length=1, max_length=200_000)


class AssistantReportOut(Schema):
    sent: bool
    duplicate: bool
