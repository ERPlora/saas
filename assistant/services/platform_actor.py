"""The platform acting on the gateway: the context its commands and the Hub's doors call the writes with."""

from live.context import OperationContext, Scope, system_context


def platform_context() -> OperationContext:
    """The platform acting on the gateway (its commands, the Hub's doors)."""
    return system_context(Scope("platform", "assistant"))
