"""The mail of billing: an invoice of ERPlora was issued (lot L3-C; ported from ERPlora/saas
``apps/dashboard/billing/emails.py``, saas#1061), and a renewal could not be collected or the business was
suspended for it (BILLING-F16, saas#2593).

Branded, as text and as HTML (``base.emails``, ACCOUNTS-F46), in the language of the invoice (its payer's). It
LINKS to the panel's Billing page instead of attaching the PDF: the PDF is the platform hub's, asked on demand,
and it carries the QR. Sent after the COMMIT by ``billing.services`` the first time the platform hub issues the
invoice; one that cannot leave (also when its HTML cannot be drawn) is logged and reported as ``MailNotSent``, so
it is sent again later (the invoice is the source of truth). No database here.
"""

import logging

from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext as _

from base.emails import branded_message
from billing.money import from_cents

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
    language = invoice.language or settings.LANGUAGE_CODE
    with translation.override(language):
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
        branded_message(subject, lines, [to], language=language).send()
    except Exception as failed:  # noqa: BLE001 - reported to the caller, which sends it again later
        logger.error("[EMAIL] Invoice %s not sent to %s: %s", invoice.number, to, failed)
        raise MailNotSent(str(failed)) from failed
    logger.info("[EMAIL] Invoice %s sent to %s", invoice.number, to)
    return True


#: What a mail of the unpaid episode is, in its ``X-ERPlora-Notice`` header (support filters by it).
PAYMENT_FAILED = "billing.payment_failed"
BUSINESS_SUSPENDED = "billing.business_suspended"


def _billing_url(hub) -> str:
    return f"https://{settings.PUBLIC_HOST}/billing/invoices?business={hub.id}"


def _send_notice(notice: str, subject: str, lines: list[str], to: str, *, language: str) -> None:
    try:
        branded_message(subject, lines, [to], language=language, headers={"X-ERPlora-Notice": notice}).send()
    except Exception as failed:  # noqa: BLE001 - reported to the caller, which sends it again later
        logger.error("[EMAIL] %s not sent to %s: %s", notice, to, failed)
        raise MailNotSent(str(failed)) from failed
    logger.info("[EMAIL] %s sent to %s", notice, to)


def send_payment_failed(hub, *, to: str, language: str, amount, declined: bool, suspends_on) -> None:
    """Tell the payer that the renewal of ``hub`` could not be collected: how much, until when it keeps working
    (``suspends_on``) and where to pay it. ``MailNotSent`` when the mail could not leave."""
    language = language or settings.LANGUAGE_CODE
    with translation.override(language):
        subject = _("We could not charge the plan of %(business)s") % {"business": hub.name}
        lines = [
            _("We could not charge %(amount)s for the plan of %(business)s.")
            % {"amount": _money(amount), "business": hub.name},
        ]
        if declined:
            lines.append(_("The bank declined the card: change it before paying, we will not charge it again."))
        lines += [
            _("%(business)s keeps working until %(date)s. If the invoice is not paid by then, it is suspended. Nothing is deleted.")
            % {"business": hub.name, "date": date_format(suspends_on, "DATE_FORMAT")},
            "",
            _("Pay it from Billing: %(url)s") % {"url": _billing_url(hub)},
        ]
    _send_notice(PAYMENT_FAILED, subject, lines, to, language=language)


def send_business_suspended(hub, *, to: str, language: str, amount) -> None:
    """Tell the payer that ``hub`` is suspended until its unpaid invoice (``amount``) is paid, and where to pay
    it. ``MailNotSent`` when the mail could not leave."""
    language = language or settings.LANGUAGE_CODE
    with translation.override(language):
        subject = _("%(business)s is suspended") % {"business": hub.name}
        lines = [
            _("%(business)s is suspended because an invoice of %(amount)s was not paid.")
            % {"business": hub.name, "amount": _money(amount)},
            _("Your data is safe: as soon as the invoice is paid, the business works again."),
            "",
            _("Pay it from Billing: %(url)s") % {"url": _billing_url(hub)},
        ]
    _send_notice(BUSINESS_SUSPENDED, subject, lines, to, language=language)


#: The headers of the team's OSS notices (BILLING-F06).
OSS_NOTICE = "billing.oss_{kind}"


def send_oss_notice(notice) -> None:
    """Tell the team's mailbox (``SUPPORT_EMAIL``) that the year passed ``OSS_WARNING_PERCENT`` of the OSS
    threshold (register in the OSS now: form 035 takes days) or crossed it (destination VAT already applies:
    register at once).
    ``MailNotSent`` when the mail could not leave."""
    from billing.services import OSS_WARNING_PERCENT

    values = {
        "year": notice.year,
        "last_year": notice.year - 1,
        "amount": _money(from_cents(notice.accumulated_cents)),
        "threshold": _money(from_cents(notice.threshold_cents)),
        "percent": OSS_WARNING_PERCENT,
        "invoice": notice.invoice.number,
    }
    with translation.override(settings.LANGUAGE_CODE):
        if notice.kind == "near":
            subject = _("OSS: cross-border B2C sales passed %(percent)s %% of the threshold in %(year)s") % values
            lines = [
                _(
                    "Sales to consumers in other EU member states in %(year)s reached %(amount)s (tax base), past "
                    "%(percent)s %% of the OSS threshold of %(threshold)s."
                )
                % values,
                _("Sale that passed it: invoice %(invoice)s.") % values,
                "",
                _(
                    "Above the threshold, destination VAT applies on its own from the crossing sale. Registering in "
                    "the OSS (form 035) takes days: start it now."
                ),
            ]
        else:
            subject = _("OSS: cross-border B2C sales crossed the threshold in %(year)s") % values
            if notice.reason == "previous_year":
                why = _(
                    "Sales to consumers in other EU member states in %(last_year)s closed at %(amount)s (tax base), "
                    "above the OSS threshold of %(threshold)s, so the whole of %(year)s goes in destination VAT."
                )
            else:
                why = _(
                    "Sales to consumers in other EU member states in %(year)s reached %(amount)s (tax base), above "
                    "the OSS threshold of %(threshold)s."
                )
            lines = [
                why % values,
                _("First sale in destination VAT: invoice %(invoice)s, from %(date)s.")
                % {**values, "date": date_format(notice.effective_from, "DATE_FORMAT")},
                "",
                _("Destination VAT already applies on its own. Registering in the OSS (form 035) is urgent: do it now."),
            ]
        lines.append(_("This notice is sent once per year."))
    _send_notice(
        OSS_NOTICE.format(kind=notice.kind), subject, lines, settings.SUPPORT_EMAIL, language=settings.LANGUAGE_CODE
    )

