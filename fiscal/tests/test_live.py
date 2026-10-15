"""The live query of fiscal and the events that re-run it (plan 2026-10-15; the panel's card of a business).

``fiscal.representation.status`` re-runs on the channel that changed the authorisation (the owner's for the
Hub's upload, the reviewer's for a decision) and on the channel of each owner and admin of the business, told
by ``fiscal.representation.changed`` (``services.tell_the_business``).
"""

from live.live_registry import live_registry
from live.operations import get

from fiscal import events


def fiscal_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("fiscal.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_state_of_the_authorisation_is_live():
    assert set(fiscal_queries()) == {"fiscal.representation.status"}


def test_it_needs_the_accounts_permission():
    op = get("fiscal.representation.status")

    assert (op.kind, op.permission) == ("query", "fiscal.view")


def test_every_event_cited_is_one_of_fiscal():
    for on in fiscal_queries().values():
        assert set(on) <= set(events.ALL)


def test_every_step_and_the_tell_re_run_it():
    for event in events.ALL:
        assert "fiscal.representation.status" in live_registry.affected([event]), event
