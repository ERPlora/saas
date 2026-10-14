// The Members of a business (mockups `business.html` «members», round 17 §2.7–2.8): the live
// `hubs.member.list` in a server-side DataTable (cards up to 900 px) with name, email, role, status and
// last access; per row ONLY the actions the server computed (`actions`, in its order); «Invite» when the
// account may invite; the places of the plan, a pending ownership offer with «Withdraw», and what
// each role may do.
import { DataTable } from '@erplora/ui/components';
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

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { accessibleName, apiError, BYE, describeCall, errorFrame, flush, mountHubs, subId } from '../__tests__/mount-hubs';
import { member } from '../__tests__/members';
import MembersTab from './MembersTab.vue';

const BUSINESS = {
  id: 'h1',
  name: 'Panadería López',
  status: 'active',
  pending_transfer: null,
  can: { open: true, manage_members: true, manage_settings: true, manage_billing: true, transfer: true, delete: true },
};
const ROWS = [
  member('laura', { name: 'Laura Martín', role: 'hub_owner', role_label: 'Owner', is_me: true, actions: [], assignable_roles: [], last_opened_at: '2026-10-13T09:00:00Z' }),
  member('carlos', { name: 'Carlos Ruiz', role: 'hub_admin', role_label: 'Admin', actions: ['change_role', 'remove', 'transfer'] }),
  member('jorge', {
    name: 'jorge@example.com',
    email: 'jorge@example.com',
    status: 'pending',
    status_label: 'Pending',
    joined_at: null,
    accepted_at: null,
    invited_at: '2026-10-11T10:00:00Z',
    actions: ['change_role', 'resend', 'cancel'],
  }),
];
const page = (rows = ROWS, extra: Record<string, unknown> = {}) => ({
  rows,
  total: rows.length,
  limit: 50,
  offset: 0,
  seats: { used: 3, limit: 5 },
  invitable_roles: ['hub_admin', 'hub_manager', 'hub_employee'],
  ...extra,
});

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

async function setup(business: Record<string, unknown> = {}, api: (c: ReturnType<typeof describeCall>) => Response = () => Response.json({})) {
  const m = await mountHubs(MembersTab, { props: { business: { ...BUSINESS, ...business } }, api: (call) => api(describeCall(call)) });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const actionsOf = (id: string) =>
    m.wrapper.findAll(`[data-testid^="members-row-${id}-"]`).map((b) => b.attributes('data-testid')!.slice(`members-row-${id}-`.length));
  return { ...m, call, table, prop, testid, q, actionsOf, show: (result: unknown, rev?: number) => m.result(call, 'hubs.member.list', result, rev) };
}

