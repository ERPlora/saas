// Businesses (`/businesses`, round 17 §2.3; mockups `businesses.html`, README §3b): the account's
// businesses in a server-side DataTable (list or cards; cards up to 900 px), with their status, plan,
// role and last use; per row «Open», «Manage», «Recover», «Delete» by what the role allows; above it
// the pending invitations and ownership offers and the unpaid invoices; «Create business» opens the
// dialog (form → preparing → ready) and the new row appears «Preparing» through the live list; empty,
// the sign-up form itself.
import { DataTable } from '@erplora/ui/components';
import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

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

import { accessibleName, describeCall, enterView, errorFrame, flush, type MountOptions, mountHubs, subId } from '../__tests__/mount-hubs';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import BusinessListPage from './BusinessListPage.vue';
import { navigation } from '../open-business';

/** What the server says the row's buttons do (`can`), from its role and status, as queries.can does. */
function canOf(extra: Record<string, unknown>) {
  const role = (extra.role as string) ?? 'hub_owner';
  const status = (extra.status as string) ?? 'active';
  const writable = status !== 'deleting';
  const manages = (role === 'hub_owner' || role === 'hub_admin') && writable;
  return {
    open: !['preparing', 'suspended', 'deleting'].includes(status),
    manage: manages,
    restore: role === 'hub_owner' && status === 'deleting',
    delete: role === 'hub_owner' && writable,
  };
}

const row = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  slug: id,
  name,
  host: `${id}.localhost:8000`,
  status: 'active',
  status_label: 'Active',
  plan: { slug: 'starter', name: 'Starter' },
  role: 'hub_owner',
  role_label: 'Owner',
  last_opened_at: null,
  can_open: true,
  open_blocked_reason: null,
  hub_error: null,
  deletion_requested_at: null,
  purge_after: null,
  created_at: '2026-03-02T10:00:00Z',
  can: canOf(extra),
  ...extra,
});
const PREPARING = { status: 'preparing', status_label: 'Preparing', can_open: false, open_blocked_reason: 'preparing' };
const ROWS = [
  row('bakery', 'Panadería López', { last_opened_at: '2026-10-13T09:12:00Z' }),
  row('cafe', 'Café Central', { ...PREPARING, plan: { slug: 'free', name: 'Free' } }),
  row('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', plan: { slug: 'free', name: 'Free' } }),
  row('plaza', 'Bar La Plaza', { status: 'past_due', status_label: 'Payment pending' }),
];
const page = (rows: unknown[], extra: Record<string, unknown> = {}) => ({
  rows,
  total: rows.length,
  limit: 50,
  offset: 0,
  invitations: [],
  ownership_offers: [],
  ...extra,
});
const INVITATION = {
  id: 'm1',
  hub: { id: 'norte', slug: 'norte', name: 'Bar Norte' },
  role: 'hub_employee',
  role_label: 'Employee',
  invited_by: 'Pedro Sanz',
  invited_at: null,
  expires_at: null,
  message: '',
};
const OFFER = { id: 't1', hub: { id: 'mar', slug: 'mar', name: 'Bar del Mar' }, from_email: 'pedro@example.com', expires_at: '2026-10-20T10:00:00Z' };

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(options: MountOptions & { respond?: (c: ReturnType<typeof describeCall>) => Response | undefined } = {}) {
  vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(BusinessListPage, {
    path: '/businesses',
    api: (call) => {
      const c = describeCall(call);
      const answer = options.respond?.(c);
      if (answer) return answer;
      if (c.path === '/api/hubs/businesses/open') return Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/' });
      if (c.path === '/api/catalog/business-types') return Response.json({ business_types: [] });
      return Response.json({});
    },
    ...options,
  });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="businesses-row"]');
  const params = () => m.client.stream.subscriptions('hubs.business.list').map((sub) => sub.params);
  const show = (result: unknown, rev?: number) => m.result(call, 'hubs.business.list', result, rev);
  return { ...m, call, testid, q, table, prop, rows, params, show };
}

