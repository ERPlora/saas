// The banner of an invoice Stripe could not charge, on top of Invoices (mockups `billing.html` «past-due»,
// «suspended-norte», «card-updated»; README §4, §6.18 and §6.20; UX-AUDIT-4 R2, X-34): how much, of which
// business, which invoice and since when; until when the business still works (7 days of grace) or that it
// is suspended and nothing is deleted. On the web «Pay the invoice» is the main action; after a declined card
// «Change card» is, and «Pay» waits with the reason next to it. Once the card changed, the banner says so and
// «Pay» is back. Inside the apps, how to pay it, without a button nor a link.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { unpaidRow } from '../__tests__/billing-fixtures';
import { businessRow, PLAZA } from '../__tests__/fixtures';
import { flush, mountBilling } from '../__tests__/mount-billing';
import { browser } from '../browser';
import UnpaidInvoiceNotice from './UnpaidInvoiceNotice.vue';

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

const DECLINED = unpaidRow('i1', { pay_blocked_reason: 'card_change_required', can: { pay: false, pdf: false } });

async function notice(props: Record<string, unknown>, locale: 'en' | 'es' = 'en', api?: () => Response) {
  const s = await mountBilling(UnpaidInvoiceNotice, { props, locale, api });
  const q = (id: string) => s.wrapper.find(`[data-testid="${id}"]`);
  return { ...s, q };
}

