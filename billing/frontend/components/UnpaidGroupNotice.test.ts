// Two or more invoices Stripe could not charge, on top of Invoices, in ONE banner (mockups `billing.html`
// «past-due-two»; audit 2026-10-14, R-15: one banner per business took half the page at 1024 px): «2 unpaid
// invoices: €72.58», then each business on its own line — the suspended ones first — with what happens to it
// and its amount, the dates as days (never the hour). On the web each line has its own action: «Pay the
// invoice», or after a declined card «Change card» first and «Pay» waiting, said why. Another account paying
// the business: only why. Inside the apps no button, only where to pay them.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { unpaidRow } from '../__tests__/billing-fixtures';
import { businessRow, PLAZA } from '../__tests__/fixtures';
import { describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import { browser } from '../browser';
import type { UnpaidItem } from '../unpaid';
import UnpaidGroupNotice from './UnpaidGroupNotice.vue';

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

const NORTE = businessRow('norte', 'Bar Norte', { status: 'suspended', unpaid_reason: 'card_declined', unpaid_since: '2026-10-02T08:00:00Z' });
const OPEN_PLAZA = unpaidRow('i1', { total_cents: 3629 });
const DECLINED_NORTE = unpaidRow('i2', {
  business: { id: 'norte', name: 'Bar Norte' },
  date: '2026-10-02',
  total_cents: 3629,
  pay_blocked_reason: 'card_change_required',
  can: { pay: false, pdf: false },
});
/** As the account's list sends them: Bar La Plaza first, Bar Norte (suspended) after. */
const ITEMS: UnpaidItem[] = [
  { invoice: OPEN_PLAZA, business: { ...PLAZA, unpaid_reason: 'payment_failed' } },
  { invoice: DECLINED_NORTE, business: NORTE },
];

async function setup(items: UnpaidItem[] = ITEMS, locale: 'en' | 'es' = 'en', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({})) {
  const s = await mountBilling(UnpaidGroupNotice, { props: { items }, locale, api: (call) => api(describeCall(call)) });
  const lines = () => s.wrapper.findAll('[data-testid="unpaid-group-item"]');
  const line = (id: string) => s.wrapper.get(`[data-testid="unpaid-group-item"][data-id="${id}"]`);
  return { ...s, lines, line };
}

describe('UnpaidGroupNotice', () => {
  it('one danger banner: how many and how much in all, then each business on its own line, the suspended first', async () => {
    const s = await setup();
    expect(s.wrapper.attributes('role')).toBe('alert');
    expect(s.wrapper.attributes('data-tone')).toBe('danger');
    expect(s.wrapper.find('.heading').text()).toBe('2 unpaid invoices: €72.58');
    expect(s.lines().map((line) => line.get('[data-testid="unpaid-group-text"]').text())).toEqual([
      'Bar Norte is suspended until it is paid (€36.29). The bank declined the card.',
      'Bar La Plaza is suspended on Oct 17, 2026 if it is not paid (€36.29).',
    ]);
    expect(s.line('i2').get('strong').text()).toBe('Bar Norte');
    expect(s.wrapper.get('[data-testid="unpaid-group-footer"]').text()).toBe('Nothing is deleted: once an invoice is paid, its business works again at once.');
  });

  it('the most urgent first, as Businesses orders them: the suspended, then the one suspended soonest (audit 2 S-07)', async () => {
    const norte = businessRow('norte', 'Bar Norte', { status: 'past_due', unpaid_reason: 'payment_failed', unpaid_since: '2026-10-12T08:00:00Z' });
    const plaza = { ...PLAZA, unpaid_reason: 'payment_failed' as const, unpaid_since: '2026-10-10T08:00:00Z' };
    // The invoices come newest first (Bar Norte's), the order of the list.
    const s = await setup([
      { invoice: unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' }, date: '2026-10-12' }), business: norte },
      { invoice: OPEN_PLAZA, business: plaza },
    ]);
    expect(s.lines().map((line) => line.attributes('data-id'))).toEqual(['i1', 'i2']);
    // Only the most urgent is filled (audit 2 S-06).
    expect(s.line('i1').get('[data-testid="pay-invoice"]').attributes('fill')).toBe('solid');
    expect(s.line('i2').get('[data-testid="pay-invoice"]').attributes('fill')).toBe('outline');
  });

  it('a second business with a declined card: its «Change card» outlined too', async () => {
    const plaza = { ...PLAZA, unpaid_reason: 'card_declined' as const, unpaid_since: '2026-10-10T08:00:00Z' };
    const s = await setup([
      { invoice: DECLINED_NORTE, business: NORTE },
      { invoice: unpaidRow('i1', { pay_blocked_reason: 'card_change_required', can: { pay: false, pdf: false } }), business: plaza },
    ]);
    expect(s.line('i2').get('[data-testid="unpaid-group-change-card"]').attributes('fill')).toBe('solid');
    expect(s.line('i1').get('[data-testid="unpaid-group-change-card"]').attributes('fill')).toBe('outline');
  });

  it('dates are days, never the hour', async () => {
    const s = await setup();
    expect(s.wrapper.text()).not.toMatch(/\d{1,2}:\d{2}/);
  });

  it('on the web, «Pay the invoice» on each line that can pay', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(ITEMS, 'en', (call) => (call.path === '/api/billing/invoices/pay' ? Response.json({ url: 'https://invoice.stripe.com/i/plaza' }) : Response.json({})));
    const pay = s.line('i1').get('[data-testid="pay-invoice"]');
    expect(pay.text()).toBe('Pay the invoice · €36.29');
    // Bar La Plaza is not the most urgent (Bar Norte is suspended): its way out is outlined (audit 2 S-06).
    expect(pay.attributes('fill')).toBe('outline');
    expect(s.line('i1').find('[data-testid="unpaid-group-change-card"]').exists()).toBe(false);
    await pay.trigger('click');
    await flush();
    expect(s.calls().filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/api/billing/invoices/pay', body: { id: 'i1' }, query: {} }]);
    expect(assign).toHaveBeenCalledWith('https://invoice.stripe.com/i/plaza');
  });

  it('after a declined card, «Change card» leads that line and its «Pay» waits, saying why', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(ITEMS, 'en', (call) => (call.path === '/api/billing/portal' ? Response.json({ url: 'https://billing.stripe.com/p/session/x' }) : Response.json({})));
    const norte = s.line('i2');
    const change = norte.get('[data-testid="unpaid-group-change-card"]');
    expect(change.text()).toBe('Change card');
    const pay = norte.get('[data-testid="pay-invoice"]');
    expect((pay.element as HTMLElement & { disabled: boolean }).disabled).toBe(true);
    expect(pay.attributes('fill')).toBe('outline');
    const why = norte.get('[data-testid="unpaid-group-why"]');
    expect(why.text()).toBe('Change the card first: we do not charge the card the bank declined again.');
    const host = pay.element;
    expect(host.getAttribute('aria-describedby') ?? host.shadowRoot?.querySelector('button')?.getAttribute('aria-describedby')).toBe(why.attributes('id'));
    await change.trigger('click');
    await flush();
    expect(s.calls()).toEqual([{ method: 'POST', path: '/api/billing/portal', body: { hub_id: 'norte' }, query: {} }]);
    expect(assign).toHaveBeenCalledWith('https://billing.stripe.com/p/session/x');
  });

  it('another account pays the business: that line has no button, only why', async () => {
    const s = await setup([
      { invoice: unpaidRow('i3', { pay_blocked_reason: 'payer_required', can: { pay: false, pdf: false } }), business: null },
      ITEMS[1],
    ]);
    const line = s.line('i3');
    expect(line.find('[data-testid="pay-invoice"]').exists()).toBe(false);
    expect(line.get('[data-testid="unpaid-group-why"]').text()).toBe('Only the account that pays this business can pay its invoices.');
    expect(line.get('[data-testid="unpaid-group-text"]').text()).toBe('Bar La Plaza is suspended if it is not paid soon (€36.29).');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface: no button nor link, only where to pay them', async (surface) => {
    applySurface(surface);
    const s = await setup();
    expect(s.wrapper.find('[data-testid="pay-invoice"]').exists()).toBe(false);
    expect(s.wrapper.find('[data-testid="unpaid-group-change-card"]').exists()).toBe(false);
    expect(s.wrapper.find('[data-testid="unpaid-group-why"]').exists()).toBe(false);
    expect(s.wrapper.findAll('[href]')).toEqual([]);
    if (surface === 'account') {
      // Already in the browser (the account the app opens): why, not «go to erplora.com in your browser» (audit 2 S-09).
      expect(s.wrapper.get('[data-testid="unpaid-group-app"]').text()).toBe('This account was opened from the app: invoices are not paid from here.');
      return;
    }
    expect(s.wrapper.get('[data-testid="unpaid-group-app"]').text()).toBe('To change the card and pay them, go to erplora.com in your browser.');
    const plain = await setup([ITEMS[0], { invoice: unpaidRow('i4', { business: { id: 'cafe', name: 'Café Central' } }), business: null }]);
    expect(plain.wrapper.get('[data-testid="unpaid-group-app"]').text()).toBe('To pay them, go to erplora.com in your browser.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(ITEMS, 'es');
    expect(s.wrapper.find('.heading').text()).toBe('2 facturas sin pagar: 72,58 €');
    expect(s.lines().map((line) => line.get('[data-testid="unpaid-group-text"]').text())).toEqual([
      'Bar Norte está suspendido hasta que se pague (36,29 €). El banco rechazó la tarjeta.',
      'Bar La Plaza se suspende el 17 oct 2026 si no se paga (36,29 €).',
    ]);
    expect(s.wrapper.get('[data-testid="unpaid-group-footer"]').text()).toBe('No se borra nada: al pagar una factura, su negocio vuelve a funcionar al momento.');
    expect(s.line('i2').get('[data-testid="unpaid-group-change-card"]').text()).toBe('Cambiar tarjeta');
    expect(s.line('i1').get('[data-testid="pay-invoice"]').text()).toBe('Pagar la factura · 36,29 €');
  });
});
