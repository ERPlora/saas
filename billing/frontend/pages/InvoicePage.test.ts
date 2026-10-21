// The page of one ERPlora invoice (`/billing/invoices/:id`, BILLING-G05; the old «Detalle de factura» and the
// «View» of `/dashboard/billing/invoices/`, BILLING-G92): live (`billing.invoice.get`), with Back to Invoices:
//   - its number (or Stripe's reference while it is not collected), date, business, status and fiscal status;
//   - its lines (what it charges, the period, net, VAT and total) and the totals;
//   - who it is made out to, as on the day it was issued;
//   - a credit note says its type and reason and links the invoice it rectifies;
//   - «Download PDF» once issued and «Pay» (web only) while it is not collected;
//   - loading, and a failure (or an invoice that is not the account's) said with «Retry».
import { afterEach, describe, expect, it } from 'vitest';

import { invoiceRow, unpaidRow } from '../__tests__/billing-fixtures';
import { errorFrame, HELLO } from '../../../hubs/frontend/__tests__/mount-hubs';
import { flush, mountBilling, subId } from '../__tests__/mount-billing';
import type { InvoiceDetailOut } from '../../../frontend/sdk-types';
import InvoicePage from './InvoicePage.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

function detail(extra: Partial<InvoiceDetailOut> = {}): InvoiceDetailOut {
  return {
    ...invoiceRow('00042'),
    issued_on: '2026-10-01',
    paid_at: '2026-10-01T09:00:00Z',
    tax_treatment: 'standard',
    tax_country: 'ES',
    tax_rate: '21.00',
    recipient: {
      name: 'Panadería López SL',
      tax_id: 'B12345678',
      address: 'Calle Mayor 1',
      city: 'Madrid',
      postal_code: '28001',
      country: 'ES',
      email: 'facturas@panaderia.example',
    },
    lines: [
      {
        position: 1,
        description: 'Starter (monthly)',
        item_kind: 'plan',
        item_slug: 'starter',
        quantity: 1,
        proration: false,
        period_start: '2026-10-01T00:00:00Z',
        period_end: '2026-11-01T00:00:00Z',
        tax_rate: '21.00',
        net_cents: 1999,
        tax_cents: 420,
        total_cents: 2419,
      },
      {
        position: 2,
        description: 'Bookings',
        item_kind: 'module',
        item_slug: 'booking',
        quantity: 1,
        proration: true,
        period_start: '2026-10-15T00:00:00Z',
        period_end: '2026-11-01T00:00:00Z',
        tax_rate: '21.00',
        net_cents: 1000,
        tax_cents: 210,
        total_cents: 1210,
      },
    ],
    rectifies: null,
    qr: 'https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B00000000',
    ...extra,
  };
}

async function setup(invoice: InvoiceDetailOut | null, options: { locale?: 'en' | 'es'; path?: string } = {}) {
  const m = await mountBilling(InvoicePage, { locale: options.locale, path: options.path, props: { id: invoice?.id ?? '00042' } });
  const stream = await m.live();
  stream.push(HELLO);
  if (invoice) await m.result(stream, 'billing.invoice.get', invoice);
  await flush();
  const el = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => m.wrapper.findAll(`[data-testid="${id}"]`);
  return { ...m, stream, el, all };
}

describe('InvoicePage (BILLING-G05)', () => {
  it('asks the server for that invoice, live, and goes back to Invoices', async () => {
    const s = await setup(detail());
    expect(s.client.stream.subscriptions('billing.invoice.get')[0].params).toEqual({ id: '00042' });
    expect(s.el('invoice-title').text()).toBe('Invoice ERP-2026-00042');
    await s.el('topbar-back').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/billing/invoices');
  });

  it('says its date, business, status and fiscal status', async () => {
    const s = await setup(detail());
    const summary = s.el('invoice-summary').text();
    expect(summary).toContain('Oct 1, 2026');
    expect(summary).toContain('Panadería López');
    expect(summary).toContain('Paid');
    expect(summary).toContain('Accepted');
  });

  it('lists what it charges, with the period, and adds it up', async () => {
    const s = await setup(detail());
    const lines = s.all('invoice-line');
    expect(lines).toHaveLength(2);
    expect(lines[0].text()).toContain('Starter (monthly)');
    expect(lines[0].text()).toContain('Oct 1, 2026 – Nov 1, 2026');
    expect(lines[0].text()).toContain('€19.99');
    expect(lines[0].text()).toContain('21%');
    expect(lines[0].text()).toContain('€24.19');
    expect(lines[1].text()).toContain('Prorated');
    const totals = s.el('invoice-totals').text();
    expect(totals).toContain('€29.99');
    expect(totals).toContain('€6.30');
    expect(totals).toContain('€36.29');
  });

  it('says who it is made out to', async () => {
    const s = await setup(detail());
    const to = s.el('invoice-recipient').text();
    expect(to).toContain('Panadería López SL');
    expect(to).toContain('B12345678');
    expect(to).toContain('Calle Mayor 1, 28001 Madrid');
  });

  it('a credit note says its type and reason and links the invoice it rectifies', async () => {
    const s = await setup(
      detail({
        kind: 'credit_note',
        kind_label: 'Credit note',
        number: 'ERPR-2026-00003',
        rectification: { type: 'R1', reason: 'Duplicate charge' },
        rectifies: { id: '00042', number: 'ERP-2026-00042' },
      }),
    );
    expect(s.el('invoice-title').text()).toBe('Credit note ERPR-2026-00003');
    expect(s.el('invoice-rectification').text()).toContain('Credit note R1 · Duplicate charge');
    expect(s.el('invoice-rectified-link').attributes('href') ?? s.el('invoice-rectified-link').attributes('router-link')).toContain('/billing/invoices/00042');
  });

  it('issued: «Download PDF»; not collected: no number yet, «Pay» and no PDF', async () => {
    const issued = await setup(detail());
    expect(issued.el('invoice-pdf').exists()).toBe(true);
    expect(issued.el('pay-invoice').exists()).toBe(false);
    const unpaid = await setup(detail({ ...unpaidRow('00043'), id: '00043' }));
    expect(unpaid.el('invoice-title').text()).toBe('Invoice REF-00043 (not collected)');
    expect(unpaid.el('pay-invoice').exists()).toBe(true);
    expect(unpaid.el('invoice-pdf').exists()).toBe(false);
  });

  it('while it loads, a skeleton; a failure is said with «Retry»', async () => {
    const loading = await setup(null);
    expect(loading.el('invoice-loading').exists()).toBe(true);
    const failed = await setup(null);
    failed.stream.push(errorFrame(subId(failed.client, 'billing.invoice.get'), 'not_found'));
    await flush();
    expect(failed.el('invoice-error').text()).toContain('We could not load this invoice');
    expect(failed.el('invoice-retry').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(detail(), { locale: 'es' });
    expect(s.el('invoice-title').text()).toBe('Factura ERP-2026-00042');
    expect(s.el('invoice-recipient').text()).toContain('A nombre de');
    expect(s.el('invoice-totals').text()).toContain('Base imponible');
  });
});
