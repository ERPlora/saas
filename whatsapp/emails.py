"""The mails of whatsapp, each in its recipient's language (``User.language``).

«Connect WhatsApp again» (WHATSAPP-G12): Meta did not renew the business's permission, so its customers' messages
stop reaching the Hub until the number is connected again. Branded, as text and as HTML (``base.emails``,
ACCOUNTS-F46). Sent after the COMMIT of what it announces; one that cannot leave is logged, never raised (the next
renewal round tries again).
"""

import logging

from django.utils import translation
from django.utils.translation import gettext as _

from accounts.queries import hub_origin
from base.emails import branded_message

logger = logging.getLogger(__name__)


def send_reconnect(*, to: str, language: str, business: str, number: str, slug: str) -> bool:
    with translation.override(language):
        subject = _("Action needed: connect WhatsApp again (%(number)s)") % {"number": number}
        lines = [
            _(
                "The permission that lets ERPlora send and receive WhatsApp messages with %(number)s for "
                "«%(business)s» is about to expire, and Meta did not let us renew it."
            )
            % {"number": number, "business": business},
            "",
            _("Until you connect it again, your customers' WhatsApp messages will not reach your Hub."),
            "",
            _("It takes a minute: open your Hub, go to WhatsApp and connect your number again: %(url)s")
            % {"url": hub_origin(slug)},
        ]
    try:
        branded_message(subject, lines, [to], language=language).send()
    except Exception as failed:  # noqa: BLE001 - the mark is written; the next round tries the mail again
        logger.error("whatsapp.mail.not_sent kind=reconnect error=%s", type(failed).__name__)
        return False
    return True
