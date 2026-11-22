// What the Store has on sale and what the business it sells to has: the plans and the premium apps (asked again
// when the language changes), that business's catalog (a late answer for a business left behind is dropped), an
// error with «Retry», and what a command left of the subscription, kept until the catalog is asked again.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, shallowRef } from 'vue';

import type { SubscriptionOut } from '../../frontend/sdk-types/store';
import { APPS, catalog, PLANS, storeModule } from './__tests__/fixtures';
import { apiError, describeCall, flush, mountBilling } from './__tests__/mount-billing';
import { useStoreCatalog } from './store-catalog';

beforeEach(() => {
  // `apply` compares a module's `valid_until` with now: the clock stays on Oct 20, 2026. Only the date: the
  // harness keeps its own fake clock.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-20T10:00:00Z'));
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

type Answer = (call: ReturnType<typeof describeCall>) => Response | Promise<Response> | undefined;

async function setup(answer: Answer = () => undefined, hubId: string | null = 'bakery') {
  const business = shallowRef<{ id: string } | null>(hubId ? { id: hubId } : null);
  let store!: ReturnType<typeof useStoreCatalog>;
  const Host = defineComponent({
    setup() {
      store = useStoreCatalog(business);
      return () => null;
    },
  });
  const s = await mountBilling(Host, {
    api: (call) => {
      const described = describeCall(call);
      const custom = answer(described);
      if (custom) return custom;
      if (described.path === '/api/plans') return Response.json(PLANS);
      if (described.path === '/api/apps') return Response.json(APPS);
      if (described.path === '/api/billing/store') return Response.json(catalog(described.query.hub_id));
      return Response.json({});
    },
  });
  await flush();
  const asked = (path: string) => s.calls().filter((call) => call.path === path);
  return { ...s, business, asked, store: () => store };
}

function out(extra: Partial<SubscriptionOut> = {}): SubscriptionOut {
  return {
    hub_id: 'bakery',
    plan: 'standard',
    billing_interval: 'year',
    status: 'active',
    cancel_at_period_end: true,
    current_period_end: '2026-10-31T12:00:00Z',
    trial_end: null,
    modules: [],
    scheduled_change: null,
    ...extra,
  };
}

describe('useStoreCatalog', () => {
  it('asks the plans, the premium apps and what the business has', async () => {
    const s = await setup();
    expect(s.asked('/api/plans')).toHaveLength(1);
    expect(s.asked('/api/apps').map((call) => call.query)).toEqual([{ premium: 'true' }]);
    expect(s.asked('/api/billing/store').map((call) => call.query)).toEqual([{ hub_id: 'bakery' }]);
    expect(s.store().plans.value).toEqual(PLANS.plans);
    expect(s.store().apps.value).toEqual(APPS.apps);
    expect(s.store().catalog.value).toEqual(catalog('bakery'));
    expect(s.store().failed.value).toBe(false);
  });

  it('asks the plans and the apps again when the language changes', async () => {
    const s = await setup();
    s.i18n.global.locale.value = 'es';
    await flush();
    expect(s.asked('/api/plans')).toHaveLength(2);
    expect(s.asked('/api/apps')).toHaveLength(2);
    expect(s.asked('/api/billing/store')).toHaveLength(1);
  });

  it('without a business it asks for no catalog', async () => {
    const s = await setup(undefined, null);
    expect(s.asked('/api/billing/store')).toEqual([]);
    expect(s.store().catalog.value).toBeNull();
  });

  it('another business: its catalog, and a late answer for the one left behind is dropped', async () => {
    let release!: () => void;
    const late = new Promise<Response>((resolve) => {
      release = () => resolve(Response.json(catalog('bakery')));
    });
    const s = await setup(({ path, query }) => (path === '/api/billing/store' && query.hub_id === 'bakery' ? late : undefined));
    s.business.value = { id: 'cafe' };
    await flush();
    expect(s.store().catalog.value?.hub_id).toBe('cafe');
    release();
    await flush();
    expect(s.store().catalog.value?.hub_id).toBe('cafe');
  });

  it('a catalog that fails for a business left behind is not an error', async () => {
    let fail!: () => void;
    const late = new Promise<Response>((resolve) => {
      fail = () => resolve(apiError(502, 'unexpected_response', 'x'));
    });
    const s = await setup(({ path, query }) => (path === '/api/billing/store' && query.hub_id === 'bakery' ? late : undefined));
    s.business.value = { id: 'cafe' };
    await flush();
    fail();
    await flush();
    expect(s.store().failed.value).toBe(false);
  });

  it('what the business has does not load: it fails, and «Retry» asks everything again', async () => {
    let down = true;
    const s = await setup(({ path }) => (path === '/api/billing/store' && down ? apiError(502, 'unexpected_response', 'x') : undefined));
    expect(s.store().failed.value).toBe(true);
    expect(console.error).toHaveBeenCalled();
    down = false;
    s.store().retry();
    expect(s.store().failed.value).toBe(false);
    await flush();
    expect(s.asked('/api/plans')).toHaveLength(2);
    expect(s.asked('/api/billing/store')).toHaveLength(2);
    expect(s.store().catalog.value?.hub_id).toBe('bakery');
    expect(s.store().failed.value).toBe(false);
  });

  it('the prices do not load: it fails', async () => {
    const s = await setup(({ path }) => (path === '/api/apps' ? apiError(502, 'unexpected_response', 'x') : undefined));
    expect(s.store().failed.value).toBe(true);
    expect(s.store().plans.value).toBeNull();
  });

  it('«Retry» without a business asks only the prices again', async () => {
    const s = await setup(undefined, null);
    s.store().retry();
    await flush();
    expect(s.asked('/api/plans')).toHaveLength(2);
    expect(s.asked('/api/billing/store')).toEqual([]);
  });

  it('loadCatalog asks the catalog of a business again', async () => {
    const s = await setup();
    await s.store().loadCatalog('bakery');
    expect(s.asked('/api/billing/store')).toHaveLength(2);
  });

  it('keeps what a command left of the subscription, paying, with the trial it had', async () => {
    const s = await setup(({ path }) =>
      path === '/api/billing/store' ? Response.json(catalog('bakery', { subscription: { ...catalog('x').subscription!, trial_plan: 'starter' } })) : undefined,
    );
    s.store().apply(out({ scheduled_change: undefined as never, trial_end: '2026-11-04T12:00:00Z' }));
    expect(s.store().catalog.value?.subscription).toEqual({
      plan: 'standard',
      billing_interval: 'year',
      status: 'active',
      paying: true,
      cancel_at_period_end: true,
      current_period_end: '2026-10-31T12:00:00Z',
      trial_plan: 'starter',
      trial_end: '2026-11-04T12:00:00Z',
      scheduled_change: null,
    });
  });

  it('a module is owned while the subscription keeps it: with its source and its end, until that end passes', async () => {
    const modules = [storeModule('booking', 900), storeModule('loyalty', 600), storeModule('stock', 500, { owned: true, source: 'purchase' })];
    const s = await setup(({ path }) => (path === '/api/billing/store' ? Response.json(catalog('bakery', { modules })) : undefined));
    s.store().apply(
      out({
        modules: [
          { slug: 'booking', source: 'plan', valid_until: null },
          { slug: 'loyalty', source: 'purchase', valid_until: '2026-10-31T12:00:00Z' },
          { slug: 'stock', source: 'purchase', valid_until: '2026-10-19T12:00:00Z' },
        ],
      }),
    );
    expect(s.store().catalog.value?.modules.map(({ slug, owned, source, valid_until }) => [slug, owned, source, valid_until])).toEqual([
      ['booking', true, 'plan', null],
      ['loyalty', true, 'purchase', '2026-10-31T12:00:00Z'],
      ['stock', false, null, null],
    ]);
    expect(s.store().catalog.value?.modules[0]).toMatchObject({ tier: 'basic', price_monthly_cents: 900, on_sale: true });
  });

  it('what a command left of another business, or before the catalog arrived, is not kept', async () => {
    const s = await setup();
    const before = s.store().catalog.value;
    s.store().apply(out({ hub_id: 'cafe' }));
    expect(s.store().catalog.value).toBe(before);
    const empty = await setup(undefined, null);
    empty.store().apply(out());
    expect(empty.store().catalog.value).toBeNull();
  });
});
