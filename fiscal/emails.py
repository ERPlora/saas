"""The mails of an authorisation's steps (FISCAL-F05): the review desk hears of every one that waits for it, and
the owner and the admins of the business hear of every step of theirs (received, in force, returned, withdrawn),
each in their language.

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/services/grant_notifications.py`` (origin/develop)
and saas#2051 (nobody at ERPlora heard of what waited for them), without what made the old mail unsafe: the desk's
mail carries the link to the admin's review page and no document, no tax id and no name of a person (the old one
attached the decrypted documents), and the business is found by its id, never by a tax id. The desk's mailbox is
``settings.FISCAL_REVIEW_EMAIL`` (support's unless another is set); it reads Spanish, the language of the Anexo I.

Whether ERPlora may file a business's invoices keeps the business running, so these mails ask no preference
(ACCOUNTS-F23). A step a newer one replaced (a submission replaced before any review, an approval replaced by a
newer approval) tells nobody: the newer step's own mail says all there is to say.

Plain text, like the mails of hubs. ``fiscal.services`` calls ``grant_stepped`` after the COMMIT, so a mail never
announces a step that rolled back; one that cannot leave is logged with the grant's id, never raised (the step
stands, and the admin's queue still lists what waits).
"""

import logging
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from fiscal.models import RepresentationGrant
from fiscal.queries import step_to_announce

logger = logging.getLogger(__name__)

Status = RepresentationGrant.Status
#: The language the review desk reads.
DESK_LANGUAGE = "es"


def grant_stepped(grant_id: UUID) -> None:
    """Tell whom a step of the authorisation ``grant_id`` concerns, by the state it reached."""
    step = step_to_announce(grant_id)
    if step is None:
        return
    grant, people = step
    if grant.status == Status.SUBMITTED:
        _tell_the_desk(grant)
    for person in people:
        _tell_the_business(grant, person)


def _site() -> str:
    return f"https://{settings.PUBLIC_HOST}"


def _tell_the_desk(grant: RepresentationGrant) -> None:
    review = _site() + reverse(
        "admin:fiscal_representationgrant_review", args=[grant.pk]
    )
    facts = {"business": grant.hub.name, "version": grant.version}
    with translation.override(DESK_LANGUAGE):
        subject = (
            _("Signed authorisation to review: %(business)s (version %(version)d)")
            % facts
        )
        lines = [
            _(
                "%(business)s sent its signed authorisation (version %(version)d): it waits for a person of "
                "ERPlora to review it."
            )
            % facts,
            "",
            _("Review it: %(url)s") % {"url": review},
        ]
    _send(grant, subject, lines, settings.FISCAL_REVIEW_EMAIL)


def _tell_the_business(grant: RepresentationGrant, person) -> None:
    business = grant.hub.name
    panel = f"{_site()}/businesses/{grant.hub_id}"
    with translation.override(person.language or settings.LANGUAGE_CODE):
        if grant.status == Status.SUBMITTED:
            subject = _("We received the signed authorisation of %(business)s") % {
                "business": business
            }
            lines = [
                _(
                    "A person of ERPlora reviews it and you will get a mail with the answer. Until then, "
                    "ERPlora does not send the invoices of %(business)s to the tax agency with its seal."
                )
                % {"business": business},
            ]
        elif grant.status == Status.APPROVED:
            subject = _("The signed authorisation of %(business)s is now in force") % {
                "business": business
            }
            lines = [
                _(
                    "ERPlora may now send the invoices of %(business)s to the tax agency with its seal."
                )
                % {"business": business},
            ]
        elif grant.status == Status.RETURNED:
            subject = _(
                "We returned the signed authorisation of %(business)s"
            ) % {"business": business}
            lines = [
                _("Why: %(reason)s") % {"reason": grant.reason},
                "",
                _(
                    "Fix it and send it again from the VeriFactu app of the business."
                ),
            ]
        else:
            subject = _(
                "ERPlora withdrew the signed authorisation of %(business)s"
            ) % {"business": business}
            lines = [
                _("Why: %(reason)s") % {"reason": grant.reason},
                "",
                _(
                    "ERPlora no longer sends the invoices of %(business)s to the tax agency with its seal. "
                    "Send a new one from the VeriFactu app of the business."
                )
                % {"business": business},
            ]
        lines += ["", _("See it in the panel: %(url)s") % {"url": panel}]
    _send(grant, subject, lines, person.email)


def _send(grant: RepresentationGrant, subject: str, lines: list[str], to: str) -> bool:
    try:
        send_mail(subject, "\n".join(lines) + "\n", None, [to])
    except Exception as failed:  # noqa: BLE001 - a mail never undoes the step it announces
        logger.error(
            "fiscal.mail.not_sent grant=%s status=%s: %s",
            grant.pk,
            grant.status,
            type(failed).__name__,
        )
        return False
    return True
