"""The live queries of accounts and the events that re-run them (plan 2026-10-13 §3, live data).

The scope is the account (PLAN-SAAS §6): a command notifies the channel of the account that ran it, so
The Account page's queries re-run at once in every tab of that account.
"""

from live.live_registry import live_registry
from live.operations import get

from accounts import events

LIVE = {"accounts.profile.get", "accounts.preferences.get", "accounts.session.list", "accounts.apikey.list"}


def accounts_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("accounts.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_pages_of_cuenta_are_live():
    assert set(accounts_queries()) == LIVE


def test_every_live_query_needs_the_accounts_permission():
    for name in LIVE:
        op = get(name)
        assert (op.kind, op.permission) == ("query", "accounts.view"), name


def test_every_event_cited_is_one_of_accounts():
    for on in accounts_queries().values():
        assert set(on) <= set(events.ALL)
