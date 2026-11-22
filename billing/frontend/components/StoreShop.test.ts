// The Store on the web: the business it sells to (`?business=` or the first the account owns), its unpaid invoice
// if any, and what it shows while the prices or the businesses load or fail. Plans, the checkout and Modules have
// their own files (`StoreShop.<topic>.test.ts`).
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { BAKERY, CAFE, PLAZA, SALON, businessPage } from '../__tests__/fixtures';
import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { apiError, flush, ionProps, optionValue } from '../__tests__/mount-billing';
import { setup, setUpStoreShop } from '../__tests__/store-shop';

beforeEach(() => {
  // The shop compares a module's `valid_until` with now (`apply`): the fixtures end on Oct 31, 2026, so the
  // clock stays before it. Only the date: the timers stay real (the harness has its own fake clock).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-20T10:00:00Z'));
});

setUpStoreShop();

describe('StoreShop', () => {
  it('sells to the first business the account owns: its businesses to pick, and the plans on sale', async () => {
    const s = await setup();
    expect(s.stream.subs.map((sub) => [sub.op, sub.params])).toEqual([['hubs.business.list', { limit: 100 }]]);
    const options = s.el('store-business').findAll('ion-select-option');
    // Peluquería Ana is managed, not owned: only the owner buys.
    expect(options.map((o) => [optionValue(o), o.text()])).toEqual([
      ['bakery', 'Panadería López · Starter'],
      ['cafe', 'Café Central · Free'],
      ['plaza', 'Bar La Plaza · Starter'],
    ]);
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    const calls = s.calls().map((c) => [c.path, c.query]);
    expect(calls).toEqual(
      expect.arrayContaining([
        ['/api/plans', {}],
        ['/api/apps', { premium: 'true' }],
        ['/api/billing/store', { hub_id: 'bakery' }],
      ]),
    );
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
    expect(s.el('plan-starter').find('[data-testid="plan-current"]').exists()).toBe(true);
  });

  it('without ?business= it sells to the first business that can buy, not one blocked by an unpaid invoice', async () => {
    const s = await setup({ rows: [PLAZA, BAKERY, CAFE] });
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    expect(s.el('store-unpaid').exists()).toBe(false);
  });

  it('?business= chooses the business it came from', async () => {
    const s = await setup({ businessId: 'cafe' });
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'cafe' });
    expect(s.calls().map((c) => c.query.hub_id).filter(Boolean)).toEqual(['cafe']);
    expect(s.el('plan-upgrade').text()).toBe('Upgrade to Starter');
  });

  it('an unknown ?business= falls back to the first one and says so, until another is picked', async () => {
    const s = await setup({ businessId: 'nope' });
    expect(s.el('store-unknown-business').text()).toContain('We could not find that business among yours: here is Panadería López.');
    await s.pick('cafe');
    expect(s.el('store-unknown-business').exists()).toBe(false);
    expect(s.wrapper.emitted('update:businessId')).toEqual([['cafe']]);
    expect(s.calls().at(-1)?.query).toEqual({ hub_id: 'cafe' });
  });

  it('a business with an unpaid invoice: says why, where to pay, and nothing charges', async () => {
    const s = await setup({ businessId: 'plaza' });
    const notice = s.el('store-unpaid');
    expect(notice.text()).toContain('Bar La Plaza has an unpaid invoice');
    expect(notice.text()).toContain('The bank declined the last card.');
    expect(s.el('store-unpaid-billing').attributes('routerlink')).toBe('/dashboard/billing?business=plaza');
    // A declined card cannot pay: no «Pay the invoice» until the card changes.
    expect(s.el('store-unpaid-pay').exists()).toBe(false);
    await s.wrapper.setProps({ tab: 'modules' });
    await flush();
    expect((s.el('module-booking').find('[data-testid="module-add"]').element as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('once the card changed, the notice offers to pay the invoice', async () => {
    const s = await setup({ businessId: 'plaza', rows: [{ ...PLAZA, unpaid_reason: 'card_changed' }] });
    expect(s.el('store-unpaid').text()).toContain('The card was changed: pay the invoice before adding anything.');
    expect(ionProps(s.el('store-unpaid-pay'), 'href')).toEqual({ href: 'https://invoice.stripe.com/i/plaza' });
  });

  it('prices that do not load are said, nothing charged, with «Retry»', async () => {
    let fail = true;
    const s = await setup({ answer: ({ path }) => (path === '/api/plans' && fail ? apiError(502, 'unexpected_response', 'x') : undefined) });
    expect(s.el('store-error').text()).toContain('We could not load the prices');
    expect(s.el('store-error').text()).toContain('Nothing was charged. Try again in a few seconds.');
    fail = false;
    await s.el('store-retry').trigger('click');
    await flush();
    expect(s.el('store-error').exists()).toBe(false);
    expect(s.all('plan-name')).toHaveLength(2);
  });

  it('while it loads, skeleton cards', async () => {
    const s = await setup({ answer: ({ path }) => (path === '/api/billing/store' ? (new Promise(() => {}) as never) : undefined) });
    expect(s.el('store-loading').exists()).toBe(true);
  });

  it('an account that owns no business is told who buys, and where to go', async () => {
    const s = await setup({ rows: [SALON] });
    expect(s.el('store-no-business').text()).toContain('You have no business to buy for');
    expect(s.calls().filter((c) => c.path === '/api/billing/store')).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.text()).toContain('¿Para qué negocio?');
    expect(s.wrapper.text()).toContain('Precios sin IVA.');
  });
});

describe('StoreShop: businesses that do not load are said, never «You have no business to buy for»', () => {
  const states = (s: Awaited<ReturnType<typeof setup>>) => ({
    error: s.el('store-error').exists() ? s.el('store-error').find('.heading').text() : null,
    retry: s.el('store-retry').exists(),
    noBusiness: s.el('store-no-business').exists(),
    loading: s.el('store-loading').exists(),
  });
  const BUSINESSES_ERROR = 'We could not load your businesses';

  it('their query fails: it says so with «Retry», not that there is no business', async () => {
    const s = await setup({ list: 'none' });
    s.stream.push(errorFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, 'internal_error'));
    await flush();
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('nothing in time: skeleton cards until the limit, then the error', async () => {
    const s = await setup({ list: 'none' });
    // The time limit counts from the mount (opening the stream already took 150 ms of it).
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(states(s)).toEqual({ error: null, retry: false, noBusiness: false, loading: true });
    await s.clock.advance(1);
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('the stream refused (/api/live answers 503): it could not load them, it does not say there are none', async () => {
    const s = await setup({ list: 'down' });
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('«Retry» opens the stream again and sells to the businesses that come', async () => {
    const s = await setup({ list: 'none' });
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    await s.el('store-retry').trigger('click');
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(states(s)).toEqual({ error: null, retry: false, noBusiness: false, loading: true });
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage([BAKERY, CAFE] as never), 1));
    await flush();
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
  });

  it('says it in Spanish', async () => {
    const s = await setup({ list: 'down', locale: 'es' });
    expect(s.el('store-error').text()).toContain('No hemos podido cargar tus negocios');
  });
});
