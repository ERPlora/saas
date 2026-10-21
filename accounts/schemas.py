"""Schemas of the accounts operations. ``HubListOut`` is typed by hand in ``frontend/sdk-types.d.ts``.

The inputs of the Account page refuse a field they do not know (``extra="forbid"``): a 422 on it, never a silent
no-op (a client sending ``currency`` learns the panel has none).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.conf import settings
from django.utils.translation import gettext
from ninja import Schema
from pydantic import ConfigDict, Field, field_validator

#: The languages an account may choose (``settings.LANGUAGES``: English, the source, and Spanish).
Language = Literal[tuple(code for code, _ in settings.LANGUAGES)]
ThemeMode = Literal["system", "light", "dark"]


class StrictIn(Schema):
    model_config = ConfigDict(extra="forbid")


class HubListIn(Schema):
    pass


class HubOut(Schema):
    """A hub the account can enter: its slug, its host and the jump to it (``/hub-login/``)."""

    slug: str
    host: str
    url: str


class HubListOut(Schema):
    hubs: list[HubOut]


# --- Preferences ----------------------------------------------------------------------------------


class PreferencesGetIn(StrictIn):
    pass


class PreferencesOut(Schema):
    """Account → Preferences: the theme mode (``ThemeMode`` of the shell), the account's language and the
    two mail switches («Invoices and payments» mails have none: they are always sent)."""

    theme_mode: ThemeMode
    language: Language
    hub_alerts: bool
    marketing_emails: bool


class PreferencesUpdateIn(StrictIn):
    """Only what is sent changes (the page saves each control on its own)."""

    theme_mode: ThemeMode | None = None
    language: Language | None = None
    hub_alerts: bool | None = None
    marketing_emails: bool | None = None


# --- Profile --------------------------------------------------------------------------------------


class ProfileGetIn(StrictIn):
    pass


class ProfileOut(Schema):
    """Account → Profile. ``email_verified`` follows the invitations' rule (``queries.email_is_proven``);
    ``pending_email`` is the new address waiting for its link (``accounts.email.change``); ``photo`` is a data
    URL (``accounts.photo.upload``) or ``None`` (the panel paints the initials)."""

    id: UUID
    email: str
    email_verified: bool
    pending_email: str | None
    first_name: str
    last_name: str
    full_name: str
    photo: str | None
    has_password: bool
    date_joined: datetime


class ProfileUpdateIn(StrictIn):
    first_name: str = Field(max_length=150)
    last_name: str = Field(max_length=150)

    @field_validator("first_name")
    @classmethod
    def _first_name_given(cls, value: str) -> str:
        """The first name is required (audit 2 S-10: a blank one was saved and the panel lost its «Hello, Laura»);
        the last name may be cleared."""
        value = value.strip()
        if not value:
            raise ValueError(gettext("Write your first name."))
        return value


class ProfileDeleteIn(StrictIn):
    pass


class ProfileDeletedOut(Schema):
    deleted: bool


class EmailChangeIn(StrictIn):
    # RFC 5321's longest address; what fits the account is checked by the operation.
    email: str = Field(max_length=320)


class EmailVerifyIn(StrictIn):
    code: str = Field(max_length=16)


class EmailVerifyOut(Schema):
    """A wrong code is no error of the request: ``verified`` is false and ``attempts_left`` says how many tries
    the code has left (0: ask for a new one). Answering an error would roll back the try it spent."""

    verified: bool
    attempts_left: int
    profile: ProfileOut


# --- Photo ----------------------------------------------------------------------------------------


class PhotoUploadIn(StrictIn):
    """A JPEG, PNG or WebP as a ``data:`` URL (what the browser's file reader gives) or plain base64. What it may
    be is checked by the operation (``accounts.photos``), with one message per reason on ``image``."""

    image: str


class PhotoRemoveIn(StrictIn):
    pass


# --- Sessions -------------------------------------------------------------------------------------


#: The most sessions one page of ``accounts.session.list`` holds: well within a live result (``MAX_RESULT_BYTES``).
SESSION_PAGE_MAX = 100


class SessionListIn(StrictIn):
    """A page of the account's sessions: ``limit`` rows from ``offset``, this session first."""

    limit: int = Field(25, ge=1, le=SESSION_PAGE_MAX)
    offset: int = Field(0, ge=0)


class SessionRowOut(Schema):
    """A signed-in browser or app (``allauth.usersessions``). ``device`` is a code the panel names in the
    reader's language (``iphone``, ``ipad``, ``android``, ``windows``, ``chromeos``, ``mac``, ``linux`` or ``""``);
    ``browser`` a proper noun (``""`` inside the app, whose version is ``app_version``); the location is ``ip``."""

    id: int
    device: str
    browser: str
    browser_version: str
    app_version: str | None
    ip: str
    created_at: datetime
    last_seen_at: datetime
    is_current: bool


class SessionListOut(Schema):
    """One page of the sessions. ``total`` counts every session that still signs the account in; ``others``, those
    but this one (what «Close other sessions» ends), whichever page is asked."""

    rows: list[SessionRowOut]
    total: int
    limit: int
    offset: int
    others: int


class SessionCloseIn(StrictIn):
    id: int


class SessionCloseOthersIn(StrictIn):
    pass


class SessionsClosedOut(Schema):
    closed: int


# --- Account → Security → Two-factor authentication: the trusted browsers (ACCOUNTS-F17) -----------------------


class BrowserTrustGetIn(StrictIn):
    pass


class BrowserTrustRevokeIn(StrictIn):
    pass


class BrowserTrustOut(Schema):
    #: Until when this browser skips the app's code at sign-in («Trust this browser», ACCOUNTS-F05), or ``None``.
    trusted_until: datetime | None


# --- API keys -------------------------------------------------------------------------------------


class ApiKeyListIn(StrictIn):
    pass


class ApiKeyRowOut(Schema):
    """A key of the account, never its secret nor its hash: ``prefix`` is ``erps_live_`` and the first characters
    of the secret (how its owner tells it apart). A revoked key is no longer listed; an expired one is, marked."""

    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    expired: bool


class ApiKeyScopeOut(Schema):
    id: str
    label: str


class ApiKeyListOut(Schema):
    rows: list[ApiKeyRowOut]
    total: int
    #: What a key may be given, with what the panel says next to each (the dialog «New key»).
    scopes: list[ApiKeyScopeOut]


class ApiKeyCreateIn(StrictIn):
    name: str = Field(max_length=120)
    scopes: list[str] = Field(min_length=1)
    #: 30 or 90 days, or ``null`` for a key that does not expire.
    expires_in_days: Literal[30, 90] | None = 90

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(gettext("Give it a name: it is how you will tell your keys apart."))
        return value

    @field_validator("scopes")
    @classmethod
    def _known_scopes(cls, value: list[str]) -> list[str]:
        from accounts.models import UnknownScope, validate_scopes

        try:
            return validate_scopes(value)
        except UnknownScope:
            from accounts.models import API_KEY_SCOPES

            unknown = ", ".join(sorted(scope for scope in value if scope not in API_KEY_SCOPES))
            raise ValueError(gettext("Unknown permission: %(scopes)s.") % {"scopes": unknown}) from None


class ApiKeyCreatedOut(Schema):
    key: ApiKeyRowOut
    #: The whole key: shown this once and never again (only its hash is kept).
    secret: str


class ApiKeyRevokeIn(StrictIn):
    id: UUID
