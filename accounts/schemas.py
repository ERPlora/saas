"""Schemas of the accounts operations. ``HubListOut`` is typed by hand in ``frontend/sdk-types.d.ts``."""

from ninja import Schema


class HubListIn(Schema):
    pass


class HubOut(Schema):
    """A hub the account can enter: its slug, its host and the jump to it (``/hub-login/``)."""

    slug: str
    host: str
    url: str


class HubListOut(Schema):
    hubs: list[HubOut]
