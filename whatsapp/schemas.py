"""The inputs and outputs of whatsapp's operations (``services.py``, ``queries.py``) and of its doors.

The doors' bodies are the Hub's contract (``hub/apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el SaaS»): the
same fields, codes and answers the Hub already sends and reads; nothing here renames them.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field, SecretStr, StringConstraints, model_validator

#: The Hub's ``hub``: the business's slug in phase 1 (its UUID in phase 2).
HubRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
#: An international number, with or without ``+`` (the Hub's ``INTERNATIONAL``).
International = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[1-9]\d{6,14}$")]
#: The ``Idempotency-Key`` of a send (the Hub's ``client_message_id``) or of a template's registration.
IdempotencyKey = Annotated[str, StringConstraints(min_length=1, max_length=255)]


class IngestIn(Schema):
    payload: dict = Field(description="Meta's webhook as it arrived (its signature already checked).")


class IngestOut(Schema):
    hub_ids: list[UUID] = Field(description="The businesses something new was parked for.")
    template_hubs: list[UUID] = Field(
        default_factory=list, description="The businesses whose templates Meta changed and should be read again."
    )
    parked: int = 0
    statuses: int = 0
    verdicts: int = 0
    discarded: int = 0


class ClaimIn(Schema):
    hub_ids: list[UUID] | None = Field(None, description="Only these businesses; all when missing.")
    limit: int = Field(50, ge=1, le=500)


class ClaimedDelivery(Schema):
    id: UUID
    kind: Literal["message", "status"]
    revision: int
    received_at: datetime
    body: dict = Field(description="The door's body, ``hub`` included.")


class ClaimOut(Schema):
    deliveries: list[ClaimedDelivery]


class RecordIn(Schema):
    id: UUID
    revision: int = Field(ge=0)
    outcome: Literal["delivered", "retry", "refused", "drop"]
    error: str = Field("", max_length=300)


class RecordOut(Schema):
    outcome: str


# --- Door 5: send ---------------------------------------------------------------------------------------------


class TemplateRef(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)] = "es"
    variables: list[Annotated[str, StringConstraints(max_length=1024)]] = Field(default_factory=list, max_length=100)


class SendIn(Schema):
    """Door 5's body: ``{"hub", "to", "type": "text", "text"}`` or ``{"hub", "to", "type": "template", "template"}``."""

    hub: HubRef
    to: International
    type: Literal["text", "template"]
    text: Annotated[str, StringConstraints(max_length=4096)] | None = None
    template: TemplateRef | None = None

    @model_validator(mode="after")
    def _one_kind(self):
        if self.type == "text" and (not (self.text or "").strip() or self.template is not None):
            raise ValueError("A text message carries a non-empty text and no template.")
        if self.type == "template" and (self.template is None or self.text is not None):
            raise ValueError("A template message carries its template and no text.")
        return self


class SendClaimIn(Schema):
    hub: HubRef
    key: IdempotencyKey
    template_name: str = ""
    template_language: str = ""


class SendClaimOut(Schema):
    #: ``claimed``: this call sends it now; ``sent``: it went before (``wa_message_id``, maybe empty when Meta gave
    #: none); ``in_flight``: another call is sending it; ``refused``: it does not leave (``status``, ``code``).
    outcome: Literal["claimed", "sent", "in_flight", "refused"]
    status: int = 0
    code: str = ""
    message: str = ""
    send_id: UUID | None = None
    hub_id: UUID | None = None
    phone_number_id: str = ""
    token: SecretStr | None = None
    wa_message_id: str = ""


class SendRecordIn(Schema):
    send_id: UUID
    #: ``sent``: Meta accepted it (``wa_message_id``, empty if Meta gave none); ``unknown``: no answer came back (the
    #: place stays taken); ``released``: Meta refused it or was not reached: nothing left, the place is freed.
    outcome: Literal["sent", "unknown", "released"]
    wa_message_id: str = Field("", max_length=255)
    needs_reconnect: bool = False


class SendRecordOut(Schema):
    outcome: str


# --- Door 6: erase --------------------------------------------------------------------------------------------


class EraseIn(Schema):
    hub: HubRef
    phone: International
    wa_message_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=10000
    )


class EraseOut(Schema):
    erased: bool


# --- Doors 8 and 9: templates ---------------------------------------------------------------------------------


class TemplateIn(Schema):
    """Door 8's body: a template to register at Meta (new, or an edit of its ``meta_id``). The fields are loose on
    purpose: Meta's rules (name, lengths, variables, buttons) are checked by ``templates.check``, which says which
    one failed in the 409 ``whatsapp.template_invalid`` the Hub shows, instead of a bare 422."""

    hub: HubRef
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=600)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
    header: Annotated[str, StringConstraints(max_length=2000)] = ""
    body: Annotated[str, StringConstraints(max_length=8192)] = ""
    body_examples: list[Annotated[str, StringConstraints(max_length=1024)]] = Field(
        default_factory=list, max_length=100
    )
    footer: Annotated[str, StringConstraints(max_length=2000)] = ""
    buttons: list[dict] = Field(default_factory=list, max_length=20)
    meta_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = ""


class TemplateOut(Schema):
    meta_id: str
    status: str


class TemplateDeleteIn(Schema):
    """Door 9's body: that one template, in that language, at Meta."""

    hub: HubRef
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    meta_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = ""


class TemplateDeleteOut(Schema):
    deleted: bool


class TemplateClaimIn(Schema):
    hub: HubRef
    key: IdempotencyKey