describe('MembersTab: the list', () => {
  it('follows hubs.member.list of the business in a server-side table titled «Members», cards up to 900 px', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('hubs.member.list').map((sub) => sub.params)).toEqual([{ hub_id: 'h1', limit: 50, offset: 0 }]);
    await s.show(page());
    expect(s.table().props()).toMatchObject({ serverSide: true, title: 'Members', total: 3, views: ['table', 'cards'], cardBreakpoint: 900, addable: true, testid: 'members' });
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => c.label)).toEqual(['Name', 'Email', 'Role', 'Status', 'Last access']);
  });

  it('marks the account’s own row, paints the statuses, and the invitation’s date', async () => {
    const s = await setup();
    await s.show(page());
    const rows = s.wrapper.findAll('[data-testid="members-row"]');
    expect(rows[0].get('[data-testid="member-you"]').text()).toBe('You');
    expect(rows[1].find('[data-testid="member-you"]').exists()).toBe(false);
    expect(rows.map((r) => r.get('.status-pill').text())).toEqual(['Active', 'Active', 'Pending']);
    expect(rows[2].get('[data-testid="member-last"]').text()).toMatch(/^Invited on Oct 11, 2026/);
  });

  it('gives the table the actions to fold: the server’s, in its order, «Transfer ownership» only in «⋮»', async () => {
    const s = await setup();
    await s.show(page());
    expect(s.prop<Array<Record<string, unknown>>>('actions').map((a) => [a.id, !!a.menuOnly])).toEqual([
      ['change_role', false],
      ['remove', false],
      ['resend', false],
      ['cancel', false],
      ['transfer', true],
    ]);
    expect(s.prop<Array<{ key: string; priority?: string }>>('columns').map((c) => [c.key, c.priority ?? 'normal'])).toEqual([
      ['name', 'high'],
      ['email', 'normal'],
      ['role_label', 'normal'],
      ['status', 'normal'],
      ['last_opened_at', 'low'],
    ]);
    expect(s.prop('entityLabel')).toEqual({ one: 'member', many: 'members' });
    expect(s.wrapper.find('.row-action').exists()).toBe(false);
  });

  it('renders only the actions the server computed, in its order', async () => {
    const s = await setup();
    await s.show(page());
    expect(s.actionsOf('laura')).toEqual([]);
    expect(s.actionsOf('carlos')).toEqual(['change_role', 'remove', 'menu']);
    expect(s.actionsOf('jorge')).toEqual(['change_role', 'resend', 'cancel']);
    await s.testid('members-row-carlos-menu').trigger('click');
    await flush();
    expect(s.wrapper.find('[data-testid="members-row-carlos-transfer"]').element.tagName).toBe('ION-ITEM');
    expect(s.wrapper.find('[data-testid="members-row-carlos-transfer"]').text()).toBe('Transfer the ownership to Carlos Ruiz');
  });

  it('without the right to invite (no invitable roles) there is no «Invite»', async () => {
    const s = await setup();
    await s.show(page(ROWS, { invitable_roles: [] }));
    expect(s.prop('addable')).toBe(false);
  });

  it('says the places of the plan, and what each role may do', async () => {
    const s = await setup();
    await s.show(page());
    expect(s.testid('members-seats').text()).toBe('3 of 5 places on the plan');
    expect(s.testid('members-roles').text()).toContain('What can each one do?');
    expect(s.testid('members-roles').text()).toContain('Owner: everything, also the plan, transferring and deleting the business.');
  });

  it('an error is the table’s, with «Retry»', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'hubs.member.list'), 'server_error'));
    await flush();
    expect(s.prop('error')).toBe('msg server_error');
    expect(s.prop<Record<string, string>>('labels').loadError).toBe('We could not load the members');
  });
});

describe('MembersTab: a clean page (Ioan, 2026-10-14)', () => {
  it('the stream gone before any answer: loading, then the table’s error with «Retry», never an empty list (R-04)', async () => {
    const s = await setup();
    s.call.push(BYE);
    await flush();
    expect(s.prop('loading')).toBe(true);
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.prop('loading')).toBe(false);
    expect(s.prop('error')).toBe('Check your connection and try again.');
    const streams = s.net.streams.length;
    s.table().vm.$emit('retry');
    await s.clock.advance(1);
    expect(s.net.streams.length).toBeGreaterThan(streams);
    expect(s.prop('loading')).toBe(true);
  });

  it('the list fills its section: a `.panel-fill` stack that grows in the page, the table with `fill`', async () => {
    const s = await setup();
    await s.show(page());
    expect(s.prop('fill')).toBe(true);
    expect(s.wrapper.element.classList.contains('panel-fill')).toBe(true);
    expect(s.table().element.parentElement).toBe(s.wrapper.element);
  });

  it('asks for rows per page only when there are more members than the shortest page (mockups README §3b)', async () => {
    const s = await setup();
    await s.show(page());
    expect(s.prop('pageSizeChooser')).toBe(false);
    await s.show(page(ROWS, { total: 11 }), 2);
    expect(s.prop('pageSizeChooser')).toBe(true);
  });
});

