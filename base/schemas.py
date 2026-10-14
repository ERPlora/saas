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


class SessionMeOut(Schema):
    user: SessionUser | None
    scope: SessionScope
    permissions: list[str]
    menu: list[MenuGroup]
    apps: list[AppState]
    language: str
