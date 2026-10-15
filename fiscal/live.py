"""The live query of fiscal and the events that re-run it after the COMMIT (plan 2026-10-15).

The scope is the account (PLAN-SAAS §6): each step of an authorisation notifies the channel that took it (the
owner's for the Hub's upload, the reviewer's for a decision), and ``fiscal.representation.changed`` reaches
each owner and admin of the business (``services.tell_the_business``), so the card on their page re-runs at
once.
"""

from live.live_registry import live

from fiscal import events

live("fiscal.representation.status", on=[*events.REPRESENTATION, events.REPRESENTATION_CHANGED])
