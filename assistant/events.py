"""Events of the assistant (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, in the transaction of
the write. Their payloads carry ids and counts, never a provider's key nor what a person wrote.

The assistant reacts to no event of another app and has no live list (no screen in the panel), so this module only
names its events.
"""

#: A provider's key was added or changed (``rotated``: another key was typed): ``{"provider", "credential", "rotated"}``.
CREDENTIAL_SAVED = "assistant.credential.saved"
#: A provider's key was deleted: ``{"provider", "credential"}``.
CREDENTIAL_DELETED = "assistant.credential.deleted"
#: A provider's models were chosen: ``{"provider", "created", "kept", "deleted", "protected"}``.
MODEL_SELECTED = "assistant.model.selected"
#: The model that answers or its fallback changed: ``{"active_model", "fallback_model"}`` (ids or ``None``).
POLICY_UPDATED = "assistant.policy.updated"
#: A member of the staff tried a model from the admin: ``{"model", "prompt_chars", "tools"}`` (never the message).
MODEL_TRIED = "assistant.model.tried"
#: Every value kept with the key of the credentials was written again with the current one:
#: ``{"rotated", "current", "unreadable"}`` (counts).
ENCRYPTION_ROTATED = "assistant.encryption.rotated"

ALL = [
    CREDENTIAL_SAVED,
    CREDENTIAL_DELETED,
    MODEL_SELECTED,
    POLICY_UPDATED,
    MODEL_TRIED,
    ENCRYPTION_ROTATED,
]
