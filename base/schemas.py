"""Schemas of base's operations. ``SessionMeOut`` mirrors ``SessionMe`` of packages/ui (shell/session.ts)
and hub-next's: one shell for both SPAs."""

from typing import Literal

from ninja import Schema


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
