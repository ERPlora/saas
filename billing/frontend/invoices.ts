// The Billing section's rules about an invoice, apart from the screen (mockups `billing.html`, README §3b and
// §6.18; billing/README.md «Facturas de ERPlora (L3-C)»):
//   - a paid invoice reads «Paid» once the platform hub issued it (its PDF exists) and «Issuing» until then;
//     one Stripe could not charge reads «Not collected»; a cancelled one, the server's own word;
//   - our number names it once paid; before, Stripe's reference;
//   - an unpaid invoice leaves the business working 7 days, then it is suspended (PLAN-SAAS §3.3);
//   - the account sees the invoices of the businesses it owns or pays.
import { invoiceStatusPill, type StatusPillSpec } from '@erplora/ui/components';

import type { BusinessRowOut, InvoiceRowOut } from '../../frontend/sdk-types';

/** The grace of an unpaid invoice before the business is suspended. */
const GRACE_MS = 7 * 24 * 60 * 60 * 1000;
/** The years the filter offers: this one and the ones before it. */
const YEARS = 5;
/** What the platform hub answers once it issued the invoice (QR and PDF). */
const ISSUED = new Set(['issued', 'accepted', 'accepted_with_errors']);

/** Tone and label of an invoice's status. */
export function invoicePill(
  row: Pick<InvoiceRowOut, 'payment_status' | 'payment_status_label' | 'fiscal_status'>,
  locale: string,
): StatusPillSpec {
  if (row.payment_status === 'open') return invoiceStatusPill('failed', locale);
  if (row.payment_status === 'void') return { tone: 'neutral', label: row.payment_status_label, busy: false };
  return invoiceStatusPill(ISSUED.has(row.fiscal_status) ? 'paid' : 'issuing', locale);
}

/** What names the invoice: our number once paid, Stripe's reference before. */
export function invoiceName(row: Pick<InvoiceRowOut, 'number' | 'reference'>): string {
  return row.number ?? row.reference;
}

/** When a business with an invoice unpaid since `since` (ISO 8601) is suspended; `''` without a date. */
export function graceEnd(since: string | null | undefined): string {
  if (!since) return '';
  const start = Date.parse(since);
  return Number.isNaN(start) ? '' : new Date(start + GRACE_MS).toISOString();
}

/** The years the filter offers, the newest first. */
export function yearOptions(now: Date = new Date()): number[] {
  const year = now.getFullYear();
  return Array.from({ length: YEARS }, (_, index) => year - index);
}

/** The businesses whose invoices the account sees (it owns or pays them), by name in `locale`. */
export function invoiceBusinesses(rows: readonly BusinessRowOut[], locale: string): BusinessRowOut[] {
  return rows
    .filter((row) => row.role === 'hub_owner' || row.is_payer)
    .sort((a, b) => a.name.localeCompare(b.name, locale));
}

const money = new Map<string, Intl.NumberFormat>();

/** Cents in `currency` (Stripe writes it in lower case; euros without one), in the person's language. */
export function formatAmount(cents: number, currency: string, locale: string): string {
  const code = (currency || 'eur').toUpperCase();
  const key = `${locale}|${code}`;
  let format = money.get(key);
  if (!format) {
    format = new Intl.NumberFormat(locale, { style: 'currency', currency: code });
    money.set(key, format);
  }
  return format.format(cents / 100);
}

/** How a card brand writes itself (Stripe sends `visa`, `mastercard`, `amex`…). */
const BRANDS: Readonly<Record<string, string>> = {
  amex: 'American Express',
  diners: 'Diners Club',
  jcb: 'JCB',
  unionpay: 'UnionPay',
};

export function cardBrand(brand: string): string {
  if (!brand) return '';
  return BRANDS[brand] ?? brand.charAt(0).toUpperCase() + brand.slice(1);
}
