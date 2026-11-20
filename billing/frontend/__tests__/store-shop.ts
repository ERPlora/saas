// The Store on the web (`StoreShop`) mounted for its tests: the account's businesses arrive through the live list,
// and the server answers the plans, the premium apps and each business's catalog. A test file mocks `@ionic/vue`
// and `@erplora/ui/shell` as the panel's tests do, freezes the clock itself (the frozen-dates guard reads the test
// file) and calls `setUpStoreShop()` at its top.
import { toastInfo, toastSuccess } from '@erplora/ui/shell';
import { afterEach, vi } from 'vitest';

import StoreShop from '../components/StoreShop.vue';
import { APPS, BAKERY, CAFE, catalog, FREE_SUBSCRIPTION, PLANS, PLAZA, SALON, businessPage, storeModule } from './fixtures';
import { flush, mountBilling, type StreamCall } from './mount-billing';

export function setUpStoreShop(): void {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(toastSuccess).mockClear();
    vi.mocked(toastInfo).mockClear();
    document.body.innerHTML = '';
  });
}

type Answer = (call: { method: string; path: string; query: Record<string, string>; body: unknown }) => Response | undefined;

/** The server: catalogs by business (Panadería pays Starter, Café is on Free, Bar La Plaza owes). */
const CATALOGS: Record<string, ReturnType<typeof catalog>> = {
  bakery: catalog('bakery', { modules: [storeModule('booking', 900), storeModule('loyalty', 600, { owned: true, source: 'purchase', valid_until: '2026-10-31T12:00:00Z' })] }),
  cafe: catalog('cafe', { subscription: FREE_SUBSCRIPTION }),
  plaza: catalog('plaza'),
};

/** `list`: the account's businesses arrive (`result`, by default), nothing arrives yet (`none`), or the stream
 *  is refused (`down`: `/api/live` answers 503). */
export async function setup(
  options: { tab?: 'plans' | 'modules'; businessId?: string; rows?: unknown[]; answer?: Answer; locale?: 'en' | 'es'; list?: 'result' | 'none' | 'down' } = {},
) {
  const answer = options.answer ?? (() => undefined);
  const m = await mountBilling(StoreShop, {
    locale: options.locale,
    props: { tab: options.tab ?? 'plans', businessId: options.businessId },
    stubs: { CheckoutModal: true, ProrationDialog: true, AnnualSwitchDialog: true },
    api: (call) => {
      const url = new URL(call.url, 'http://localhost');
      const described = {
        method: (call.init.method ?? 'GET').toUpperCase(),
        path: url.pathname,
        query: Object.fromEntries(url.searchParams.entries()),
        body: typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined,
      };
      const custom = answer(described);
      if (custom) return custom;
      if (described.path === '/api/plans') return Response.json(PLANS);
      if (described.path === '/api/apps') return Response.json(APPS);
      if (described.path === '/api/billing/store') return Response.json(CATALOGS[described.query.hub_id]);
      return Response.json({});
    },
  });
  const list = options.list ?? 'result';
  if (list === 'down') m.liveDown.value = true;
  const stream = list === 'down' ? (await m.clock.advance(150), undefined) : await m.live();
  if (stream && list === 'result') await m.result(stream, 'hubs.business.list', businessPage((options.rows ?? [BAKERY, CAFE, PLAZA, SALON]) as never));
  await flush();
  const el = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => m.wrapper.findAll(`[data-testid="${id}"]`);
  const pick = async (id: string) => {
    el('store-business').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: id } }));
    await flush();
  };
  return { ...m, stream: stream as StreamCall, el, all, pick };
}
