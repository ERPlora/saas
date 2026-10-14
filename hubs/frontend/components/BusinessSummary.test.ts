// The Summary of a business (mockups `business.html` «summary», PLAN-SAAS §3.6): its plan (what it
// covers, the trial; changing it is the Store's, web only), the people on it against what the plan
// covers, «On your devices» and its details. Deleted, only the plan (cancelled) and the details.
import { UsageCounter, UsageMeter } from '@erplora/ui/components';
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

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
};

afterEach(() => {
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

  it('the people on the business against the places of its plan', async () => {
    const s = await setup();
    const meter = s.card('summary-usage').getComponent(UsageMeter);
    expect(meter.props()).toMatchObject({ label: 'Places on the plan', value: 2, max: 3 });
    expect(s.card('summary-usage').findAllComponents(UsageCounter).map((c: { props: (k: string) => unknown }) => [c.props('label'), c.props('value')])).toEqual([
      ['People', 2],
      ['The plan covers', 3],
    ]);
  });

  it('with unlimited places there is no bar, only the figures', async () => {
    const s = await setup({ seats: { used: 4, limit: null } });
    expect(s.card('summary-usage').findComponent(UsageMeter).exists()).toBe(false);
    expect(s.card('summary-usage').findAllComponents(UsageCounter).map((c: { props: (k: string) => unknown }) => c.props('value'))).toEqual([4, 'Unlimited']);
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
