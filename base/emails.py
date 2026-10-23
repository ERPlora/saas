"""The branded mail of erplora.com (ACCOUNTS-F46; PLAN-SAAS §7, block 13): every mail leaves as text AND as HTML,
the HTML on the common template ``templates/emails/base.html`` (the logo, a header and a footer of the brand, CSS
inline, and nothing fetched from the network but the logo, which erplora.com serves itself).

A sender keeps its words: it hands its subject and its lines (paragraphs apart by an empty line), the text part is
those lines as they are, and the HTML part shows the same lines, escaped and with their links clickable. The
language is the recipient's, given explicitly: the senders build their lines in it and send outside it. Sending
stays the sender's, with its own ``try``/``except`` and log: a failure here is raised, never swallowed.

Ported in structure from ERPlora/saas ``apps/core/emails.py`` (``send_branded_email`` and its ``_fallback.html``,
origin/develop). allauth's mails get the same HTML through ``accounts.adapters.AccountAdapter.render_mail``.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation

TEMPLATE = "emails/base.html"
#: The logo of the mails: the public web's, served without a hash in its name, so its URL stays.
LOGO = "public/img/logo.png"


def brand() -> dict[str, str]:
    """What the common template needs of the brand, written here so no context can replace it."""
    host = settings.PUBLIC_HOST
    return {
        "logo_url": f"https://{host}{settings.STATIC_URL}{LOGO}",
        "site_url": f"https://{host}",
        "site_host": host,
    }


def _paragraphs(lines: list[str], code: str | None) -> list[dict]:
    paragraphs: list[dict] = []
    current: list[str] = []
    for line in [*lines, ""]:
        if line.strip():
            current.append(line)
            continue
        if current:
            paragraphs.append({"lines": current, "code": code is not None and current == [code]})
            current = []
    return paragraphs


def branded_html(lines: list[str], *, language: str, subject: str = "", code: str | None = None) -> str:
    """The HTML part of a mail that says ``lines`` in ``language``; the paragraph that is ``code`` alone, boxed."""
    with translation.override(language):
        return render_to_string(TEMPLATE, {"subject": subject, "paragraphs": _paragraphs(lines, code), **brand()})


def branded_message(
    subject: str,
    lines: list[str],
    to: list[str],
    *,
    language: str,
    from_email: str | None = None,
    reply_to: list[str] | None = None,
    headers: dict[str, str] | None = None,
    code: str | None = None,
) -> EmailMultiAlternatives:
    """A mail of ``lines`` to ``to``: its text, and its HTML on the common template, in ``language``."""
    message = EmailMultiAlternatives(
        subject,
        "\n".join(lines) + "\n",
        from_email,
        to,
        reply_to=reply_to,
        headers=headers,
    )
    message.attach_alternative(branded_html(lines, language=language, subject=subject, code=code), "text/html")
    return message
