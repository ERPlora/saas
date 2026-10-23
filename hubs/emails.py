"""The mails of hubs, each in its recipient's language (``User.language``), branded as text and as HTML
(``base.emails.branded_message``, ACCOUNTS-F46).

Ported from ERPlora/saas ``apps/dashboard/hubs/main/emails.py`` (origin/develop): the invitation
(``send_invitation``), the ownership offer and its acceptance (``send_ownership_offer``,
``send_ownership_accepted``, which say until when a paid plan is paid, HUBS-F28), the deletion with the date
until which the business can be recovered (``send_deletion``), the business ready to open (``send_ready``, once,
when the Hub reports it ready) and the notices of a business suspended for an unpaid plan
(``send_suspension_notice``). Services call them after the COMMIT: a mail never announces a write that rolled
back, and one that cannot leave is logged, never raised (the write is the source of truth).
"""

import logging

from django.conf import settings
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from accounts.queries import hub_start_url, receives_business_notices
from base.emails import branded_message

logger = logging.getLogger(__name__)


def base_url(request) -> str:
    """Where the links of a mail point: the SaaS the request came to, or the public host."""
    if request is not None:
        return f"{request.scheme}://{request.get_host()}"
    return f"https://{settings.PUBLIC_HOST}"


def send_invitation(member, *, base_url: str, new_account: bool) -> bool:
    """Tell the invited person who invited them, to which business, as what and until when."""
    inviter = member.invited_by
    language = _language_of(member.user)
    with translation.override(language):
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
    return _send(subject, lines, member.user.email, language)


def send_ownership_offer(transfer, *, base_url: str, paid_until=None) -> bool:
    """Tell the named recipient that a business is offered to them; with a paid plan (``paid_until``, the end of the
    period already paid), that it goes with the business until then and that they keep it with their card
    (HUBS-F28)."""
    language = _language_of(transfer.to_user)
    with translation.override(language):
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
                # Answered on Businesses, whose card offers «Accept the ownership» (HUBS-G82).
                "url": f"{base_url}/businesses",
            },
        ]
        if paid_until is not None:
            lines += [
                "",
                _(
                    "Its paid plan is paid until %(date)s. From then on you pay it with your card: once you accept, "
                    "keep it in Billing › Subscriptions: %(url)s"
                )
                % {"date": _date(paid_until), "url": f"{base_url}/billing/subscriptions"},
            ]
    return _send(subject, lines, transfer.to_email, language)


def send_ownership_accepted(transfer, *, base_url: str, paid_until=None) -> bool:
    """Tell the outgoing owner the hand-over went through and that they stay as admin; with a paid plan
    (``paid_until``), that their card no longer renews it (HUBS-F28)."""
    language = _language_of(transfer.from_user)
    with translation.override(language):
        subject = _("%(who)s now owns %(business)s") % {
            "who": transfer.to_email,
            "business": transfer.hub.name,
        }
        lines = [
            _(
                "%(who)s accepted the ownership of %(business)s. You stay on it as an administrator."
            )
            % {"who": transfer.to_email, "business": transfer.hub.name},
            _("See it in your businesses: %(url)s") % {"url": f"{base_url}/businesses/{transfer.hub_id}"},
        ]
        if paid_until is not None:
            lines += [
                "",
                _(
                    "Its paid plan no longer renews with your card: it stays until %(date)s, and from then on the new "
                    "owner pays it with theirs."
                )
                % {"date": _date(paid_until)},
            ]
    return _send(subject, lines, transfer.from_email, language)


def send_deletion(hub, owner, *, base_url: str, unpaid: bool = False) -> bool:
    """Tell the owner the business was deleted and until when it can still be recovered; ``unpaid``: it was
    deleted because it stayed suspended for an unpaid plan (HUBS-F20)."""
    if owner is None:
        logger.error("hubs.mail.deletion_unsent hub=%s: the business has no owner to tell", hub.pk)
        return False
    language = _language_of(owner)
    with translation.override(language):
        subject = _("%(business)s was deleted") % {"business": hub.name}
        lines = [
            _("%(business)s was deleted and no longer opens.") % {"business": hub.name},
            *(
                [_("It had been suspended for %(days)d days because an invoice was not paid.") % {"days": 180}]
                if unpaid
                else []
            ),
            "",
            _(
                "You can recover it until %(date)s from %(url)s. After that date it is erased for good."
            )
            % {"date": _date(hub.purge_after), "url": f"{base_url}/businesses"},
        ]
    return _send(subject, lines, owner.email, language)


def send_ready(hub, owner, *, base_url: str) -> bool:
    """Tell the owner the business is ready, with the way in and its page in the panel: a business notice, so not
    to an owner who turned them off in Account → Preferences (ACCOUNTS-F23; the panel says it is ready anyway)."""
    if not receives_business_notices(owner):
        logger.info("hubs.mail.ready_skipped hub=%s: the owner turned business notices off", hub.pk)
        return False
    language = _language_of(owner)
    with translation.override(language):
        subject = _("%(business)s is ready") % {"business": hub.name}
        lines = [
            _("%(business)s is ready: open it and start selling.") % {"business": hub.name},
            "",
            _("Open it: %(url)s") % {"url": hub_start_url(hub.slug)},
            _("Manage it from the panel: %(url)s") % {"url": f"{base_url}/businesses/{hub.id}"},
        ]
    return _send(subject, lines, owner.email, language)


def send_suspension_notice(hub, owner, *, base_url: str, delete_on, final: bool) -> bool:
    """Tell the owner that ``hub``, suspended for an unpaid plan, will be deleted on ``delete_on`` unless it is paid
    (HUBS-F20): the first notice (day 30) or the last one (``final``, day 150). Always sent: it warns of a deletion."""
    language = _language_of(owner)
    with translation.override(language):
        values = {"business": hub.name, "date": _date(delete_on)}
        subject = (
            _("Last notice: %(business)s will be deleted on %(date)s") % values
            if final
            else _("%(business)s is still suspended") % values
        )
        lines = [
            _("%(business)s is still suspended because an invoice was not paid.") % values,
            _("If it is not paid, the business will be deleted on %(date)s.") % values,
            _("After that you can still recover it for 90 days, on the Free plan.") % values,
            "",
            _("Pay it from Billing and it works again at once: %(url)s") % {"url": f"{base_url}/billing/invoices?business={hub.id}"},
        ]
    return _send(subject, lines, owner.email, language)


def _language_of(user) -> str:
    return user.language if user is not None else settings.LANGUAGE_CODE


def _date(moment) -> str:
    return date_format(timezone.localtime(moment), "DATE_FORMAT")


def _send(subject: str, lines: list[str], to: str, language: str) -> bool:
    try:
        branded_message(subject, lines, [to], language=language).send()
    except Exception as failed:  # noqa: BLE001 - a mail never undoes the write it announces
        logger.error("hubs.mail.not_sent to=%s subject=%r: %s", to, subject, failed)
        return False
    return True
