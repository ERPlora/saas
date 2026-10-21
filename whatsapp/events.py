"""Events of whatsapp (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, in the transaction of the
write. Their payloads carry ids and counts, never what a customer wrote nor a number.

whatsapp reacts to no event of another app and has no live list of its own (no screen in the panel), so this module
only names its events.
"""

#: Meta's webhook was read: ``{"parked", "statuses", "verdicts", "discarded"}``.
WEBHOOK_INGESTED = "whatsapp.webhook.ingested"
#: A push to the Hub ended (taken, retried, refused or dropped): ``{"delivery_id", "outcome"}``.
DELIVERY_RECORDED = "whatsapp.delivery.recorded"

#: A send of the Hub ended at Meta (sent, unknown or released): ``{"send_id", "outcome"}``.
MESSAGE_RECORDED = "whatsapp.message.recorded"
#: What was kept of a customer's number for a business was forgotten (door 6): ``{"hub_id", "rows"}``.
MESSAGE_ERASED = "whatsapp.message.erased"

#: Meta took a template the Hub asked to register (door 8): ``{"hub_id", "meta_id", "status"}``.
TEMPLATE_REGISTERED = "whatsapp.template.registered"
#: A template left the mirror, deleted at Meta (door 9) or no longer there: ``{"hub_id"}``.
TEMPLATE_FORGOTTEN = "whatsapp.template.forgotten"
#: The mirror of a business's templates was read again from Meta: ``{"hub_id", "complete"}``.
TEMPLATES_SYNCED = "whatsapp.template.synced"
#: Meta refused the business's permission: only connecting again fixes it: ``{"hub_id"}``.
NUMBER_RECONNECT_NEEDED = "whatsapp.number.reconnect_needed"
#: The daily retention forgot what it no longer keeps: ``{"deliveries", "never_taken", "sends", "registrations"}``.
RETENTION_PURGED = "whatsapp.retention.purged"

ALL = [
    WEBHOOK_INGESTED,
    DELIVERY_RECORDED,
    MESSAGE_RECORDED,
    MESSAGE_ERASED,
    TEMPLATE_REGISTERED,
    TEMPLATE_FORGOTTEN,
    TEMPLATES_SYNCED,
    NUMBER_RECONNECT_NEEDED,
    RETENTION_PURGED,
]
