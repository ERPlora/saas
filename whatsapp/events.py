"""Events of whatsapp (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, in the transaction of the
write. Their payloads carry ids and counts, never what a customer wrote nor a number.

whatsapp reacts to no event of another app and has no live list of its own (no screen in the panel), so this module
only names its events.
"""

#: Meta's webhook was read: ``{"parked", "statuses", "verdicts", "discarded"}``.
WEBHOOK_INGESTED = "whatsapp.webhook.ingested"
#: A push to the Hub ended (taken, retried, refused or dropped): ``{"delivery_id", "outcome"}``.
DELIVERY_RECORDED = "whatsapp.delivery.recorded"

ALL = [WEBHOOK_INGESTED, DELIVERY_RECORDED]