class TemplateClaimOut(Schema):
    #: ``claimed``: this call registers it now (``waba_id``, ``token``); ``done``: Meta took it before (its
    #: ``meta_id`` and ``status``).
    outcome: Literal["claimed", "done"]
    submission_id: UUID | None = None
    hub_id: UUID | None = None
    waba_id: str = ""
    token: SecretStr | None = None
    meta_id: str = ""
    status: str = ""


class TemplateRecordIn(Schema):
    submission_id: UUID
    #: ``done``: Meta took it (``mirror``: the template as the mirror keeps it); ``released``: it was not taken, and
    #: the key is free to try again.
    outcome: Literal["done", "released"]
    mirror: dict = Field(default_factory=dict)


class TemplateRecordOut(Schema):
    outcome: str


class TemplateAccountIn(Schema):
    """The business (by the Hub's ``hub`` or by its id) whose account at Meta is asked, and the template whose
    ``meta_id`` the mirror knows (optional)."""

    hub: HubRef | None = None
    hub_id: UUID | None = None
    name: str = ""
    language: str = ""

    @model_validator(mode="after")
    def _one_business(self):
        if (self.hub is None) == (self.hub_id is None):
            raise ValueError("Name the business by hub or by hub_id.")
        return self


class TemplateAccountOut(Schema):
    hub_id: UUID
    waba_id: str
    token: SecretStr
    meta_id: str = ""


class TemplateForgetIn(Schema):
    hub_id: UUID
    name: str
    language: str


class TemplateForgetOut(Schema):
    forgotten: bool


class TemplateSyncIn(Schema):
    hub_id: UUID
    #: Meta's templates as the mirror keeps them (``templates.from_meta``).
    items: list[dict]
    #: Whether Meta's list came whole: only then is what it lacks deleted from the mirror.
    complete: bool


class TemplateSyncOut(Schema):
    changed: bool


class ReconnectIn(Schema):
    hub_id: UUID


class ReconnectOut(Schema):
    changed: bool


# --- The renewal of Meta's permission (WHATSAPP-G12) ----------------------------------------------------------


class RenewalDueIn(Schema):
    #: How many days before its deadline a token is renewed.
    window_days: int = Field(14, ge=1, le=59)


class DueNumber(Schema):
    id: UUID
    hub_id: UUID
    token: SecretStr
    expires_at: datetime


class RenewalDueOut(Schema):
    numbers: list[DueNumber]


class RenewalIn(Schema):
    number_id: UUID
    #: ``renewed``: Meta gave a fresh token (``token``, ``expires_at``: ``None`` never); ``refused``: Meta said no;
    #: ``unverified``: no verdict (Meta not reached, throttled, an answer without a token).
    outcome: Literal["renewed", "refused", "unverified"]
    token: SecretStr | None = None
    expires_at: datetime | None = None


class ReconnectAlert(Schema):
    """Whom to tell that the number has to be connected again, and in which words."""

    to: str
    language: str
    business: str
    number: str
    slug: str


class RenewalOut(Schema):
    needs_reconnect: bool
    alert: ReconnectAlert | None = None


class AlertedIn(Schema):
    number_id: UUID


class AlertedOut(Schema):
    alerted: bool


# --- Doors 10–12: connecting a number (WHATSAPP-G11, WHATSAPP-G01, WHATSAPP-G02) ---------------------------------

MetaId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{1,50}$")]


class ConfigIn(Schema):
    """Door 10's body: the business whose screen opens Meta's window."""

    hub: HubRef


class ConnectIn(Schema):
    """Door 11's body: what Meta's window (Embedded Signup) handed the Hub's screen, as it came. ``event``
    ``FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`` is a number of the WhatsApp Business app (coexistence);
    ``phone_number_id`` may be missing then, and the account's only number is taken."""

    hub: HubRef
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
    event: str = Field("", max_length=64)
    waba_id: MetaId
    phone_number_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{0,50}$")] = ""
    business_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{0,50}$")] = ""


class DisconnectIn(Schema):
    hub: HubRef


class ConnectingIn(Schema):
    hub: str
    #: The number about to be registered: its PIN, if erplora.com already keeps one.
    phone_number_id: str = ""


class ConnectingOut(Schema):
    hub_id: UUID
    pin: SecretStr


class NumberConnectIn(Schema):
    hub_id: UUID
    phone_number_id: str
    display_phone: str
    display_name: str = ""
    waba_id: str
    business_id: str = ""
    token: SecretStr
    expires_at: datetime | None = None
    pin: SecretStr
    is_on_biz_app: bool = False


class NumberConnectOut(Schema):
    #: The business the number belonged to until now (it moved), if another.
    moved_from: UUID | None = None


class NumberDisconnectOut(Schema):
    disconnected: bool
    waba_id: str = ""
    #: The permission just forgotten, for unsubscribing the app at Meta after the COMMIT (never kept).
    token: SecretStr | None = None
    #: Another connected number still uses the same account at Meta: its subscription stays.
    account_in_use: bool = False


# --- An attachment opened from the Hub (WHATSAPP-G07) -----------------------------------------------------------


class MediaIn(Schema):
    delivery_id: UUID
    #: The person opening it (their erplora.com session): only an accepted member of the business gets it.
    user_id: UUID


class MediaOut(Schema):
    hub_id: UUID
    media_id: str
    token: SecretStr
    #: What the message said of it (Meta's own answer rules the type).
    mime_type: str = ""
    filename: str = ""


# --- The retention (WHATSAPP-G14) -----------------------------------------------------------------------------


class PurgeIn(Schema):
    #: Days kept; shortened by hand, never lengthened.
    days: int = Field(30, ge=1, le=30)


class PurgeOut(Schema):
    deliveries: int
    never_taken: int
    sends: int
    registrations: int
