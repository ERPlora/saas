"""Signals accounts sends for the apps that depend on it (``accounts ← hubs ← billing``: accounts never
imports them, PLAN-SAAS §3.6 point 16).

Both are sent inside the command's transaction with ``user_id`` (the account's UUID): a receiver that
queues work (``hubs.services.revoke_after_commit``) commits or rolls back with the command.
"""

from django.dispatch import Signal

#: The account's sessions in the SaaS ended: closed from Account → Security («Sign out», «Close the
#: other sessions», allauth's ``auth/sessions``) or the account deleted. Its sessions in every business must
#: end too (PLAN-SAAS §2.1: ``POST /internal/sessions/revoke {user_id}``, OIDC's back-channel logout).
sessions_ended = Signal()

#: The account is about to be deleted: its memberships of businesses go with it (``HubMember`` cascades), so
#: whoever keeps a copy of them (the Hub's snapshot) learns it here, while they can still be read.
account_deleting = Signal()
