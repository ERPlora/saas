"""The mails of hubs, each in its recipient's language (``User.language``).

Ported from ERPlora/saas ``apps/dashboard/hubs/main/emails.py`` (origin/develop) as plain text, until
block 1 brings the branded mail: the invitation (``send_invitation``), the ownership offer and its
acceptance (``send_ownership_offer``, ``send_ownership_accepted``) and the deletion with the date until
which the business can be recovered (``send_deletion``). Services call them after the COMMIT: a mail
never announces a write that rolled back, and one that cannot leave is logged, never raised (the
write is the source of truth).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def base_url(request) -> str:
    """Where the links of a mail point: the SaaS the request came to, or the public host."""
    if request is not None:
        return f"{request.scheme}://{request.get_host()}"
    return f"https://{settings.PUBLIC_HOST}"


def send_invitation(member, *, base_url: str, new_account: bool) -> bool:
    """Tell the invited person who invited them, to which business, as what and until when."""
    inviter = member.invited_by
    with translation.override(member.user.language):
        who = (inviter.get_full_name() or inviter.email) if inviter else _("Somebody")
        lines = [
            _("%(who)s invited you to join %(business)s on ERPlora as %(role)s.")
            % {
                "who": who,
                "business": member.hub.name,
                "role": member.get_role_display(),
            },
        ]
        if member.invitation_message:
            lines += ["", member.invitation_message]
        lines += [
            "",
            _("Accept the invitation: %(url)s") % {"url": f"{base_url}/invitation"},
        ]
        if member.invitation_expires_at:
            lines.append(
                _("The invitation expires on %(date)s.")
                % {"date": _date(member.invitation_expires_at)}
            )
        if new_account:
            lines += [
                "",
                _(
                    "You do not have an ERPlora account yet: sign in with Google with this address, or set "
                    "a password here: %(url)s"
                )
                # The sign-in's «Forgot your password?» (the SPA's page): the key goes to the mailbox.
                % {"url": f"{base_url}/password/reset"},
            ]
        subject = _("%(who)s invited you to %(business)s") % {
            "who": who,
            "business": member.hub.name,
        }
    return _send(subject, lines, member.user.email)


def send_ownership_offer(transfer, *, base_url: str) -> bool:
    """Tell the named recipient that a business is offered to them, and that the payer stays."""
    with translation.override(_language_of(transfer.to_user)):
        subject = _("%(who)s wants to hand %(business)s over to you") % {
            "who": transfer.from_email,
            "business": transfer.hub.name,
        }
        lines = [
            _("%(who)s offers you the ownership of %(business)s on ERPlora.")
            % {"who": transfer.from_email, "business": transfer.hub.name},
            "",
            _("Accept or decline it before %(date)s: %(url)s")
            % {
                "date": _date(transfer.expires_at),
                "url": f"{base_url}/ownership/{transfer.id}",
            },
            "",
            _(
                "The billing does not move with the business: whoever pays for it today keeps paying until they change it."
            ),
        ]
    return _send(subject, lines, transfer.to_email)


def send_ownership_accepted(transfer, *, base_url: str) -> bool:
    """Tell the outgoing owner the hand-over went through, that they stay as admin, and who pays."""
    with translation.override(_language_of(transfer.from_user)):
        subject = _("%(who)s now owns %(business)s") % {
            "who": transfer.to_email,
            "business": transfer.hub.name,
        }
        lines = [
            _(
                "%(who)s accepted the ownership of %(business)s. You stay on it as an administrator."
            )
            % {"who": transfer.to_email, "business": transfer.hub.name},
            "",
            _(
                "The billing did not move: the invoices still go to the same payer until it is changed in %(url)s."
            )
            % {"url": f"{base_url}/businesses/{transfer.hub_id}/settings"},
        ]
    return _send(subject, lines, transfer.from_email)


def send_deletion(hub, owner, *, base_url: str) -> bool:
    """Tell the owner the business was deleted and until when it can still be recovered."""
    with translation.override(owner.language):
        subject = _("%(business)s was deleted") % {"business": hub.name}
        lines = [
            _("%(business)s was deleted and no longer opens.") % {"business": hub.name},
            "",
            _(
                "You can recover it until %(date)s from %(url)s. After that date it is erased for good."
            )
            % {"date": _date(hub.purge_after), "url": f"{base_url}/businesses"},
        ]
    return _send(subject, lines, owner.email)


def _language_of(user) -> str:
    return user.language if user is not None else settings.LANGUAGE_CODE


def _date(moment) -> str:
    return date_format(timezone.localtime(moment), "DATE_FORMAT")


def _send(subject: str, lines: list[str], to: str) -> bool:
    try:
        send_mail(subject, "\n".join(lines) + "\n", None, [to])
    except Exception as failed:  # noqa: BLE001 - a mail never undoes the write it announces
        logger.error("hubs.mail.not_sent to=%s subject=%r: %s", to, subject, failed)
        return False
    return True
