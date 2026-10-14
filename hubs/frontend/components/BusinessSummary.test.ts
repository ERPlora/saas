// The Summary of a business (mockups `business.html` «summary», PLAN-SAAS §3.6): its plan (what it
// covers, the trial; changing it is the Store's, web only) with its people against the places of the
// plan, the usage the Hub measured last night (storage against the plan, the people active; PLAN-SAAS §5),
// «On your devices» and its details. Deleted, only the plan (cancelled) and the details.
import { UsageCounter, UsageMeter } from '@erplora/ui/components';
import { applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { describeCall, flush, mountHubs } from '../__tests__/mount-hubs';
import BusinessSummary from './BusinessSummary.vue';
import DeviceAccessCard from './DeviceAccessCard.vue';

const PLANS = {
  signup_trial_days: 14,
  cheapest_slug: 'free',
  plans: [
    { slug: 'free', name: 'Free', max_users: 3, max_devices: 1 },
    { slug: 'starter', name: 'Starter', max_users: 0, max_devices: 0 },
  ],
};
const BUSINESS = {
  id: 'h1',
  slug: 'bakery',
  name: 'Panadería López',
  host: 'bakery.erplora.com',
  country: 'ES',
  timezone: 'Europe/Madrid',
  language: 'es',
  business_type: { code: 'bakery', name: 'Bakery and pastry' },
  status: 'active',
  status_label: 'Active',
  hub_error: null,
  ready_at: '2026-03-02T10:00:00Z',
  created_at: '2026-03-02T10:00:00Z',
  deletion_requested_at: null,
  purge_after: null,
  role: 'hub_owner',
  role_label: 'Owner',
  plan: { slug: 'free', name: 'Free' },
  trial_plan: null,
  trial_end: null,
  seats: { used: 2, limit: 3 },
  pending_transfer: null,
  can: { open: true, manage_members: true, manage_settings: true, manage_billing: true, transfer: true, delete: true },
  usage: null,
};
/** What the Hub measured yesterday (the clock is 2026-10-14 below). */
const USAGE = {
  day: '2026-10-13',
  storage: { used_bytes: 128_849_019, limit_bytes: 1_073_741_824, percent: 12 },
  active_users: { on_day: 3, last_30_days: 4 },
  stale: false,
};

beforeEach(() => {
  // Only the date: the timers stay real (the component awaits the plans).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 14, 10, 0));
});

afterEach(() => {
  vi.useRealTimers();
  applySurface('web');
  document.body.innerHTML = '';
});

async function setup(business: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountHubs(BusinessSummary, {
    props: { business: { ...BUSINESS, ...business } },
    locale,
    api: (call) => (describeCall(call).path === '/api/plans' ? Response.json(PLANS) : Response.json({})),
  });
  await flush();
  const card = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const kv = (id: string) => Object.fromEntries(card(id).findAll('.kv > div').map((d) => [d.get('dt').text(), d.get('dd').text()]));
  return { ...m, card, kv };
}

describe('BusinessSummary', () => {
  it('the plan: its name and what it covers (devices from the plans on sale, people from the business)', async () => {
    const s = await setup();
    expect(s.calls().map((c) => c.path)).toEqual(['/api/plans']);
    expect(s.card('summary-plan').get('.card-title').text()).toBe('Free');
    expect(s.kv('summary-plan')).toEqual({ Devices: '1', Users: '2 of 3' });
  });

  it('says when the account pays for the business («You pay»), and nothing otherwise', async () => {
    const payer = await setup({ is_payer: true });
    expect(payer.card('summary-plan').get('[data-testid="summary-payer"]').text()).toBe('You pay');
    document.body.innerHTML = '';
    const other = await setup({ is_payer: false });
    expect(other.card('summary-plan').find('[data-testid="summary-payer"]').exists()).toBe(false);
  });

  it('a paid plan or a trial covers everyone: unlimited, and the trial says until when', async () => {
    const s = await setup({ trial_plan: { slug: 'starter', name: 'Starter' }, trial_end: '2026-10-30T10:00:00Z', seats: { used: 2, limit: null } });
    expect(s.kv('summary-plan')).toEqual({ Devices: 'Unlimited', Users: 'Unlimited' });
    expect(s.card('summary-plan').get('[data-testid="summary-trial"]').text()).toMatch(/^Trying Starter until Oct 30, 2026/);
  });

  it('inside the app, says where the plan is changed, without a link', async () => {
    applySurface('desktop');
    const s = await setup();
    expect(s.card('summary-plan').text()).toContain('To change your plan or add modules, go to erplora.com in your browser.');
    expect(s.card('summary-plan').find('a').exists()).toBe(false);
  });

  it('before the first night, the usage says there is no data yet', async () => {
    const s = await setup();
    const usage = s.card('summary-usage');
    expect(usage.get('.card-title').text()).toBe('How your business is doing in ERPlora');
    expect(usage.get('[data-testid="summary-usage-empty"]').text()).toBe(
      'No data yet. The figures arrive every night, from the first one after the business is created.',
    );
    expect(usage.findComponent(UsageMeter).exists()).toBe(false);
    expect(usage.findAllComponents(UsageCounter)).toHaveLength(0);
  });

  it("the storage against the plan and the people active, from yesterday's measure", async () => {
    const s = await setup({ usage: USAGE });
    const usage = s.card('summary-usage');
    expect(usage.getComponent(UsageMeter).props()).toMatchObject({
      label: 'Storage',
      percent: 12,
      hint: 'Of the space included in your plan: photos, documents and copies.',
    });
    // A percentage, never the bytes (PLAN-SAAS §5).
    expect(usage.getComponent(UsageMeter).props('value')).toBeUndefined();
    expect(usage.findAllComponents(UsageCounter).map((c: { props: (k: string) => unknown }) => [c.props('label'), c.props('value')])).toEqual([
      ['Active yesterday', 3],
      ['Last 30 days', 4],
    ]);
    expect(usage.get('[data-testid="summary-usage-day"]').text()).toBe("Yesterday's data: updated every night.");
    expect(usage.find('[data-testid="summary-usage-empty"]').exists()).toBe(false);
  });

  it('the people stay a line of the plan: the usage card is not about the places', async () => {
    const s = await setup({ usage: USAGE });
    expect(s.kv('summary-plan')).toMatchObject({ Users: '2 of 3' });
    expect(s.card('summary-usage').text()).not.toContain('Places on the plan');
  });

  it('close to the space of the plan, says it is running out; past it, that it is used up', async () => {
    const low = await setup({ usage: { ...USAGE, storage: { ...USAGE.storage, percent: 82 } } });
    expect(low.card('summary-usage').getComponent(UsageMeter).props('hint')).toBe('You are running out of space on the Free plan.');
    document.body.innerHTML = '';
    const full = await setup({
      trial_plan: { slug: 'starter', name: 'Starter' },
      trial_end: '2026-10-30T10:00:00Z',
      usage: { ...USAGE, storage: { ...USAGE.storage, percent: 104 } },
    });
    expect(full.card('summary-usage').getComponent(UsageMeter).props()).toMatchObject({
      percent: 104,
      hint: 'You have used all the space included in the Starter plan.',
    });
  });

  it('an older measure says its day, on the counter and below', async () => {
    const s = await setup({ usage: { ...USAGE, day: '2026-10-09', stale: true } });
    const usage = s.card('summary-usage');
    expect(usage.findAllComponents(UsageCounter).map((c: { props: (k: string) => unknown }) => c.props('label'))).toEqual([
      'Active on Oct 9',
      'Last 30 days',
    ]);
    expect(usage.get('[data-testid="summary-usage-day"]').text()).toBe('Data from Oct 9: updated every night.');
  });

  it('without a plan to measure against there is no bar, only the people', async () => {
    const s = await setup({ plan: null, usage: { ...USAGE, storage: { used_bytes: 10, limit_bytes: null, percent: null } } });
    expect(s.card('summary-usage').findComponent(UsageMeter).exists()).toBe(false);
    expect(s.card('summary-usage').findAllComponents(UsageCounter)).toHaveLength(2);
  });

  it('in Spanish, as the mockup says it', async () => {
    const s = await setup({ usage: USAGE }, 'es');
    const usage = s.card('summary-usage');
    expect(usage.get('.card-title').text()).toBe('Cómo va tu negocio en ERPlora');
    expect(usage.getComponent(UsageMeter).props('label')).toBe('Almacenamiento');
    expect(usage.findAllComponents(UsageCounter).map((c: { props: (k: string) => unknown }) => c.props('label'))).toEqual([
      'Activos ayer',
      'Últimos 30 días',
    ]);
    expect(usage.get('[data-testid="summary-usage-day"]').text()).toBe('Datos de ayer: se actualizan cada noche.');
    document.body.innerHTML = '';
    const older = await setup({ usage: { ...USAGE, day: '2026-10-09' } }, 'es');
    expect(older.card('summary-usage').get('[data-testid="summary-usage-day"]').text()).toBe('Datos del 9 oct: se actualizan cada noche.');
    document.body.innerHTML = '';
    const empty = await setup({}, 'es');
    expect(empty.card('summary-usage').get('[data-testid="summary-usage-empty"]').text()).toMatch(/^Sin datos todavía\./);
  });

  it('«On your devices» with the address, and the details', async () => {
    const s = await setup();
    expect(s.wrapper.getComponent(DeviceAccessCard).props('host')).toBe('bakery.erplora.com');
    expect(s.kv('summary-facts')).toMatchObject({ Type: 'Bakery and pastry', Country: 'Spain', Members: '2' });
    expect(s.kv('summary-facts').Created).toMatch(/^Mar 2, 2026/);
  });

  it('without a type, says it is not set; in Spanish, the country too', async () => {
    const s = await setup({ business_type: null }, 'es');
    expect(s.kv('summary-facts')).toMatchObject({ Tipo: 'Sin indicar', País: 'España' });
  });

  it('deleted: the plan was cancelled, no usage nor devices', async () => {
    const s = await setup({ status: 'deleting', purge_after: '2027-01-11T10:00:00Z' });
    expect(s.card('summary-plan').text()).toContain('It was cancelled when the business was deleted. If you recover it, it comes back on Free.');
    expect(s.card('summary-usage').exists()).toBe(false);
    expect(s.wrapper.findComponent(DeviceAccessCard).exists()).toBe(false);
    expect(s.card('summary-facts').exists()).toBe(true);
  });
});
