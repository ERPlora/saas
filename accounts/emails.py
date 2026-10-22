"""The mails of accounts, each in its recipient's language: the code that proves an address (Account → Profile,
«Change email») and the notice to the old address once the account changed it (Google, GitHub and Stripe send
one, so a change nobody asked for does not go unnoticed).

Plain text, like the mails of hubs, until block 1 brings the branded mail. A mail that cannot leave is logged
and reported to the caller (``False``), never raised; the code itself is never logged.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import translation
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

#: Minutes a code works (``services.EMAIL_CODE_LIFETIME``), as the mail says it.
CODE_MINUTES = 15


def _send(subject: str, lines: list[str], to: str, kind: str) -> bool:
    try:
        send_mail(subject, "\n".join(lines) + "\n", settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # noqa: BLE001 - any failure of the mail backend is reported, not raised
        logger.exception("accounts.mail_failed kind=%s", kind)
        return False
    return True


def send_email_code(email: str, code: str, *, language: str) -> bool:
    """The code that makes ``email`` the account's address, typed in the session that asked for it."""
    with translation.override(language):
        subject = _("Your ERPlora code: %(code)s") % {"code": code}
        lines = [
            _("Type this code in ERPlora to use %(email)s as the email of your account:") % {"email": email},
            "",
            code,
            "",
            _("It works for %(minutes)s minutes. If you did not ask for it, ignore this mail: nothing changes.")
            % {"minutes": CODE_MINUTES},
        ]
    return _send(subject, lines, email, "email_code")


def send_email_changed(old_email: str, new_email: str, *, language: str) -> bool:
    """Tell the old address that the account now answers to ``new_email``."""
    with translation.override(language):
        subject = _("The email of your ERPlora account changed")
        lines = [
            _("The email of your ERPlora account is now %(email)s.") % {"email": new_email},
            "",
            _("If you did not change it, write to %(support)s at once.") % {"support": settings.SUPPORT_EMAIL},
        ]
    return _send(subject, lines, old_email, "email_changed")


def send_api_key_created(email: str, name: str, scopes: list[str], *, language: str) -> bool:
    """Tell the account a key was created for it (never the key): a new way into the account."""
    from accounts.models import API_KEY_SCOPES

    with translation.override(language):
        subject = _("New API key in your ERPlora account")
        lines = [
            _("An API key called «%(name)s» was created in your ERPlora account, with these permissions: %(scopes)s.")
            % {"name": name, "scopes": ", ".join(str(API_KEY_SCOPES[scope]) for scope in scopes)},
            "",
            _("If you did not create it, revoke it in Account → API keys and write to %(support)s at once.")
            % {"support": settings.SUPPORT_EMAIL},
        ]
    return _send(subject, lines, email, "api_key_created")


def send_support_report(user, *, subject: str, description: str, context: list[tuple[str, str]]) -> bool:
    """A report of «Report a problem» to the support mailbox (ACCOUNTS-F38), «Reply-To» the account so support answers
    with «Reply». In English, as the contact form's: it is the team's mail, not the account's. ``context`` is what goes
    under the text (the account, its businesses, the page, the browser). The text itself is never logged."""
    from django.core.mail import EmailMessage

    lines = [description, "", "---", *(f"{label}: {value}" for label, value in context)]
    try:
        EmailMessage(
            subject=f"[Support] {subject}",
            body="\n".join(lines) + "\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SUPPORT_EMAIL],
            reply_to=[user.email],
        ).send(fail_silently=False)
    except Exception:  # noqa: BLE001 - any failure of the mail backend is reported, not raised
        logger.exception("accounts.mail_failed kind=support_report")
        return False
    return True
