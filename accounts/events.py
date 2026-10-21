"""Events of accounts (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, cited by live.py.

accounts reacts to no event of another app, so this module only names its own.
"""

#: The names, the photo or the email changed.
PROFILE_UPDATED = "accounts.profile.updated"
#: The account was deleted: its own streams end at their next run (the account is gone).
PROFILE_DELETED = "accounts.profile.deleted"
#: A code went to a new address: the profile shows it waiting.
EMAIL_CHANGE_REQUESTED = "accounts.email.change_requested"
PREFERENCES_UPDATED = "accounts.preferences.updated"
#: One session or all the others were closed from Account → Security.
SESSION_CLOSED = "accounts.session.closed"
#: Every browser the account trusted (ACCOUNTS-F05) asks for the app's code again.
BROWSER_TRUST_REVOKED = "accounts.browser_trust.revoked"

APIKEY_CREATED = "accounts.apikey.created"
APIKEY_REVOKED = "accounts.apikey.revoked"

ALL = [
    PROFILE_UPDATED,
    PROFILE_DELETED,
    EMAIL_CHANGE_REQUESTED,
    PREFERENCES_UPDATED,
    SESSION_CLOSED,
    BROWSER_TRUST_REVOKED,
    APIKEY_CREATED,
    APIKEY_REVOKED,
]
