"""Events of the assistant (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, in the transaction of
the write. Their payloads carry ids and counts, never a provider's key nor what a person wrote.

The assistant reacts to no event of another app and has no live list (no screen in the panel), so this module only
names its events.
"""

#: A provider's key was added or changed (``rotated``: another key was typed): ``{"provider", "credential", "rotated"}``.
CREDENTIAL_SAVED = "assistant.credential.saved"
#: A provider's key was deleted: ``{"provider", "credential"}``.
CREDENTIAL_DELETED = "assistant.credential.deleted"

ALL = [
    CREDENTIAL_SAVED,
    CREDENTIAL_DELETED,
]