describe('BusinessListPage: the list', () => {
  it('follows hubs.business.list, 50 from the first, in a server-side table with list and cards up to 900 px', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Businesses');
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    expect(s.testid('businesses-loading').exists()).toBe(true);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({
      serverSide: true,
      searchable: true,
      views: ['table', 'cards'],
      cardBreakpoint: 900,
      total: 4,
      testid: 'businesses',
      addable: true,
    });
    expect(s.prop<Record<string, string>>('labels')).toMatchObject({ add: 'Create business' });
    expect(s.prop('entityLabel')).toEqual({ one: 'business', many: 'businesses' });
    expect(s.testid('businesses-lead').text()).toBe('Here you manage your businesses. Press «Open» to work in one.');
  });

  it('gives the table its row actions to fold (README §3b, W-19): «Open» pinned, «Manage» and «Recover» inline', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<Record<string, unknown>>>('actions').map((a) => [a.id, a.icon, !!a.pinned, !!a.menuOnly])).toEqual([
      ['open', 'ion:log-in-outline', true, false],
      ['manage', 'ion:settings-outline', false, false],
      ['restore', 'ion:refresh-outline', false, false],
    ]);
    // What the box gives up first when it narrows: the web address and the last use; never the status.
    expect(s.prop<Array<{ key: string; priority?: string }>>('columns').map((c) => [c.key, c.priority ?? 'normal'])).toEqual([
      ['name', 'high'],
      ['host', 'low'],
      ['status', 'high'],
      ['plan', 'normal'],
      ['role', 'normal'],
      ['last_opened_at', 'low'],
    ]);
    // No hand-made buttons: the slot never folds.
    expect(s.wrapper.find('.row-action').exists()).toBe(false);
  });

  it('paints business, web address, status, plan, role and last use', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Business'],
      ['host', 'Web address'],
      ['status', 'Status'],
      ['plan', 'Plan'],
      ['role', 'Role'],
      ['last_opened_at', 'Last used'],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['bakery', 'cafe', 'salon', 'plaza']);
    const [bakery, cafe, salon, plaza] = s.rows();
    expect(bakery.get('.status-pill').text()).toBe('Active');
    expect(cafe.get('.status-pill').text()).toBe('Preparing');
    expect(cafe.get('[data-testid="business-status-why"]').text()).toBe('Ready in a few seconds');
    expect(plaza.get('.status-pill').text()).toBe('Payment due');
    expect(salon.get('[data-testid="business-role"]').text()).toContain('Manager');
    expect(salon.get('[data-testid="business-role"]').text()).toContain('Managed by the owner');
    expect(bakery.get('[data-testid="business-host"]').text()).toBe('bakery.localhost:8000');
  });

  it('a name opens the business’s page for whoever manages it, and the business for anybody else', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    await s.rows()[0].get('[data-testid="business-name"]').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/businesses/bakery/summary');
    await s.rows()[2].get('[data-testid="business-name"]').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'salon', next: '/' });
  });
});