describe('UnpaidInvoiceNotice', () => {
  it('names the amount, the business and the invoice, and until when the business works', async () => {
    const s = await notice({ invoice: unpaidRow('i1', { reference: 'A1B2-0004' }), business: { ...PLAZA, unpaid_reason: 'payment_failed' } });
    expect(s.wrapper.find('.heading').text()).toBe('We could not collect €36.29 from Bar La Plaza');
    expect(s.q('unpaid-body').text()).toBe(
      'Invoice A1B2-0004 of Oct 10, 2026 could not be collected. Pay it before Oct 17, 2026 or the business is suspended; nothing is deleted.',
    );
    expect(s.wrapper.attributes('role')).toBe('alert');
    expect(s.wrapper.attributes('data-tone')).toBe('danger');
  });

  it('dates are days, never the hour (audit 2026-10-14, R-15)', async () => {
    const s = await notice({ invoice: unpaidRow('i1', { date: '2026-10-10T14:23:00Z' }), business: { ...PLAZA, unpaid_reason: 'payment_failed' } });
    expect(s.q('unpaid-body').text()).toBe(
      'Invoice REF-i1 of Oct 10, 2026 could not be collected. Pay it before Oct 17, 2026 or the business is suspended; nothing is deleted.',
    );
    expect(s.wrapper.text()).not.toMatch(/\d{1,2}:\d{2}/);
  });

  it('on the web, «Pay the invoice» is the main action', async () => {
    const s = await notice({ invoice: unpaidRow('i1'), business: { ...PLAZA, unpaid_reason: 'payment_failed' } });
    expect(s.q('pay-invoice').text()).toBe('Pay the invoice · €36.29');
    expect(s.q('pay-invoice').attributes('fill')).toBe('solid');
    expect(s.q('unpaid-change-card').exists()).toBe(false);
  });

  it('after a declined card, «Change card» is the main action and «Pay» waits, saying why', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await notice({ invoice: DECLINED, business: PLAZA }, 'en', () => Response.json({ url: 'https://billing.stripe.com/p/session/x' }));
    expect(s.q('unpaid-body').text()).toMatch(/^The bank declined the card\. Invoice /);
    expect((s.q('pay-invoice').element as HTMLElement & { disabled: boolean }).disabled).toBe(true);
    expect(s.q('pay-invoice').attributes('fill')).toBe('outline');
    const hint = s.q('unpaid-why');
    expect(hint.text()).toBe('Change the card first: we do not charge the card the bank declined again.');
    const host = s.q('pay-invoice').element;
    expect(host.getAttribute('aria-describedby') ?? host.shadowRoot?.querySelector('button')?.getAttribute('aria-describedby')).toBe(hint.attributes('id'));
    await s.q('unpaid-change-card').trigger('click');
    await flush();
    expect(s.calls()).toEqual([{ method: 'POST', path: '/api/billing/portal', body: { hub_id: 'plaza' }, query: {} }]);
    expect(assign).toHaveBeenCalledWith('https://billing.stripe.com/p/session/x');
  });

  it('once the card changed, it says so and «Pay» is back', async () => {
    const s = await notice({ invoice: unpaidRow('i1'), business: { ...PLAZA, unpaid_reason: 'card_changed' } });
    expect(s.wrapper.attributes('data-tone')).toBe('success');
    expect(s.wrapper.attributes('role')).toBe('status');
    expect(s.wrapper.find('.heading').text()).toBe('Card changed');
    expect(s.q('unpaid-body').text()).toBe('You can now pay the invoice of Bar La Plaza (€36.29) with it.');
    expect((s.q('pay-invoice').element as HTMLElement & { disabled: boolean }).disabled).toBe(false);
  });

  it('a suspended business: it waits for the payment, and nothing is deleted', async () => {
    const norte = businessRow('norte', 'Bar Norte', { status: 'suspended', unpaid_reason: 'card_declined', unpaid_since: '2026-10-02T08:00:00Z' });
    const s = await notice({ invoice: { ...DECLINED, business: { id: 'norte', name: 'Bar Norte' }, date: '2026-10-02' }, business: norte });
    expect(s.wrapper.find('.heading').text()).toBe('Bar Norte is suspended: €36.29 unpaid');
    expect(s.q('unpaid-body').text()).toBe(
      'The bank declined the card. Invoice REF-i1 of Oct 2, 2026 could not be collected and the business was suspended. Your data is safe: once it is paid, the business works again at once.',
    );
  });

  it('another account pays the business: no button, only why', async () => {
    const s = await notice({ invoice: unpaidRow('i1', { pay_blocked_reason: 'payer_required', can: { pay: false, pdf: false } }), business: null });
    expect(s.q('pay-invoice').exists()).toBe(false);
    expect(s.q('unpaid-why').text()).toBe('Only the account that pays this business can pay its invoices.');
    expect(s.q('unpaid-body').text()).toBe('Invoice REF-i1 of Oct 10, 2026 could not be collected. Pay it soon or the business is suspended; nothing is deleted.');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it says how to pay, without a button nor a link', async (surface) => {
    applySurface(surface);
    const s = await notice({ invoice: DECLINED, business: PLAZA });
    expect(s.q('pay-invoice').exists()).toBe(false);
    expect(s.q('unpaid-change-card').exists()).toBe(false);
    expect(s.wrapper.findAll('[href]')).toEqual([]);
    if (surface === 'account') {
      // Already in the browser (the account the app opens): why, not where (audit 2 S-09).
      expect(s.q('unpaid-app').text()).toBe('This account was opened from the app: invoices are not paid from here.');
      return;
    }
    expect(s.q('unpaid-app').text()).toBe('To change the card and pay it, go to erplora.com in your browser.');
    const plain = await notice({ invoice: unpaidRow('i2'), business: { ...PLAZA, unpaid_reason: 'payment_failed' } });
    expect(plain.q('unpaid-app').text()).toBe('To pay it, go to erplora.com in your browser.');
  });

  it('speaks Spanish', async () => {
    const s = await notice({ invoice: DECLINED, business: PLAZA }, 'es');
    expect(s.wrapper.find('.heading').text()).toBe('No pudimos cobrar 36,29 € de Bar La Plaza');
    expect(s.q('unpaid-body').text()).toBe(
      'El banco rechazó la tarjeta. La factura REF-i1 del 10 oct 2026 no se pudo cobrar. Págala antes del 17 oct 2026 o el negocio se suspende; no se borra nada.',
    );
    expect(s.q('unpaid-change-card').text()).toBe('Cambiar tarjeta');
  });
});
