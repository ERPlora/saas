// The unpaid invoices as notices of the action center: one per business with its invoice unpaid, the same on every
// screen. On the web, whoever pays it gets «Pay the invoice · …» (Stripe's page for that invoice) and «Change card»
// (Stripe's Customer Portal); after a declined card only «Change card», since the server refuses the payment until the
// card changes. Whoever does not pay it, or inside the apps, reads the notice without buttons and why.
import { applySurface, type ActionNotice, type NoticeAction } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent } from 'vue';

import { invoicePage, unpaidRow } from './__tests__/billing-fixtures';
import { businessPage, businessRow, SALON } from './__tests__/fixtures';
import { describeCall, flush, mountBilling, type StreamCall } from './__tests__/mount-billing';
import { errorFrame, resultFrame } from '../../hubs/frontend/__tests__/mount-hubs';
import type { InvoiceRowOut } from '../../frontend/sdk-types/billing-invoices';
import type { BusinessRowOut } from '../../frontend/sdk-types/hubs';
import { browser } from './browser';
import { useUnpaidNotices } from './notices';
import { PAYING_STORAGE_KEY } from './pay';

const NOW = new Date('2026-10-13T08:00:00Z');

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  applySurface('web');
  sessionStorage.clear();
  document.body.innerHTML = '';
});

/** Payment pending since 3 days ago: its grace ends on Oct 17. */
const DUE = businessRow('plaza', 'Bar La Plaza', {
  status: 'past_due',
  unpaid_reason: 'payment_failed',
  unpaid_since: '2026-10-10T08:00:00Z',
  pay_url: 'https://invoice.stripe.com/i/plaza',
});
const NORTE = businessRow('norte', 'Bar Norte', {
  status: 'suspended',
  unpaid_reason: 'payment_failed',
  unpaid_since: '2026-10-02T08:00:00Z',
  pay_url: 'https://invoice.stripe.com/i/norte',
});
const OPEN = unpaidRow('i1', { total_cents: 2900 });
const DECLINED = unpaidRow('i1', { total_cents: 2900, pay_blocked_reason: 'card_change_required', can: { pay: false, pdf: false } });
const ELSEWHERE = unpaidRow('i1', { total_cents: 2900, pay_blocked_reason: 'payer_required', can: { pay: false, pdf: false } });

const CONSEQUENCE = 'If it is not paid by Oct 17, 2026, the business is suspended. Nothing is deleted.';

async function setup(locale: 'en' | 'es' = 'en', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({})) {
  let source!: ReturnType<typeof useUnpaidNotices>;
  const Host = defineComponent({
    setup() {
      source = useUnpaidNotices();
      return () => null;
    },
  });
  const s = await mountBilling(Host, { locale, api: (call) => api(describeCall(call)) });
  const call: StreamCall = await s.live();
  const show = async (businesses: BusinessRowOut[], open: InvoiceRowOut[]) => {
    call.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage(businesses), 1));
    call.push(resultFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, invoicePage(open), 1));
    await flush();
  };
  const notices = () => source.notices.value;
  return { ...s, call, show, notices, source: () => source };
}

/** One notice, shown with only the labels of its actions. */
async function only(business: BusinessRowOut, invoice: InvoiceRowOut | null, locale: 'en' | 'es' = 'en') {
  const s = await setup(locale);
  await s.show([business], invoice ? [invoice] : []);
  expect(s.notices()).toHaveLength(1);
  return labelled(s.notices()![0]);
}

const label = (action: NoticeAction | undefined) => (action ? { label: action.label } : undefined);
const labelled = (notice: ActionNotice) => ({ ...notice, action: label(notice.action), secondary: label(notice.secondary) });

