"""The platform acting on WhatsApp: the permission of every command and the context the platform runs them with (the
Hub's doors, Meta's webhook, the tasks, the admin's actions). No account role holds ``whatsapp.manage``."""

from live.context import OperationContext, Scope, system_context

from whatsapp import queries

PERMISSION = queries.PERMISSION


def platform_context() -> OperationContext:
    """The platform acting on WhatsApp (the Hub's doors, Meta's webhook, the tasks, the admin's actions)."""
    return system_context(Scope("platform", "whatsapp"))