describe('BusinessListPage: row actions', () => {
  const action = (s: Awaited<ReturnType<typeof setup>>, id: string, name: string) => s.testid(`businesses-row-${id}-${name}`);

  it('«Open» opens the business; being prepared it is disabled; suspended or deleted it is not there', async () => {
    const s = await setup();
    await s.show(
      page([
        ...ROWS,
        row('norte', 'Bar Norte', { status: 'suspended', can_open: false, open_blocked_reason: 'suspended' }),
        row('viejo', 'Bar Viejo', { status: 'deleting', can_open: false, open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' }),
      ]),
    );
    expect(accessibleName(action(s, 'bakery', 'open'))).toBe('Open Panadería López');
    expect((action(s, 'cafe', 'open').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    expect(action(s, 'norte', 'open').exists()).toBe(false);
    expect(action(s, 'viejo', 'open').exists()).toBe(false);
    await action(s, 'bakery', 'open').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'bakery', next: '/' });
  });

  it('the buttons are what the server says the row allows (`can`), never deduced from the role', async () => {
    const s = await setup();
    await s.show(
      page([
        row('bakery', 'Panadería López', { can: { open: true, manage: false, restore: false, delete: true } }),
        row('admin', 'Admin Bar', { role: 'hub_admin', role_label: 'Admin' }),
        row('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager' }),
      ]),
    );
    expect(action(s, 'bakery', 'manage').exists()).toBe(false);
    expect(action(s, 'admin', 'manage').exists()).toBe(true);
    expect(action(s, 'salon', 'manage').exists()).toBe(false);
    await action(s, 'admin', 'manage').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/businesses/admin/summary');
  });

  it('«Delete» is not on the row (README §3b): it lives in the business’s Settings, with its confirmation', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.find('[data-testid$="-delete"]').exists()).toBe(false);
  });

  it('every row button is named with its business for a screen reader', async () => {
    const s = await setup();
    await s.show(page([...ROWS, row('viejo', 'Bar Viejo', { status: 'deleting', can_open: false, open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' })]));
    expect(accessibleName(action(s, 'bakery', 'open'))).toBe('Open Panadería López');
    expect(accessibleName(action(s, 'bakery', 'manage'))).toBe('Manage Panadería López');
    expect(accessibleName(action(s, 'viejo', 'restore'))).toBe('Recover Bar Viejo');
  });

  it('a deleted business offers «Recover» to its owner, which recovers it and says so', async () => {
    const s = await setup({
      respond: (c) => (c.path === '/api/hubs/businesses/restore' ? Response.json({ id: 'viejo', name: 'Bar Viejo', status: 'active' }) : undefined),
    });
    await s.show(page([row('viejo', 'Bar Viejo', { status: 'deleting', can_open: false, open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' })]));
    expect(s.rows()[0].get('[data-testid="business-status-why"]').text()).toMatch(/^Deleted\. You can recover it until Jan 11, 2027/);
    expect(action(s, 'viejo', 'delete').exists()).toBe(false);
    await action(s, 'viejo', 'restore').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/restore')?.body).toEqual({ id: 'viejo' });
    expect(toastSuccess).toHaveBeenCalledWith('Business recovered: Bar Viejo');
  });
});

describe('BusinessListPage: what waits above the list', () => {
  it('an unpaid invoice is said above the list; inside the app, how to pay without a link', async () => {
    applySurface('desktop');
    const s = await setup();
    await s.show(page(ROWS));
    const unpaid = s.testid('businesses-unpaid-plaza');
    expect(unpaid.text()).toContain('Bar La Plaza has an unpaid invoice');
    expect(unpaid.text()).toContain('To pay it, go to erplora.com in your browser.');
    expect(unpaid.find('a').exists()).toBe(false);
  });

  it('a pending invitation: accept and enter, or decline with a confirmation', async () => {
    const s = await setup();
    await s.show(page(ROWS, { invitations: [INVITATION] }));
    const banner = s.testid('businesses-invitation-m1');
    expect(banner.text()).toContain('You have been invited to Bar Norte');
    expect(banner.text()).toContain('Pedro Sanz gives you access as Employee. Accept to see it in your list.');
    await banner.get('[data-testid="invitation-accept"]').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/invitations/accept')?.body).toEqual({ id: 'm1' });
    await banner.get('[data-testid="invitation-decline"]').trigger('click');
    await flush();
    expect(s.q('decline-dialog')).not.toBeNull();
  });

  it('an ownership offer: accept it or decline it', async () => {
    const s = await setup({
      respond: (c) =>
        c.path.startsWith('/api/hubs/ownership/') ? Response.json({ id: 't1', hub: OFFER.hub, status: 'accepted' }) : undefined,
    });
    await s.show(page(ROWS, { ownership_offers: [OFFER] }));
    const banner = s.testid('businesses-offer-t1');
    expect(banner.text()).toContain('pedro@example.com offers you Bar del Mar');
    await banner.get('[data-testid="offer-accept"]').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/ownership/accept')?.body).toEqual({ id: 't1' });
    expect(toastSuccess).toHaveBeenCalledWith('You are now the owner of Bar del Mar');
    await banner.get('[data-testid="offer-decline"]').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/ownership/decline')?.body).toEqual({ id: 't1' });
  });
});

describe('BusinessListPage: states', () => {
  it('empty: the sign-up form itself, and where an invitation would show', async () => {
    const s = await setup();
    await s.show(page([]));
    const empty = s.testid('businesses-empty');
    expect(empty.text()).toContain('Create your first business');
    expect(empty.text()).toContain('Free and no card: just the name and the country.');
    expect(empty.findComponent(BusinessCreateForm).exists()).toBe(true);
    expect(empty.text()).toContain('Invited? The invitation shows up here if you sign in with the email it was sent to.');
    expect(s.testid('businesses-lead').exists()).toBe(false);
  });

  it('a search without matches says so instead of the form', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const bar = s.testid('businesses-search').element as HTMLElement & { value?: string };
    bar.value = 'zzz';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'zzz' } }));
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 0, search: 'zzz' }]);
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.list', page([]));
    expect(s.testid('businesses-no-results').text()).toContain('Nothing matches the search');
    await s.testid('businesses-show-all').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('a failed recovery is said in the person’s language', async () => {
    const s = await setup({
      locale: 'es',
      respond: (c) => (c.path === '/api/hubs/businesses/restore' ? (Promise.reject(new TypeError('Failed to fetch')) as never) : undefined),
    });
    await s.show(page([row('viejo', 'Bar Viejo', { status: 'deleting', can_open: false, open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' })]));
    await s.testid('businesses-row-viejo-restore').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.');
  });

  it('an error says it and retries', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'hubs.business.list'), 'server_error'));
    await flush();
    expect(s.prop('error')).toBe('msg server_error');
    expect(s.prop<Record<string, string>>('labels').loadError).toBe('We could not load your businesses');
  });
});

describe('BusinessListPage: «Create business»', () => {
  async function openCreate(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup({
      respond: (c) => (c.path === '/api/hubs/businesses' && c.method === 'POST' ? Response.json({ id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing' }) : undefined),
      ...extra,
    });
    await s.show(page(ROWS));
    await s.testid('businesses-add').trigger('click');
    await flush();
    return s;
  }

  it('opens the dialog with the form, the dialog’s button creating', async () => {
    const s = await openCreate();
    expect(s.q('create-modal')?.getAttribute('aria-label')).toBe('Create business');
    expect(s.q('create-modal')?.textContent).toContain('What is your business called?');
    expect(s.q('create-modal-submit')?.textContent).toContain('Create my business');
  });

  it('opens by itself from the launcher’s «Create another business» (?create=1), also when the page is shown again', async () => {
    const s = await setup({ path: '/businesses?create=1' });
    await flush();
    expect(s.q('create-modal')).not.toBeNull();
    s.q('create-modal-cancel')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).toBeNull();
    await s.router.push('/businesses?create=1');
    enterView(s.wrapper);
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('follows the new business on its own, also when the list does not show it (a search, another page)', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    s.q('create-modal-submit')!.click();
    await flush();
    expect(s.client.stream.subscriptions('hubs.business.get').map((sub) => sub.params)).toEqual([{ id: 'dulce' }]);
    // The focus moves to the step's own button (V-19).
    expect(focus.mock.contexts).toContain(s.q('create-modal-close-list'));
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'active', hub_error: null, can: { open: true } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Your business is ready');
    expect(focus.mock.contexts).toContain(s.q('create-modal-open'));
  });

  it('after creating: «Preparing», the new row «Preparing» in the list, then «ready» with «Open business»', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Preparing Pastelería Dulce');
    expect(s.q('create-modal')?.textContent).toContain('You can close this window: you will see it in your list as «Preparing».');
    await s.show(page([row('dulce', 'Pastelería Dulce', PREPARING), ...ROWS]), 2);
    expect(s.rows()[0].get('.status-pill').text()).toBe('Preparing');
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'active', hub_error: null, can: { open: true } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Your business is ready');
    expect(s.q('create-modal')?.textContent).toContain('Your address: dulce.localhost:8000');
    s.q('create-modal-open')!.click();
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'dulce', next: '/' });
  });

  it('a preparation the Hub refused says so in the dialog', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing', hub_error: 'hub_refused', can: { open: false } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('It could not be prepared');
    expect(s.q('create-modal')?.textContent).toContain('We saved Pastelería Dulce, but it could not be prepared.');
    s.q('create-modal-close-list')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).toBeNull();
  });
});

describe('BusinessListPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Negocios');
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Negocio', 'Dirección web', 'Estado', 'Plan', 'Rol', 'Último uso']);
    expect(accessibleName(s.testid('businesses-row-bakery-open'))).toBe('Abrir Panadería López');
    expect(accessibleName(s.testid('businesses-row-bakery-manage'))).toBe('Gestionar Panadería López');
  });
});