describe('useUnpaidNotices', () => {
  it('one urgent notice per business with its invoice unpaid: what it owes, how long it has and its way out', async () => {
    expect(await only(DUE, OPEN)).toEqual({
      id: 'billing.unpaid:plaza',
      severity: 'danger',
      icon: 'ion:card-outline',
      label: 'Bar La Plaza has an unpaid invoice',
      title: 'Bar La Plaza has an unpaid invoice',
      figure: '€29.00',
      chip: '4 days left',
      due: { from: '2026-10-10T08:00:00Z', at: '2026-10-17T08:00:00.000Z' },
      body: CONSEQUENCE,
      action: { label: 'Pay the invoice · €29.00' },
      secondary: { label: 'Change card' },
    });
  });

  it.each([
    ['«Pay the invoice» goes to Stripe’s page for that invoice, remembered for «Invoice paid»', 'action', '/api/billing/invoices/pay', { id: 'i1' }, 'i1'],
    ['«Change card» opens the Customer Portal of the business’s payer', 'secondary', '/api/billing/portal', { hub_id: 'plaza' }, null],
  ] as const)('%s', async (_, which, path, body, remembered) => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const page = `https://stripe.test${path}`;
    const s = await setup('en', (call) => Response.json(call.path === path ? { url: page } : {}));
    await s.show([DUE], [OPEN]);
    await s.notices()![0][which]?.run?.();
    expect([s.calls(), assign.mock.calls]).toEqual([[{ method: 'POST', path, body, query: {} }], [[page]]]);
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBe(remembered);
  });

  it('after a declined card «Change card» is the only way out, and it says why', async () => {
    const notice = await only({ ...DUE, unpaid_reason: 'card_declined' }, DECLINED);
    expect(notice.action).toEqual({ label: 'Change card' });
    expect(notice.secondary).toBeUndefined();
    expect(notice.body).toBe(`The bank declined the card. ${CONSEQUENCE}`);
  });

  it('once the card changed, it says so and «Pay the invoice» is back', async () => {
    const notice = await only({ ...DUE, unpaid_reason: 'card_changed' }, OPEN);
    expect(notice.body).toBe(`Card changed: you can pay it now. ${CONSEQUENCE}`);
    expect(notice.action).toEqual({ label: 'Pay the invoice · €29.00' });
  });

  it('a suspended business: the deadline already passed, and nothing is deleted', async () => {
    const notice = await only(NORTE, unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' } }));
    expect(notice.chip).toBe('suspended');
    expect(notice.due).toEqual({ from: '2026-10-02T08:00:00Z', at: '2026-10-09T08:00:00.000Z' });
    expect(notice.body).toBe('It was suspended because of an unpaid invoice. Nothing is deleted: once it is paid it works again at once.');
  });

  it.each([
    ['2026-10-08T00:00:00Z', '2 days left'],
    ['2026-10-06T20:00:00Z', 'last day'],
    ['2026-10-05T00:00:00Z', 'last day'],
  ])('unpaid since %s: «%s»', async (since, chip) => {
    expect((await only({ ...DUE, unpaid_since: since }, OPEN)).chip).toBe(chip);
  });

  it('the days left follow the clock', async () => {
    const s = await setup();
    await s.show([DUE], [OPEN]);
    vi.setSystemTime(new Date('2026-10-14T08:00:00Z'));
    await s.clock.advance(60_000);
    await flush();
    expect(s.notices()![0].chip).toBe('3 days left');
  });

  it('without the day it went unpaid: the general sentence, no countdown it cannot know', async () => {
    const notice = await only({ ...DUE, unpaid_since: null }, OPEN);
    expect(notice.chip).toBeUndefined();
    expect(notice.due).toBeUndefined();
    expect(notice.body).toBe('If it is not paid soon, the business is suspended. Nothing is deleted.');
  });

  it('another account pays the business: no button, only who can pay it', async () => {
    const notice = await only({ ...DUE, pay_url: null, is_payer: false }, ELSEWHERE);
    expect(notice.action).toBeUndefined();
    expect(notice.secondary).toBeUndefined();
    expect(notice.body).toBe(`${CONSEQUENCE} Only the account that pays this business can pay its invoices.`);
  });

  it('without Stripe’s link to pay it, no «Pay the invoice»: its payer still changes the card', async () => {
    const notice = await only({ ...DUE, pay_url: null }, OPEN);
    expect(notice.action).toEqual({ label: 'Change card' });
    expect(notice.secondary).toBeUndefined();
    expect(notice.body).toBe(CONSEQUENCE);
  });

  it('another account is charged for it (after a hand-over): who can pay it, whatever this one owns', async () => {
    const notice = await only(DUE, ELSEWHERE);
    expect([notice.action, notice.secondary]).toEqual([undefined, undefined]);
    expect(notice.body).toBe(`${CONSEQUENCE} Only the account that pays this business can pay its invoices.`);
  });

  it('its invoice not in the account’s list: no amount, and «Change card» alone', async () => {
    const notice = await only(DUE, null);
    expect(notice.figure).toBeUndefined();
    expect(notice.action).toEqual({ label: 'Change card' });
    expect(notice.secondary).toBeUndefined();
  });

  it.each(['desktop', 'mobile'] as const)('inside the %s app: no button, and where to pay it', async (surface) => {
    applySurface(surface);
    const plain = await only(DUE, OPEN);
    expect([plain.action, plain.secondary]).toEqual([undefined, undefined]);
    expect(plain.body).toBe(`${CONSEQUENCE} To pay it, go to erplora.com in your browser.`);
    const declined = await only({ ...DUE, unpaid_reason: 'card_declined' }, DECLINED);
    expect(declined.body).toBe(`The bank declined the card. ${CONSEQUENCE} To change the card and pay it, go to erplora.com in your browser.`);
  });

  it('the account the app opens in the browser: why it pays nothing here', async () => {
    applySurface('account');
    const notice = await only(DUE, OPEN);
    expect(notice.action).toBeUndefined();
    expect(notice.body).toBe(`${CONSEQUENCE} This account was opened from the app: invoices are not paid from here.`);
  });

  it('several businesses, several notices; the action center orders them', async () => {
    const s = await setup();
    await s.show([DUE, SALON, NORTE], [OPEN, unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' } })]);
    expect(s.notices()!.map((notice) => notice.id)).toEqual(['billing.unpaid:plaza', 'billing.unpaid:norte']);
  });

  it('loading, nothing yet; nothing owed, no notice', async () => {
    const s = await setup();
    expect(s.notices()).toBeUndefined();
    await s.show([SALON], []);
    expect(s.notices()).toEqual([]);
  });

  it('a list that fails says so, and «Retry» asks again', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, 'internal_error'));
    await flush();
    expect(s.source().failed.value).toBe(true);
    const before = s.net.streams.length;
    s.source().retry?.();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
  });

  it('speaks Spanish', async () => {
    expect(await only(DUE, OPEN, 'es')).toMatchObject({
      title: 'Bar La Plaza tiene una factura sin pagar',
      figure: '29,00 €',
      chip: 'quedan 4 días',
      body: 'Si no se paga antes del 17 oct 2026, el negocio se suspende. No se borra nada.',
      action: { label: 'Pagar la factura · 29,00 €' },
      secondary: { label: 'Cambiar tarjeta' },
    });
    expect((await only(NORTE, null, 'es')).chip).toBe('suspendido');
    expect((await only({ ...DUE, unpaid_since: '2026-10-06T20:00:00Z' }, OPEN, 'es')).chip).toBe('último día');
  });
});
