// Businesses (`/dashboard/businesses`): the account's
// businesses in a server-side DataTable (list or cards; cards up to 900 px), with their status, plan,
// role and last use; per row «Open», «Manage», «Recover», «Delete» by what the role allows; above it
// the pending invitations and ownership offers (an unpaid invoice is the bell's); empty,
// the sign-up form itself.
// clock: data only — no code under test compares these dates with now.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { accessibleName, BYE, errorFrame, flush, subId } from '../__tests__/mount-hubs';
import { page, ROWS, row, setup, setUpBusinessListPage } from '../__tests__/business-list-page';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';

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

setUpBusinessListPage();

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

  it('gives the table its row actions to fold: «Open» pinned, «Manage» and «Recover» inline', async () => {
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
    // The address is not cut with «…» (DataTable clips a cell's span): it may take a second line,
    // breaking only after a dot.
    expect(bakery.get('[data-testid="business-host"]').element.tagName).toBe('DIV');
    expect(bakery.find('[data-testid="business-host"] .host-name').exists()).toBe(true);
  });

  it('under the status, why: never a payment the bell already says, a suspension with its day', async () => {
    const s = await setup();
    await s.show(
      page([
        row('plaza', 'Bar La Plaza', { status: 'past_due', status_label: 'Payment pending', unpaid_since: '2026-10-10T14:23:00Z' }),
        row('norte', 'Bar Norte', { status: 'suspended', status_label: 'Suspended', can_open: false, unpaid_since: '2026-10-09T08:00:00Z' }),
      ]),
    );
    expect(s.rows()[0].find('[data-testid="business-status-why"]').exists()).toBe(false);
    expect(s.rows()[1].get('[data-testid="business-status-why"]').text()).toBe(
      'Suspended because of an unpaid invoice since Oct 9, 2026. Your data is safe: pay the invoice and it works again at once.',
    );
  });

  it('a name opens the business’s page for whoever manages it, and the business for anybody else', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    await s.rows()[0].get('[data-testid="business-name"]').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/dashboard/businesses/bakery/summary');
    await s.rows()[2].get('[data-testid="business-name"]').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'salon', next: '/' });
  });
});

describe('BusinessListPage: a clean page', () => {
  it('the list fills the page between the topbar and the footer: rows scroll inside, toolbar and footer stay', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('contentLayout')).toBe('detail-fill');
    expect(s.prop('fill')).toBe(true);
    expect(s.table().element.parentElement?.classList.contains('panel-fill')).toBe(true);
  });

  it('asks for rows per page only when there are more businesses than the shortest page', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop('pageSizeChooser')).toBe(false);
    await s.show(page(ROWS, { total: 11 }), 2);
    expect(s.prop('pageSizeChooser')).toBe(true);
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
    expect(accessibleName(action(s, 'bakery', 'open'))).toBe('Open: Panadería López');
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
    expect(s.router.currentRoute.value.path).toBe('/dashboard/businesses/admin/summary');
  });

  it('«Delete» is not on the row: it lives in the business’s Settings, with its confirmation', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.find('[data-testid$="-delete"]').exists()).toBe(false);
  });

  it('every row button tells a screen reader which business it is for, its short words first', async () => {
    const s = await setup();
    await s.show(page([...ROWS, row('viejo', 'Bar Viejo', { status: 'deleting', can_open: false, open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' })]));
    expect(accessibleName(action(s, 'bakery', 'open'))).toBe('Open: Panadería López');
    expect(accessibleName(action(s, 'bakery', 'manage'))).toBe('Manage: Panadería López');
    expect(accessibleName(action(s, 'viejo', 'restore'))).toBe('Recover: Bar Viejo');
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
  it('an unpaid invoice is no box above the list: its row says it, and paying is the bell’s', async () => {
    const s = await setup();
    await s.show(
      page([row('plaza', 'Bar La Plaza', { status: 'past_due', unpaid_reason: 'payment_failed', unpaid_since: '2026-10-10T10:00:00Z', pay_url: 'https://invoice.stripe.com/i/abc' })]),
    );
    expect(s.wrapper.find('[data-testid^="businesses-unpaid"]').exists()).toBe(false);
    expect(s.wrapper.find('[href^="https://invoice.stripe.com"]').exists()).toBe(false);
    expect(s.rows()[0].text()).toContain('Payment due');
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

  it('the stream gone before any answer (no network, /api/live down): loading, then an error with «Retry», never the sign-up form', async () => {
    const s = await setup();
    s.call.push(BYE);
    await flush();
    expect(s.prop('loading')).toBe(true);
    expect(s.testid('businesses-empty').exists()).toBe(false);
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.prop('loading')).toBe(false);
    expect(s.prop('error')).toBe('Check your connection and try again.');
    expect(s.testid('businesses-empty').exists()).toBe(false);
    expect(s.testid('businesses-reconnecting').exists()).toBe(false);
    const before = s.net.streams.length;
    await s.testid('businesses-retry').trigger('click');
    await s.clock.advance(1);
    expect(s.net.streams.length).toBeGreaterThan(before);
    expect(s.prop('loading')).toBe(true);
    const again = s.net.lastStream();
    again.push('event: hello\ndata: {"stream":"s-2"}\n\n');
    await s.result(again, 'hubs.business.list', page(ROWS));
    expect(s.prop('error')).toBeUndefined();
    expect(s.rows().length).toBe(ROWS.length);
  });

  it('with businesses on screen, a dropped stream keeps them and says it is reconnecting', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.call.push(BYE);
    await flush();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.rows().length).toBe(ROWS.length);
    expect(s.prop('error')).toBeUndefined();
    expect(s.testid('businesses-reconnecting').exists()).toBe(true);
  });

  it('an error says it and retries', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'hubs.business.list'), 'server_error'));
    await flush();
    expect(s.prop('error')).toBe('msg server_error');
    expect(s.prop<Record<string, string>>('labels').loadError).toBe('We could not load your businesses');
  });
});

describe('BusinessListPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Negocios');
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Negocio', 'Dirección web', 'Estado', 'Plan', 'Rol', 'Último uso']);
    expect(accessibleName(s.testid('businesses-row-bakery-open'))).toBe('Abrir: Panadería López');
    expect(accessibleName(s.testid('businesses-row-bakery-manage'))).toBe('Gestionar: Panadería López');
  });
});
