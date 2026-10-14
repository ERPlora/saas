// A business's page (`/businesses/:id/:tab`, round 17 §2.3; mockups `business.html`): the live
// `hubs.business.get`, a header with its name, address, status, plan and role and «Open», and four
// sections in the footer tabbar — Summary · Members · Modules · Settings — each at its own address.
// Deleted, a banner says until when it can be recovered; a payment pending or a suspension is said too.
import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { BYE, describeCall, errorFrame, flush, ionProps, mountHubs, subId } from '../__tests__/mount-hubs';
import BusinessSettings from '../components/BusinessSettings.vue';
import BusinessSummary from '../components/BusinessSummary.vue';
import DangerZone from '../components/DangerZone.vue';
import MembersTab from '../components/MembersTab.vue';
import BusinessPage from './BusinessPage.vue';
import { navigation } from '../open-business';

const BUSINESS = {
  id: 'h1',
  slug: 'bakery',
  name: 'Panadería López',
  host: 'bakery.erplora.com',
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
  plan: { slug: 'starter', name: 'Starter' },
  trial_plan: null,
  trial_end: null,
  seats: { used: 4, limit: null },
  pending_transfer: null,
  can: { open: true, manage_members: true, manage_settings: true, manage_billing: true, transfer: true, delete: true },
};

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(tab = 'summary', business: Record<string, unknown> | null = {}, locale: 'en' | 'es' = 'en') {
  vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(BusinessPage, {
    path: `/businesses/h1/${tab}`,
    props: { id: 'h1', tab },
    locale,
    api: (call) => {
      const c = describeCall(call);
      if (c.path === '/api/hubs/businesses/open') return Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/' });
      if (c.path === '/api/hubs/businesses/restore') return Response.json({ ...BUSINESS, status: 'active' });
      if (c.path === '/api/plans') return Response.json({ signup_trial_days: 0, cheapest_slug: null, plans: [] });
      return Response.json({});
    },
  });
  const call = await m.live();
  if (business) await m.result(call, 'hubs.business.get', { ...BUSINESS, ...business });
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, call, testid, page: () => m.wrapper.getComponent(AppPage) };
}

describe('BusinessPage: the frame', () => {
  it('follows hubs.business.get of the business, titled by its name, back to Businesses', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('hubs.business.get').map((sub) => sub.params)).toEqual([{ id: 'h1' }]);
    expect(s.page().props()).toMatchObject({ title: 'Panadería López', backHref: '/businesses', tabsLabel: 'Business sections' });
  });

  it('has the four sections in the footer tabbar, each at its address, with its icon', async () => {
    const s = await setup();
    expect(s.page().props('tabs')).toEqual([
      { id: 'summary', label: 'Summary', icon: 'ion:grid-outline', to: '/businesses/h1/summary' },
      { id: 'members', label: 'Members', icon: 'ion:people-outline', to: '/businesses/h1/members' },
      { id: 'modules', label: 'Modules', icon: 'ion:apps-outline', to: '/businesses/h1/modules' },
      { id: 'settings', label: 'Settings', icon: 'ion:settings-outline', to: '/businesses/h1/settings' },
    ]);
  });

  it('the header: name, address, status, plan and role, and «Open» (solid on the Summary)', async () => {
    const s = await setup();
    const header = s.testid('business-header');
    expect(header.get('.biz-header__title').text()).toBe('Panadería López');
    expect(header.get('.biz-header__url').text()).toBe('bakery.erplora.com');
    expect(header.get('.status-pill').text()).toBe('Active');
    expect(header.get('.biz-header__meta').text()).toBe('Plan Starter · Owner');
    const open = s.testid('business-open');
    expect(ionProps(open, 'fill')).toEqual({ fill: 'solid' });
    await open.trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'h1', next: '/' });
  });

  it('a suspended business has no «Open», and says why, with the way to pay', async () => {
    const s = await setup('summary', {
      status: 'suspended',
      can: { ...BUSINESS.can, open: false },
      unpaid_reason: 'card_declined',
      unpaid_since: '2026-10-01T10:00:00Z',
      pay_url: 'https://invoice.stripe.com/i/abc',
    });
    expect(s.testid('business-open').exists()).toBe(false);
    expect(s.testid('business-state').exists()).toBe(false);
    const unpaid = s.testid('business-unpaid');
    expect(unpaid.text()).toContain('Panadería López is suspended');
    expect(unpaid.get('[data-testid="unpaid-card"]').text()).toBe('The bank declined the card: change it before paying.');
  });

  it('a payment pending is said with the way to pay; the business still opens', async () => {
    const s = await setup('summary', { status: 'past_due', unpaid_reason: 'payment_failed', unpaid_since: '2026-10-10T10:00:00Z', pay_url: 'https://invoice.stripe.com/i/abc' });
    expect(s.testid('business-unpaid').find('[data-testid="unpaid-pay"]').exists()).toBe(true);
    expect(s.testid('business-open').exists()).toBe(true);
  });

  it('being prepared, it says it will be ready soon (this page opens nothing by itself)', async () => {
    const s = await setup('summary', { status: 'preparing', can: { ...BUSINESS.can, open: false } });
    expect(s.testid('business-state').text()).toBe('Ready in a few seconds');
  });

  it('a failed recovery is said in the person’s language', async () => {
    const s = await setup('summary', {
      status: 'deleting',
      deletion_requested_at: '2026-10-13T10:00:00Z',
      purge_after: '2027-01-11T10:00:00Z',
      can: { ...BUSINESS.can, open: false, delete: false, restore: true },
    }, 'es');
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    await s.testid('business-restore').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.');
  });

  it('loading: a skeleton; an error: why, and «Retry»', async () => {
    const s = await setup('summary', null);
    expect(s.testid('business-loading').exists()).toBe(true);
    s.call.push(errorFrame(subId(s.client, 'hubs.business.get'), 'not_found'));
    await flush();
    expect(s.testid('business-error').text()).toContain('We could not load this business');
    expect(s.testid('business-error').text()).toContain('Maybe you no longer have access to it, or there is a connection problem.');
    expect(s.testid('business-retry').exists()).toBe(true);
  });

  it('the stream gone before any answer: an error with «Retry» after the time limit, never a skeleton for ever (R-08)', async () => {
    const s = await setup('summary', null);
    s.call.push(BYE);
    await flush();
    expect(s.testid('business-loading').exists()).toBe(true);
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.testid('business-loading').exists()).toBe(false);
    expect(s.testid('business-error').text()).toContain('We could not load this business');
    const streams = s.net.streams.length;
    await s.testid('business-retry').trigger('click');
    await s.clock.advance(1);
    expect(s.net.streams.length).toBeGreaterThan(streams);
    expect(s.testid('business-loading').exists()).toBe(true);
  });

  it('an error has no tabbar: its sections would only repeat it (W-18 of the mockups)', async () => {
    const s = await setup('members', null);
    expect(s.page().props('tabs')).toHaveLength(4);
    s.call.push(errorFrame(subId(s.client, 'hubs.business.get'), 'not_found'));
    await flush();
    expect(s.page().props('tabs')).toEqual([]);
  });
});

