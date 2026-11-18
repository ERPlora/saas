// Businesses on a phone: each business is a card of the table itself, the name heading it, the status (and why) under
// it and the rest as lines with their icons; and in the list the last use is sized by its content, so the name gives
// way before that date is cut.
// clock: data only — no code under test compares these dates with now.
import { DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { viewport } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import { business } from '../__tests__/businesses';
import { accessibleName, describeCall, mountHubs } from '../__tests__/mount-hubs';
import BusinessListPage from './BusinessListPage.vue';

const row = (id: string, name: string, extra: Record<string, unknown> = {}) =>
  business(id, name, { last_opened_at: '2026-10-13T09:12:00Z', can: { open: true, manage: true, restore: false, delete: true }, ...extra });
const ROWS = [
  row('bakery', 'Panadería López'),
  row('cafe', 'Café Central', { status: 'preparing', status_label: 'Preparing', can_open: false, open_blocked_reason: 'preparing', last_opened_at: null }),
  row('salon', 'Peluquería Ana', {
    role: 'hub_manager',
    role_label: 'Manager',
    plan: { slug: 'free', name: 'Free' },
    can: { open: true, manage: false, restore: false, delete: false },
  }),
];
const page = { rows: ROWS, total: ROWS.length, limit: 50, offset: 0, invitations: [], ownership_offers: [] };

async function setup() {
  const m = await mountHubs(BusinessListPage, {
    path: '/dashboard/businesses',
    api: (call) => (describeCall(call).path === '/api/catalog/business-types' ? Response.json({ business_types: [] }) : Response.json({})),
  });
  await m.result(await m.live(), 'hubs.business.list', page);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  return { ...m, table, cards: () => m.wrapper.findAll('.data-table__card') };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('BusinessListPage: on a phone', () => {
  beforeEach(() => viewport(true));

  it('each business is a card of the table: its name heading it, then the status and why', async () => {
    const s = await setup();
    expect(s.cards().map((card) => card.get('.data-table__card-title').text())).toEqual(['Panadería López', 'Café Central', 'Peluquería Ana']);
    expect(s.cards()[0].find('.data-table__card-title [data-testid="business-name"]').exists()).toBe(true);
    expect(s.cards().map((card) => card.get('.data-table__card-status').text())).toEqual([
      'Active',
      'PreparingReady in a few seconds',
      'Active',
    ]);
  });

  it('the web address, the plan, the role and the last use are lines with their icons', async () => {
    const s = await setup();
    const lines = s.cards()[2].findAll('.data-table__card-meta');
    expect(lines.map((line) => line.attributes('data-column'))).toEqual(['host', 'plan', 'role', 'last_opened_at']);
    expect(lines.map((line) => line.get('.data-table__card-meta-value').text())).toEqual([
      'salon.localhost:8000',
      'Free',
      'ManagerManaged by the owner',
      expect.stringMatching(/^Oct 13, 2026/),
    ]);
    expect(lines.every((line) => line.find('.data-table__card-meta-icon').exists())).toBe(true);
    expect(s.wrapper.find('.card-pills').exists()).toBe(false);
  });

  it('a card’s main button says «Open» in short words, for the eye and for a screen reader', async () => {
    const s = await setup();
    const open = s.wrapper.get('[data-testid="businesses-row-bakery-open"]');
    expect([open.text(), accessibleName(open)]).toEqual(['Open', 'Open']);
  });

  it('a business never used has no line for it', async () => {
    const s = await setup();
    expect(s.cards()[1].findAll('.data-table__card-meta').map((line) => line.attributes('data-column'))).toEqual(['host', 'plan', 'role']);
  });
});

describe('BusinessListPage: the list', () => {
  it('sizes the plan and the last use by their content, so the name gives way before they are cut', async () => {
    const s = await setup();
    const columns = (s.table().props() as { columns: Array<{ key: string; width?: string }> }).columns;
    expect(columns.filter((column) => column.width === undefined).map((column) => column.key)).toEqual(['plan', 'last_opened_at']);
  });
});
