"""What a door answers is ``(status, body)``: the body of a 2xx, or the single error envelope."""

#: Meta's codes of a send it refused, by what the Hub is told (its 409 codes; any other is ``meta_rejected``).
WINDOW_CLOSED = frozenset({131047, 470})
RECIPIENT_BLOCKED = frozenset({131021, 131026, 131030, 131049, 131050})
NOT_CONNECTED = frozenset({10, 190, 200, 131031, 133010})
#: The business's permission expired or was withdrawn in Meta: only connecting the number again fixes it. Doors 5, 8
#: and 9 and the attachments (``media``, which reads it from here) say ``whatsapp.reconnect_needed`` and mark the
#: number so.
EXPIRED_PERMISSION = 190


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}
