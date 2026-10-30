// A business's page (`/dashboard/businesses/:id/:tab`, round 17 §2.3; mockups `business.html`): the live
// `hubs.business.get`, a header with its name, address, status, plan and role and «Open», and four
// sections in the footer tabbar — Summary · Members · Modules · Settings — each at its own address.
// Deleted, a banner says until when it can be recovered; a payment pending or a suspension is said too.
import { RELEASE_GRACE_MS } from '@erplora/ui/sdk';
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
import RepresentationCard from '../../../fiscal/frontend/components/RepresentationCard.vue';
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

/** A copy the Hub keeps of the business's data (`hubs.data_copy.list`). */
const COPY = { id: 'h1hex/20261013T100500Z-offboarding.dump', kind: 'offboarding', created_at: '2026-10-13T10:05:00Z', bytes: 2048 };

async function setup(tab = 'summary', business: Record<string, unknown> | null = {}, locale: 'en' | 'es' = 'en') {
  vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(BusinessPage, {
    path: `/dashboard/businesses/h1/${tab}`,
    props: { id: 'h1', tab },
    locale,
    api: (call) => {
      const c = describeCall(call);
      if (c.path === '/api/hubs/businesses/open') return Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/' });
      if (c.path === '/api/hubs/businesses/restore') return Response.json({ ...BUSINESS, status: 'active' });
      if (c.path === '/api/plans') return Response.json({ signup_trial_days: 0, cheapest_slug: null, plans: [] });
      if (c.path === '/api/hubs/data-copies') return Response.json({ business_id: 'h1', copies: [COPY] });
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
    expect(s.page().props()).toMatchObject({ title: 'Panadería López', backHref: '/dashboard/businesses', tabsLabel: 'Business sections' });
  });

  it('has the four sections in the footer tabbar, each at its address, with its icon', async () => {
    const s = await setup();
    expect(s.page().props('tabs')).toEqual([
      { id: 'summary', label: 'Summary', icon: 'ion:grid-outline', to: '/dashboard/businesses/h1/summary' },
      { id: 'members', label: 'Members', icon: 'ion:people-outline', to: '/dashboard/businesses/h1/members' },
      { id: 'modules', label: 'Modules', icon: 'ion:apps-outline', to: '/dashboard/businesses/h1/modules' },
      { id: 'settings', label: 'Settings', icon: 'ion:settings-outline', to: '/dashboard/businesses/h1/settings' },
    ]);
  });

  it('the header: name, address, status, plan and role, and «Open» (solid on the Summary)', async () => {
    const s = await setup();
    const header = s.testid('business-header');
    expect(header.get('.biz-header__title').text()).toBe('Panadería López');
    expect(header.get('.biz-header__url').text()).toBe('bakery.erplora.com');
    expect(header.find('.biz-header__url .host-name').exists()).toBe(true);
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

  it('a role that may not manage it (a manager’s deep link): no permission, not a connection problem (audit 2 R-19)', async () => {
    const s = await setup('members', null);
    s.call.push(errorFrame(subId(s.client, 'hubs.business.get'), 'permission_denied'));
    await flush();
    expect(s.testid('business-error').text()).toContain('You do not have permission to manage this business');
    expect(s.testid('business-error').text()).toContain('Your role does not allow it. If you need it, ask the owner.');
    expect(s.testid('business-error').text()).not.toContain('connection');
    expect(s.testid('business-retry').exists()).toBe(false);
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
    // Only Members: no other section under it.
    expect(s.wrapper.findComponent(BusinessSummary).exists()).toBe(false);
    expect(s.wrapper.findComponent(BusinessSettings).exists()).toBe(false);
    expect(s.wrapper.findComponent(DangerZone).exists()).toBe(false);
    expect(s.testid('business-modules').exists()).toBe(false);
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

describe('BusinessPage: the authorisation for ERPlora to file its invoices (fiscal)', () => {
  const OP = 'fiscal.representation.status';
  const NONE = {
    status: 'none',
    version: null,
    submitted_at: null,
    reviewed_at: null,
    changed_at: null,
    reason: '',
    taxpayer_tax_id: '',
    taxpayer_name: '',
    signer_name: '',
    documents: { signed_model: false, id_copy: false, signature_sample: false, representation_proof: false },
    history: [],
  };

  it('the Summary of a Spanish business shows it under its cards, for that business', async () => {
    const s = await setup('summary');
    const card = s.wrapper.getComponent(RepresentationCard);
    expect(card.props()).toMatchObject({ id: 'h1', canManage: true, managing: false });
    expect(s.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{ id: 'h1' }]);
    const summary = s.wrapper.getComponent(BusinessSummary).element;
    expect(summary.compareDocumentPosition(card.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('only on the Summary', async () => {
    for (const tab of ['members', 'modules', 'settings']) {
      const s = await setup(tab);
      expect(s.wrapper.findComponent(RepresentationCard).exists(), tab).toBe(false);
      s.wrapper.unmount();
      document.body.innerHTML = '';
    }
  });

  /** The card is on screen (it is asked for with the page, so it may be there and hidden). */
  const cardShown = (s: Awaited<ReturnType<typeof setup>>) => s.testid('representation').exists() && s.testid('representation').isVisible();

  it('only for a business in Spain: the AEAT is Spanish', async () => {
    const s = await setup('summary', { country: 'PT', timezone: 'Europe/Lisbon' });
    expect(cardShown(s)).toBe(false);
  });

  it('not once the business is deleted: its Summary keeps only the plan and the details', async () => {
    const s = await setup('summary', { status: 'deleting', deletion_requested_at: '2026-10-13T10:00:00Z', purge_after: '2027-01-11T10:00:00Z', can: { ...BUSINESS.can, open: false } });
    expect(cardShown(s)).toBe(false);
  });

  it('«Manage in your business» opens the business, as «Open» does', async () => {
    const s = await setup('summary');
    await s.result(s.call, OP, NONE);
    await s.testid('representation-manage').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'h1', next: '/' });
    expect(navigation.assign).toHaveBeenCalledWith('http://bakery.localhost:8000/auth/login?next=/');
  });

  it('suspended or not to be opened: the card stays, without «Manage in your business»', async () => {
    for (const business of [{ status: 'suspended', status_label: 'Suspended' }, { can: { ...BUSINESS.can, open: false } }]) {
      const s = await setup('summary', business);
      expect(s.wrapper.getComponent(RepresentationCard).props('canManage')).toBe(false);
      s.wrapper.unmount();
      document.body.innerHTML = '';
    }
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

  it('its owner downloads the copy of its data from its Summary, where the deletion mail leads (HUBS-F18)', async () => {
    const s = await setup('summary', { ...DELETED, can: { ...DELETED.can, download_data: true } });
    await flush();
    expect(s.testid('data-copy-card').text()).toContain('Download the data');
    expect(s.wrapper.findAll('[data-testid="data-copy-row"]')).toHaveLength(1);
  });

  it('nobody else is offered the copy of its data', async () => {
    const s = await setup('summary', { ...DELETED, role: 'hub_admin', role_label: 'Admin', can: { ...DELETED.can, restore: false, download_data: false } });
    await flush();
    expect(s.testid('data-copy-card').exists()).toBe(false);
    expect(s.calls().some((c) => c.path === '/api/hubs/data-copies')).toBe(false);
  });
});

// FIX-SAAS-BUSINESSES-LIVE-DOUBLE-OPEN: a section that only needs the business's id (the route has it) asks for
// its data with the page, so the page's stream opens once; waiting for `hubs.business.get` to mount it made
// the SDK reopen the stream and the first `GET /api/live` ended aborted.
describe('BusinessPage: one stream', () => {
  it('Members asks for its list in the first stream, with the business, and the business’s answer does not reopen it', async () => {
    const s = await setup('members', null);
    expect(s.testid('business-loading').exists()).toBe(true);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.subs.map((sub) => [sub.op, sub.params])).toEqual(
      expect.arrayContaining([
        ['hubs.business.get', { id: 'h1' }],
        ['hubs.member.list', { hub_id: 'h1', limit: 50, offset: 0 }],
      ]),
    );
    await s.result(s.call, 'hubs.business.get', BUSINESS);
    await s.clock.advance(1000);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.aborted()).toBe(false);
    expect(s.wrapper.getComponent(MembersTab).props()).toMatchObject({ id: 'h1', business: { id: 'h1', name: 'Panadería López' } });
  });

  it('the Summary asks for the authorisation in the first stream, with the business, and the business’s answer does not reopen it', async () => {
    const s = await setup('summary', null);
    expect(s.testid('business-loading').exists()).toBe(true);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.subs.map((sub) => [sub.op, sub.params])).toEqual(
      expect.arrayContaining([
        ['hubs.business.get', { id: 'h1' }],
        ['fiscal.representation.status', { id: 'h1' }],
      ]),
    );
    await s.result(s.call, 'hubs.business.get', BUSINESS);
    await s.clock.advance(1000);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.aborted()).toBe(false);
    expect(s.testid('representation').isVisible()).toBe(true);
  });

  it('a business outside Spain keeps the stream it opened: the authorisation it asked for stays hidden, without a reopen', async () => {
    const s = await setup('summary', null);
    await s.result(s.call, 'hubs.business.get', { ...BUSINESS, country: 'PT', timezone: 'Europe/Lisbon' });
    await s.clock.advance(RELEASE_GRACE_MS + 1000);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.aborted()).toBe(false);
    expect(s.testid('representation').isVisible()).toBe(false);
  });

  it('Members goes with the business’s error: the page says it once, without a list', async () => {
    const s = await setup('members', null);
    s.call.push(errorFrame(subId(s.client, 'hubs.business.get'), 'permission_denied'));
    await flush();
    expect(s.testid('business-error').exists()).toBe(true);
    expect(s.wrapper.findComponent(MembersTab).exists()).toBe(false);
  });

  it('while the business loads, the page’s skeleton is the only thing on screen: Members waits for it to show its list', async () => {
    const s = await setup('members', null);
    expect(s.testid('business-loading').exists()).toBe(true);
    expect(s.wrapper.getComponent(MembersTab).props('business')).toBeUndefined();
    await s.result(s.call, 'hubs.member.list', { rows: [], total: 0, limit: 50, offset: 0, seats: { used: 1, limit: null }, invitable_roles: [] });
    expect(s.wrapper.find('.members-stack').exists()).toBe(false);
    expect(s.wrapper.find('[data-testid^="members"]').exists()).toBe(false);
  });

  it('a deleted business shows its Summary on the Members address: the list it asked for goes away', async () => {
    const s = await setup('members', {
      status: 'deleting',
      deletion_requested_at: '2026-10-13T10:00:00Z',
      purge_after: '2027-01-11T10:00:00Z',
      can: { ...BUSINESS.can, open: false, delete: false, restore: true },
    });
    expect(s.wrapper.findComponent(MembersTab).exists()).toBe(false);
    // Past the SDK's grace before it lets an unmounted query go, and its resubscribe debounce.
    await s.clock.advance(RELEASE_GRACE_MS + 1000);
    expect(s.client.stream.subscriptions('hubs.member.list')).toEqual([]);
  });
});

describe('BusinessPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup('summary', {}, 'es');
    expect((s.page().props('tabs') as Array<{ label: string }>).map((tab) => tab.label)).toEqual(['Resumen', 'Miembros', 'Módulos', 'Ajustes']);
    expect(s.testid('business-open').text()).toContain('Abrir');
  });
});
