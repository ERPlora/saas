"""The mail of billing: an invoice of ERPlora was issued (lot L3-C; ported from ERPlora/saas
``apps/dashboard/billing/emails.py``, saas#1061).

Plain text in the language of the invoice (its payer's), as every mail of the SaaS until block 1 brings the
branded one (``hubs/emails.py``). It LINKS to the panel's Billing page instead of attaching the PDF: the PDF
is the platform hub's, asked on demand, and it carries the QR. Sent after the COMMIT by
``billing.services`` the first time the platform hub issues the invoice; one that cannot leave is logged,
never raised (the invoice is the source of truth). No database here.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class MailNotSent(Exception):
    """The mail could not leave: not sent, so it is sent again later (``reconcile_platform_invoices``)."""


def _money(euros) -> str:
    return f"{number_format(euros, decimal_pos=2, force_grouping=True)} €"


def send_invoice_issued(invoice) -> bool:
    """Tell the payer that ``invoice`` is issued, with its amounts and where to download it. ``False`` when
    there is nothing to send (not paid, nobody to send it to); ``MailNotSent`` when the mail could not leave."""
    if invoice.payment_status != "paid":
        logger.info(
            "[EMAIL] Invoice %s is %s: no mail",
            invoice.number or invoice.pk,
            invoice.payment_status,
        )
        return False
    account = invoice.payer_account
    to = invoice.payer_email or (account.email if account is not None else "")
    if not to:
        logger.info("[EMAIL] Invoice %s has nobody to send it to", invoice.number)
        return False
    with translation.override(invoice.language or settings.LANGUAGE_CODE):
        if invoice.kind == "credit_note":
            subject = _("Credit note %(number)s from ERPlora") % {
                "number": invoice.number
            }
            opening = _("ERPlora issued credit note %(number)s for %(business)s.")
        else:
            subject = _("Invoice %(number)s from ERPlora") % {"number": invoice.number}
            opening = _("ERPlora issued invoice %(number)s for %(business)s.")
        lines = [
            opening % {"number": invoice.number, "business": invoice.business_name},
            "",
            _("Date: %(date)s")
            % {"date": date_format(invoice.issued_on, "DATE_FORMAT")},
            _("Tax base: %(amount)s") % {"amount": _money(invoice.net)},
            _("VAT (%(rate)s %%): %(amount)s")
            % {
                "rate": number_format(invoice.tax_rate, decimal_pos=2),
                "amount": _money(invoice.tax),
            },
            _("Total: %(amount)s") % {"amount": _money(invoice.total)},
            "",
            _("Download it from Billing: %(url)s")
            % {"url": f"https://{settings.PUBLIC_HOST}/billing"},
        ]
    try:
        send_mail(subject, "\n".join(lines) + "\n", None, [to])
    except Exception as failed:  # noqa: BLE001 - reported to the caller, which sends it again later
        logger.error("[EMAIL] Invoice %s not sent to %s: %s", invoice.number, to, failed)
        raise MailNotSent(str(failed)) from failed
    logger.info("[EMAIL] Invoice %s sent to %s", invoice.number, to)
    return True
