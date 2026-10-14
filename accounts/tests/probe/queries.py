"""Reads of the probe API (see the package docstring)."""

from ninja import Schema


class ProbeIn(Schema):
    pass


class WhoOut(Schema):
    email: str | None


def who(ctx, data):
    return {"email": getattr(ctx.actor, "email", None)}
