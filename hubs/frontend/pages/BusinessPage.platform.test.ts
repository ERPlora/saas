// The page of ERPlora's own business (`is_platform`): its Summary and its Members. It has no plan, its apps are not
// chosen here and nobody changes its settings, so those sections are not offered, and an address to one shows the
// Summary.
import { applySurface } from '@erplora/ui/shell';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { describeCall, mountHubs } from '../__tests__/mount-hubs';
import BusinessSettings from '../components/BusinessSettings.vue';
import BusinessSummary from '../components/BusinessSummary.vue';
import CustomDomainCard from '../components/CustomDomainCard.vue';
import DangerZone from '../components/DangerZone.vue';
import MembersTab from '../components/MembersTab.vue';
import BusinessPage from './BusinessPage.vue';

const OWN = {
  id: 'p1',
  slug: 'erp',
  name: 'ERPlora',
  host: 'erp.erplora.com',
  is_platform: true,
  country: 'ES',
  timezone: 'Europe/Madrid',
  language: 'es',
  business_type: null,
  status: 'active',
  status_label: 'Active',
  hub_error: null,
  ready_at: '2026-03-02T10:00:00Z',
  created_at: '2026-03-02T10:00:00Z',
  deletion_requested_at: null,
  purge_after: null,
  role: 'hub_owner',
  role_label: 'Owner',
  plan: null,
  trial_plan: null,
  trial_end: null,
  seats: { used: 1, limit: null },
  pending_transfer: null,
  can: {
    open: true,
    manage: true,
    manage_members: true,
    manage_settings: false,
    manage_billing: false,
    transfer: true,
    restore: false,
    delete: false,
    change_address: false,
    download_data: true,
  },
  usage: null,
};

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

async function setup(tab: string, business: Record<string, unknown> = {}) {
  const m = await mountHubs(BusinessPage, {
    path: `/dashboard/businesses/p1/${tab}`,
    props: { id: 'p1', tab },
    api: (call) =>
      describeCall(call).path === '/api/hubs/data-copies'
        ? Response.json({ business_id: 'p1', available: true, copies: [] })
        : Response.json({}),
  });
  await m.result(await m.live(), 'hubs.business.get', { ...OWN, ...business });
  return { ...m, tabs: () => (m.wrapper.getComponent(AppPage).props('tabs') as Array<{ id: string }>).map((entry) => entry.id) };
}

describe('BusinessPage: ERPlora’s own business', () => {
  it('offers its Summary and its Members alone', async () => {
    expect((await setup('summary')).tabs()).toEqual(['summary', 'members']);
  });

  it('any other business keeps its four sections', async () => {
    const s = await setup('summary', { is_platform: false });
    expect(s.tabs()).toEqual(['summary', 'members', 'modules', 'settings']);
  });

  it.each(['modules', 'settings'])('the address of its %s shows the Summary, with nothing to change', async (tab) => {
    const s = await setup(tab);
    expect(s.wrapper.findComponent(BusinessSummary).exists()).toBe(true);
    for (const absent of [BusinessSettings, DangerZone]) expect(s.wrapper.findComponent(absent).exists()).toBe(false);
    expect(s.wrapper.find('[data-testid="business-modules"]').exists()).toBe(false);
  });

  it('the address of its Members shows its people', async () => {
    const s = await setup('members');
    expect(s.wrapper.findComponent(MembersTab).isVisible()).toBe(true);
  });

  it('never shows a domain of its own', async () => {
    const s = await setup('settings');
    expect(s.wrapper.findComponent(CustomDomainCard).exists()).toBe(false);
  });

  it('says its role without a plan, and opens', async () => {
    const s = await setup('summary');
    expect(s.wrapper.get('[data-testid="business-header"] .biz-header__meta').text()).toBe('Owner');
    expect(s.wrapper.find('[data-testid="business-open"]').exists()).toBe(true);
  });
});