describe('MembersTab: actions', () => {
  it('every row button is named with its member for a screen reader', async () => {
    const s = await setup();
    await s.show(page());
    const label = (id: string) => accessibleName(s.testid(id));
    expect(label('members-row-carlos-change_role')).toBe('Change the role of Carlos Ruiz');
    expect(label('members-row-carlos-remove')).toBe('Remove Carlos Ruiz');
    expect(label('members-row-jorge-resend')).toBe('Send the invitation again to jorge@example.com');
    expect(label('members-row-jorge-cancel')).toBe('Cancel the invitation to jorge@example.com');
  });

  it('a lost connection on «Resend» is said in the person’s language', async () => {
    const s = await setup({}, () => Promise.reject(new TypeError('Failed to fetch')) as never);
    await s.show(page());
    await s.testid('members-row-jorge-resend').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('We could not reach ERPlora. Check your connection and try again.');
  });

  it('«Invite» opens the invitation dialog', async () => {
    const s = await setup();
    await s.show(page());
    await s.testid('members-add').trigger('click');
    await flush();
    expect(s.q('invite-modal')?.getAttribute('aria-label')).toBe('Invite to Panadería López');
  });

  it('«Change role», «Remove», «Cancel invitation» and «Transfer ownership» open their dialogs', async () => {
    const s = await setup();
    await s.show(page());
    await s.testid('members-row-carlos-change_role').trigger('click');
    await flush();
    expect(s.q('role-modal')?.getAttribute('aria-label')).toBe('Change the role of Carlos Ruiz');
    await s.testid('members-row-carlos-remove').trigger('click');
    await flush();
    expect(s.q('remove-dialog')?.getAttribute('aria-label')).toBe('Remove Carlos Ruiz');
    await s.testid('members-row-jorge-cancel').trigger('click');
    await flush();
    expect(s.q('remove-dialog')?.getAttribute('aria-label')).toBe('Cancel the invitation');
    await s.testid('members-row-carlos-menu').trigger('click');
    await flush();
    await s.testid('members-row-carlos-transfer').trigger('click');
    await flush();
    expect(s.q('transfer-dialog')?.getAttribute('aria-label')).toBe('Transfer Panadería López');
  });

  it('«Resend» sends the invitation again and says to whom', async () => {
    const s = await setup({}, (c) => (c.path === '/api/hubs/members/resend' ? Response.json(ROWS[2]) : Response.json({})));
    await s.show(page());
    await s.testid('members-row-jorge-resend').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/members/resend', { id: 'jorge' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Invitation sent again to jorge@example.com');
  });

  it('a refused «Resend» is said', async () => {
    const s = await setup({}, () => apiError(409, 'hubs.business_deleted', 'This business was deleted.'));
    await s.show(page());
    await s.testid('members-row-jorge-resend').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('This business was deleted.');
  });

  it('a pending ownership offer is said, and the owner withdraws it', async () => {
    const s = await setup(
      { pending_transfer: { id: 't1', to_email: 'carlos@example.com', expires_at: '2026-10-20T10:00:00Z' } },
      (c) => (c.path === '/api/hubs/ownership/cancel' ? Response.json({ id: 't1', status: 'cancelled' }) : Response.json({})),
    );
    await s.show(page());
    expect(s.testid('members-transfer').text()).toContain('Ownership offered to carlos@example.com');
    await s.testid('members-transfer-cancel').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/ownership/cancel', { id: 't1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Offer withdrawn');
  });

  it('speaks Spanish', async () => {
    const s = await mountHubs(MembersTab, { props: { business: BUSINESS }, locale: 'es' });
    const call = await s.live();
    await s.result(call, 'hubs.member.list', page());
    expect(accessibleName(s.wrapper.get('[data-testid="members-row-carlos-change_role"]'))).toBe('Cambiar el rol de Carlos Ruiz');
    expect(s.wrapper.find('[data-testid="members-seats"]').text()).toBe('3 de 5 plazas del plan');
  });
});
