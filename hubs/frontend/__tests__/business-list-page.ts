// The businesses page (`/dashboard/businesses`) mounted for its tests: the rows of `hubs.business.list` it shows,
// each with what the server says it allows. A test file mocks `@ionic/vue` and `@erplora/ui/shell` as the panel's
// tests do and calls `setUpBusinessListPage()` at its top.
// clock: data only — no code under test compares these dates with now.
import { DataTable } from '@erplora/ui/components';
import { applySurface, toastSuccess } from '@erplora/ui/shell';
import { afterEach, vi } from 'vitest';
import type { Component } from 'vue';

import { navigation } from '../open-business';
import BusinessListPage from '../pages/BusinessListPage.vue';
import { business } from './businesses';
import { describeCall, type MountOptions, mountHubs } from './mount-hubs';

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

export const row = (id: string, name: string, extra: Record<string, unknown> = {}) => business(id, name, { can: canOf(extra), ...extra });
export const PREPARING = { status: 'preparing', status_label: 'Preparing', can_open: false, open_blocked_reason: 'preparing' };
export const ROWS = [
  row('bakery', 'Panadería López', { last_opened_at: '2026-10-13T09:12:00Z' }),
  row('cafe', 'Café Central', { ...PREPARING, plan: { slug: 'free', name: 'Free' } }),
  row('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', plan: { slug: 'free', name: 'Free' } }),
  row('plaza', 'Bar La Plaza', { status: 'past_due', status_label: 'Payment pending' }),
];
export const page = (rows: unknown[], extra: Record<string, unknown> = {}) => ({
  rows,
  total: rows.length,
  limit: 50,
  offset: 0,
  invitations: [],
  ownership_offers: [],
  ...extra,
});

export function setUpBusinessListPage(): void {
  afterEach(() => {
    applySurface('web');
    vi.restoreAllMocks();
    vi.mocked(toastSuccess).mockClear();
    document.body.innerHTML = '';
  });
}

export async function setup(options: MountOptions & { respond?: (c: ReturnType<typeof describeCall>) => Response | undefined } = {}) {
  vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(BusinessListPage, {
    path: '/dashboard/businesses',
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
