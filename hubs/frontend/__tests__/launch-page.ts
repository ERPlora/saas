// The entry (`/launch`) mounted for its tests, signed in by default: the rows of `hubs.business.list` it shows and
// the businesses it opens. A test file mocks `@ionic/vue` and `@erplora/ui/shell` as the panel's tests do and calls
// `setUpLaunchPage()` at its top.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, vi } from 'vitest';

import { navigation } from '../open-business';
import LaunchPage from '../pages/LaunchPage.vue';
import { describeCall, type MountOptions, mountHubs } from './mount-hubs';

export const PREPARING = { status: 'preparing', status_label: 'Preparing', can_open: false, open_blocked_reason: 'preparing' };
export const INVITATION = {
  id: 'm1',
  hub: { id: 'ana', slug: 'ana', name: 'Peluquería Ana' },
  role: 'hub_manager',
  role_label: 'Manager',
  invited_by: 'Carlos Ruiz',
  invited_at: '2026-10-12T10:00:00Z',
  expires_at: '2026-10-19T10:00:00Z',
  message: '',
};
export const page = (rows: unknown[], invitations: unknown[] = []) => ({
  rows,
  total: rows.length,
  limit: 50,
  offset: 0,
  invitations,
  ownership_offers: [],
});
export const OPENED = { url: 'http://bakery.localhost:8000/auth/login?next=/' };

export function setUpLaunchPage(): void {
  afterEach(() => {
    applySurface('web');
    vi.restoreAllMocks();
    document.body.innerHTML = '';
    document.title = '';
  });
}

export async function setup(options: MountOptions = {}) {
  const navigate = vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(LaunchPage, {
    path: '/launch',
    api: (call) => {
      const c = describeCall(call);
      if (c.path === '/api/hubs/businesses/open') return Response.json(OPENED);
      if (c.path === '/api/catalog/business-types') return Response.json({ business_types: [] });
      return Response.json({});
    },
    ...options,
  });
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const title = () => m.wrapper.get('ion-card-title').text();
  const opened = () => m.calls().filter((c) => c.path === '/api/hubs/businesses/open').map((c) => c.body);
  return { ...m, navigate, testid, title, opened };
}

/** Signed in and live, with the first result of the list. */
export async function showing(result: unknown, options: MountOptions = {}) {
  const s = await setup(options);
  const call = await s.live();
  await s.result(call, 'hubs.business.list', result);
  return { ...s, call };
}