describe('BusinessPage: the sections', () => {
  it('Summary', async () => {
    const s = await setup('summary');
    expect(s.wrapper.getComponent(BusinessSummary).props('business')).toMatchObject({ id: 'h1' });
  });

  it('Members, with «Open» outlined', async () => {
    const s = await setup('members');
    expect(s.wrapper.getComponent(MembersTab).props('business')).toMatchObject({ id: 'h1', name: 'Panadería López' });
    expect(ionProps(s.testid('business-open'), 'fill')).toEqual({ fill: 'outline' });
  });

  it('Modules: apps are turned on inside the business; the header’s «Open», solid, is its one action', async () => {
    const s = await setup('modules');
    expect(s.testid('business-modules').text()).toContain('Apps are turned on and off inside the business');
    // One «Open» per screen (Ioan, 2026-10-14): the card no longer repeats the header's.
    expect(s.wrapper.findAll('[data-testid="business-modules-open"]')).toHaveLength(0);
    expect(ionProps(s.testid('business-open'), 'fill')).toEqual({ fill: 'solid' });
    await s.testid('business-open').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'h1', next: '/' });
  });

  it('Members fills the page between the topbar and the tabbar; the other sections read as a page', async () => {
    for (const [tab, layout, fill] of [
      ['members', 'detail-fill', true],
      ['summary', 'detail', false],
      ['modules', 'detail', false],
      ['settings', 'detail', false],
    ] as const) {
      const s = await setup(tab);
      expect(s.page().props('contentLayout'), tab).toBe(layout);
      expect(s.testid('business-header').element.parentElement?.classList.contains('panel-fill'), tab).toBe(fill);
      s.wrapper.unmount();
      document.body.innerHTML = '';
    }
  });

  it('Modules inside the app says where to add modules, without a link', async () => {
    applySurface('desktop');
    const s = await setup('modules');
    expect(s.testid('business-modules').text()).toContain('To change your plan or add modules, go to erplora.com in your browser.');
  });

  it('Settings: the general settings and the danger zone', async () => {
    const s = await setup('settings');
    expect(s.wrapper.getComponent(BusinessSettings).props('business')).toMatchObject({ id: 'h1' });
    expect(s.wrapper.getComponent(DangerZone).props('business')).toMatchObject({ id: 'h1' });
  });
});

describe('BusinessPage: deleted', () => {
  const DELETED = { status: 'deleting', deletion_requested_at: '2026-10-13T10:00:00Z', purge_after: '2027-01-11T10:00:00Z', can: { ...BUSINESS.can, open: false, delete: false, restore: true } };

  it('says until when it can be recovered and the owner recovers it', async () => {
    const s = await setup('summary', DELETED);
    const banner = s.testid('business-deleted');
    expect(banner.text()).toMatch(/It will be erased for good on Jan 11, 2027/);
    expect(s.testid('business-open').exists()).toBe(false);
    await s.testid('business-restore').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/restore')?.body).toEqual({ id: 'h1' });
    expect(toastSuccess).toHaveBeenCalledWith('Business recovered: Panadería López');
  });

  it('has no tabbar and shows its Summary whatever the address (W-B3 of the mockups)', async () => {
    const s = await setup('members', DELETED);
    expect(s.page().props('tabs')).toEqual([]);
    expect(s.wrapper.findComponent(MembersTab).exists()).toBe(false);
    expect(s.wrapper.findComponent(BusinessSummary).exists()).toBe(true);
  });

  it('an admin only reads that the owner can recover it', async () => {
    const s = await setup('summary', { ...DELETED, role: 'hub_admin', role_label: 'Admin', can: { ...DELETED.can, restore: false } });
    expect(s.testid('business-deleted').text()).toContain('Only its owner can recover it.');
    expect(s.testid('business-restore').exists()).toBe(false);
  });
});

describe('BusinessPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup('summary', {}, 'es');
    expect((s.page().props('tabs') as Array<{ label: string }>).map((tab) => tab.label)).toEqual(['Resumen', 'Miembros', 'Módulos', 'Ajustes']);
    expect(s.testid('business-open').text()).toContain('Abrir');
  });
});
