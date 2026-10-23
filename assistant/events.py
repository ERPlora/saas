"""Events of the assistant (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, in the transaction of
the write. Their payloads carry ids and counts, never a provider's key nor what a person wrote.

The assistant reacts to no event of another app and has no live list (no screen in the panel), so this module only
names its events. Those of a turn carry numbers only: never a conversation, a person nor a text.
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

#: A message of the allowance was taken for a turn: ``{"hub", "demo", "used", "limit"}`` (the business's id, or the
#: demo's address).
MESSAGE_CLAIMED = "assistant.message.claimed"
#: A turn that failed before answering gave its message back: ``{"hub", "demo", "used"}``.
MESSAGE_RELEASED = "assistant.message.released"
#: What a turn, an embedding or the voice spent was added: ``{"hub", "demo", "tokens_input", "tokens_output",
#: "tokens_embedding", "transcriptions", "speech_characters", "cost_usd"}``.
USAGE_RECORDED = "assistant.usage.recorded"

#: The report of an answer was mailed to support: ``{"hub", "demo", "reason"}`` (never the question, the answer nor
#: the comment).
REPORT_SENT = "assistant.report.sent"

ALL = [
    CREDENTIAL_SAVED,
    CREDENTIAL_DELETED,
    MODEL_SELECTED,
    POLICY_UPDATED,
    MODEL_TRIED,
    ENCRYPTION_ROTATED,
    MESSAGE_CLAIMED,
    MESSAGE_RELEASED,
    USAGE_RECORDED,
    REPORT_SENT,
]
