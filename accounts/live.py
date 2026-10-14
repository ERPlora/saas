"""Live queries of accounts and the events that re-run them (plan 2026-10-13 §3, live data).

The scope is the account (PLAN-SAAS §6): a command notifies the channel of the account that ran it, so
The Account page's queries re-run at once in every tab of that account.
"""

from live.live_registry import live

from accounts import events

# A deleted account's own streams re-run at once and end (the account is gone).
live("accounts.profile.get", on=[events.PROFILE_UPDATED, events.PROFILE_DELETED, events.EMAIL_CHANGE_REQUESTED])
live("accounts.preferences.get", on=[events.PREFERENCES_UPDATED])
live("accounts.session.list", on=[events.SESSION_CLOSED])
live("accounts.apikey.list", on=[events.APIKEY_CREATED, events.APIKEY_REVOKED])
