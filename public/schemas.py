"""Input and output schemas of the public web's operations (OpenAPI and the Hub's runtime)."""

from ninja import Schema


class AppReleaseIn(Schema):
    pass


class AppReleaseOut(Schema):
    """The version ``latest/`` publishes, or ``None`` when it could not be read (hub#400): never a
    number, never an invented version."""

    version: str | None
