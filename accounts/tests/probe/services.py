"""Writes of the probe API (see the package docstring)."""


def touch(ctx, data):
    return {"email": getattr(ctx.actor, "email", None)}
