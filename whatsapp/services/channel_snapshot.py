"""The business's WhatsApp in the Hub's snapshot (door 4): what a command changed of it reaches the Hub."""

from uuid import UUID

from hubs.services import hub_push


def announce_channel(hub_id: UUID) -> None:
    """The business's WhatsApp changed (its number, its month's usage, a template): its snapshot carries it under
    ``whatsapp`` (door 4) with a newer version, pushed after the COMMIT and retried by ``reconcile_hub_states``."""
    hub_push.bump_state(hub_id)
    hub_push.push_after_commit(hub_id)
