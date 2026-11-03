"""The assistant's mails to a person, each in its recipient's language (``User.language``), branded as text and as
HTML (``base.emails.branded_message``, ACCOUNTS-F46).

- ``send_messages_near`` (ASSISTANT-F29, step 1): an account has 80 % of its month's messages with the panel's
  assistant spent: how many are left of how many, when they come back and the way to the panel.
- ``send_messages_spent`` (ASSISTANT-F29, step 2): the month's messages are spent: when they come back, that each
  business has its own assistant with its own messages, and the way to the panel.

Neither offers a plan nor messages to buy: there are none (ASSISTANT-F26). ``assistant.services`` calls them after the
COMMIT of the claim that reached them; one that cannot leave is logged and answered ``False``, never raised: the turn
goes on, and the service frees its mark so the next message of the month tries again.
"""

import logging
from datetime import date

from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from base.emails import branded_message
from base.navigation import PANEL

logger = logging.getLogger(__name__)


def send_messages_near(user, *, used: int, limit: int, resets_on: date) -> bool:
    """Tell ``user`` how many of the month's messages with the panel's assistant are left, and when they come back."""
    left = max(limit - used, 0)
    with translation.override(user.language):
        subject = ngettext(
            "You have %(left)s message with the assistant left this month",
            "You have %(left)s messages with the assistant left this month",
            left,
        ) % {"left": left}
        lines = [
            ngettext(
                "You have %(left)s of %(limit)s messages with the assistant left this month.",
                "You have %(left)s of %(limit)s messages with the assistant left this month.",
                left,
            )
            % {"left": left, "limit": limit},
            _("They come back on %(date)s.") % {"date": _day(resets_on)},
            "",
            _("Open your panel: %(url)s") % {"url": _panel()},
        ]
    return _send(subject, lines, user.email, user.language)


def send_messages_spent(user, *, limit: int, resets_on: date) -> bool:
    """Tell ``user`` the month's messages with the panel's assistant are spent, when they come back, and that each
    business has its own assistant."""
    with translation.override(user.language):
        subject = _("You have used this month's messages with the assistant")
        lines = [
            _("You have used all %(limit)s messages with the assistant this month.") % {"limit": limit},
            _("They come back on %(date)s.") % {"date": _day(resets_on)},
            "",
            _("Each business has its own assistant, with its own messages: open the business to keep asking there."),
            "",
            _("Open your panel: %(url)s") % {"url": _panel()},
        ]
    return _send(subject, lines, user.email, user.language)


def _day(day: date) -> str:
    """The day and month in the active language («1 de diciembre», «December 1»)."""
    return date_format(day, "MONTH_DAY_FORMAT")


def _panel() -> str:
    return f"https://{settings.PUBLIC_HOST}{PANEL}"


def _send(subject: str, lines: list[str], to: str, language: str) -> bool:
    try:
        branded_message(subject, lines, [to], language=language).send()
    except Exception as failed:  # noqa: BLE001 - a mail never stops the turn that reached it
        logger.error("assistant.mail.not_sent to=%s subject=%r: %s", to, subject, failed)
        return False
    return True
