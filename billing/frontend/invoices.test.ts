// The Billing section's rules about an invoice, apart from the screen (mockups `billing.html`, README §3b and
// §6.18; billing/README.md «Facturas de ERPlora (L3-C)»): how its status reads, what names it, the grace of an
// unpaid one, the years the filter offers and the businesses whose invoices the account sees.
import { describe, expect, it } from 'vitest';

import { invoiceRow } from './__tests__/billing-fixtures';
import { businessRow } from './__tests__/fixtures';
import { cardBrand, formatAmount, graceEnd, invoiceBusinesses, invoiceName, invoicePill, yearOptions } from './invoices';

describe('invoicePill', () => {
  it('reads «Not collected» for an invoice Stripe could not charge', () => {
    expect(invoicePill(invoiceRow('a', { payment_status: 'open', fiscal_status: '' }), 'en')).toEqual({ tone: 'danger', label: 'Not collected', busy: false });
  });

  it('reads «Paid» once the platform hub issued it, accepted or not by the AEAT yet', () => {
    for (const fiscal of ['issued', 'accepted', 'accepted_with_errors'] as const) {
      expect(invoicePill(invoiceRow('a', { fiscal_status: fiscal }), 'es')).toEqual({ tone: 'success', label: 'Pagada', busy: false });
    }
  });

  it('reads «Issuing» while a paid invoice waits for the platform hub (its PDF is not there yet)', () => {
    for (const fiscal of ['', 'issuing', 'rejected'] as const) {
      expect(invoicePill(invoiceRow('a', { fiscal_status: fiscal }), 'es')).toEqual({ tone: 'info', label: 'Emitiéndose', busy: true });
    }
  });

  it('reads a cancelled one with the server’s own word, neutral', () => {
    expect(invoicePill(invoiceRow('a', { payment_status: 'void', payment_status_label: 'Anulada' }), 'es')).toEqual({ tone: 'neutral', label: 'Anulada', busy: false });
  });
});

describe('invoiceName', () => {
  it('is our number once paid, else Stripe’s reference', () => {
    expect(invoiceName(invoiceRow('a', { number: 'ERP-2026-00123' }))).toBe('ERP-2026-00123');
    expect(invoiceName(invoiceRow('a', { number: null, reference: 'A1B2C3-0004' }))).toBe('A1B2C3-0004');
  });
});

describe('graceEnd', () => {
  it('is 7 days after the invoice went unpaid (PLAN-SAAS §3.3)', () => {
    expect(graceEnd('2026-10-10T08:00:00Z')).toBe('2026-10-17T08:00:00.000Z');
  });

  it('is empty without a date', () => {
    expect(graceEnd(null)).toBe('');
  });
});

describe('yearOptions', () => {
  it('offers this year and the four before it, the newest first', () => {
    expect(yearOptions(new Date('2026-10-14T10:00:00Z'))).toEqual([2026, 2025, 2024, 2023, 2022]);
  });
});

describe('invoiceBusinesses', () => {
  it('lists the businesses whose invoices the account sees: the ones it owns or pays, by name', () => {
    const rows = [
      businessRow('plaza', 'Bar La Plaza'),
      businessRow('salon', 'Peluquería Ana', { role: 'hub_manager', is_payer: false }),
      businessRow('bakery', 'Panadería López'),
      businessRow('norte', 'Bar Norte', { role: 'hub_admin', is_payer: true }),
    ];
    expect(invoiceBusinesses(rows, 'es').map((row) => row.id)).toEqual(['plaza', 'norte', 'bakery']);
  });
});

describe('formatAmount', () => {
  it('says cents in the invoice’s currency (Stripe writes it in lower case) and the person’s language', () => {
    expect(formatAmount(3629, 'eur', 'es')).toBe('36,29\u00a0€');
    expect(formatAmount(3629, 'EUR', 'en')).toBe('€36.29');
    expect(formatAmount(-1000, 'eur', 'en')).toBe('-€10.00');
  });

  it('falls back to euros without a currency', () => {
    expect(formatAmount(500, '', 'en')).toBe('€5.00');
  });
});

describe('cardBrand', () => {
  it('names the card as its brand writes itself', () => {
    expect(cardBrand('visa')).toBe('Visa');
    expect(cardBrand('mastercard')).toBe('Mastercard');
    expect(cardBrand('amex')).toBe('American Express');
    expect(cardBrand('diners')).toBe('Diners Club');
    expect(cardBrand('unionpay')).toBe('UnionPay');
    expect(cardBrand('jcb')).toBe('JCB');
    expect(cardBrand('discover')).toBe('Discover');
    expect(cardBrand('')).toBe('');
  });
});
