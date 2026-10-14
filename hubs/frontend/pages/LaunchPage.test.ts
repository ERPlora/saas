// The entry (`/launch`, round 17 §2.2; mockups `launch.html`, README §5): a centred card without the
// menu that never enters by itself. Signed out → sign in and come back; no business → create the first
// one here (or, invited, the invitation is the card), then «Preparing» and it opens by itself; one
// business → «Open X» or «Go to the panel», with why it does not open; several → the last opened first.
// Live: `hubs.business.list` (also the invitations).
import { applySurface } from '@erplora/ui/shell';
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

import { accessibleName, ANONYMOUS, apiError, BYE, describeCall, enterView, errorFrame, flush, ionProps, type MountOptions, mountHubs, subId } from '../__tests__/mount-hubs';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import LaunchPage from './LaunchPage.vue';
import { navigation } from '../open-business';

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
  ...extra,
});
const PREPARING = { status: 'preparing', status_label: 'Preparing', can_open: false, open_blocked_reason: 'preparing' };
const INVITATION = {
  id: 'm1',
  hub: { id: 'ana', slug: 'ana', name: 'Peluquería Ana' },
  role: 'hub_manager',
  role_label: 'Manager',
  invited_by: 'Carlos Ruiz',
  invited_at: '2026-10-12T10:00:00Z',
  expires_at: '2026-10-19T10:00:00Z',
  message: '',
};
const page = (rows: unknown[], invitations: unknown[] = []) => ({
  rows,
  total: rows.length,
  limit: 50,
  offset: 0,
  invitations,
  ownership_offers: [],
});
const OPENED = { url: 'http://bakery.localhost:8000/auth/login?next=/' };

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.title = '';
});

async function setup(options: MountOptions = {}) {
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
async function showing(result: unknown, options: MountOptions = {}) {
  const s = await setup(options);
  const call = await s.live();
  await s.result(call, 'hubs.business.list', result);
  return { ...s, call };
}

describe('LaunchPage: signed out', () => {
  it('asks to sign in and come back here, and subscribes to nothing', async () => {
    const s = await setup({ session: ANONYMOUS });
    expect(s.title()).toBe('Sign in to ERPlora');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Sign in with your ERPlora account.');
    expect(s.client.stream.subscriptions('hubs.business.list')).toEqual([]);
    await s.testid('launch-sign-in').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/login?next=/launch');
    expect(ionProps(s.testid('launch-sign-up'), 'href')).toEqual({ href: '/accounts/signup/?next=/launch' });
  });

  it('inside the app, says the app uses the erplora.com account', async () => {
    applySurface('desktop');
    const s = await setup({ session: ANONYMOUS });
    expect(s.wrapper.get('.shell-lead').text()).toBe('The app uses your erplora.com account.');
  });
});

describe('LaunchPage: loading and errors', () => {
  it('follows the account’s businesses, with a spinner until the first result', async () => {
    const s = await setup();
    await s.live();
    expect(s.client.stream.subscriptions('hubs.business.list').map((sub) => sub.params)).toEqual([{ limit: 50, offset: 0 }]);
    expect(s.testid('launch-loading').exists()).toBe(true);
    expect(document.title).toBe('Enter - ERPlora');
  });

  it('says it could not load them and retries on demand', async () => {
    const s = await setup();
    const call = await s.live();
    call.push(errorFrame(subId(s.client, 'hubs.business.list'), 'server_error'));
    await flush();
    expect(s.testid('launch-error').text()).toContain('We could not load your businesses.');
    const streams = s.net.streams.length;
    await s.testid('launch-retry').trigger('click');
    await s.clock.advance(150);
    expect(s.net.streams.length).toBeGreaterThan(streams);
  });

  it('shows the notice of the 2FA settings when it sent here', async () => {
    const s = await showing(page([row('bakery', 'Bakery')]), { path: '/launch?notice=mfa_unavailable' });
    expect(s.testid('launch-notice').text()).toContain('Two-factor authentication is not available on this account yet.');
  });
});

describe('LaunchPage: the first time (no business)', () => {
  it('is the sign-up: the form, «or», «Go to the panel» and where an invitation would show', async () => {
    const s = await showing(page([]));
    expect(s.title()).toBe('Create your business');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Free and no card: just the name and the country.');
    expect(s.wrapper.findComponent(BusinessCreateForm).exists()).toBe(true);
    expect(s.testid('launch-divider').text()).toBe('or');
    expect(s.testid('launch-foot').text()).toBe('Invited? The invitation shows up here if you sign in with the email it was sent to.');
    await s.testid('launch-panel').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/businesses');
  });

  it('after creating it, shows its preparation and opens it by itself once it is ready', async () => {
    const s = await showing(page([]));
    s.wrapper.findComponent(BusinessCreateForm).vm.$emit('created', { id: 'bakery', name: 'Bakery', status: 'preparing' }, { typeName: 'Bakery and pastry' });
    await flush();
    expect(s.title()).toBe('Preparing Bakery');
    expect(s.wrapper.get('ol.deploy-steps').text()).toContain('Installing the modules for Bakery and pastry');
    expect(s.testid('launch-panel').text()).toBe('Go to the panel meanwhile');
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', PREPARING)]), 2);
    expect(s.opened()).toEqual([]);
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery')]), 3);
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(s.navigate).toHaveBeenCalledOnce();
  });
});

describe('LaunchPage: the preparation the Hub refused', () => {
  it('after creating, a refused preparation says so and offers the panel, instead of preparing for ever', async () => {
    const s = await showing(page([]));
    s.wrapper.findComponent(BusinessCreateForm).vm.$emit('created', { id: 'bakery', name: 'Bakery', status: 'preparing' }, { typeName: null });
    await flush();
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', { ...PREPARING, open_blocked_reason: 'error', hub_error: 'x' })]), 2);
    expect(s.title()).toBe('It could not be prepared');
    expect(s.testid('launch-failed').text()).toContain('We saved Bakery, but it could not be prepared.');
    expect(s.wrapper.find('ol.deploy-steps').exists()).toBe(false);
    expect(s.testid('launch-panel').text()).toBe('Go to the panel');
    expect(s.opened()).toEqual([]);
  });
});

describe('LaunchPage: opening by itself', () => {
  it('a refused opening is tried again with the next news of the business', async () => {
    let refuse = true;
    const s = await showing(page([row('bakery', 'Bakery', PREPARING)]), {
      api: (call) => {
        const c = describeCall(call);
        if (c.path === '/api/hubs/businesses/open') {
          if (refuse) {
            refuse = false;
            return apiError(409, 'hubs.business_preparing', 'This business is still being prepared.');
          }
          return Response.json(OPENED);
        }
        return Response.json({ business_types: [] });
      },
    });
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery')]), 2);
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(s.navigate).not.toHaveBeenCalled();
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', { last_opened_at: null })]), 3);
    expect(s.opened()).toHaveLength(2);
    expect(s.navigate).toHaveBeenCalledOnce();
  });
});

describe('LaunchPage: coming back to it', () => {
  it('reads its address and names the tab again each time it is shown (Ionic reuses the page)', async () => {
    const s = await showing(page([row('bakery', 'Bakery')]));
    expect(s.testid('launch-notice').exists()).toBe(false);
    document.title = 'Other page';
    await s.router.push('/launch?notice=mfa_unavailable');
    enterView(s.wrapper);
    await flush();
    expect(s.testid('launch-notice').exists()).toBe(true);
    expect(document.title).toBe('Enter - ERPlora');
  });
});

describe('LaunchPage: invited, without a business of one’s own', () => {
  it('the card is the invitation: accept and enter, decline, or create one’s own', async () => {
    const s = await showing(page([], [INVITATION]));
    expect(s.title()).toBe('You have been invited to Peluquería Ana');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Carlos Ruiz gives you access as Manager.');
    expect(s.testid('launch-accept').text()).toContain('Accept and enter');
    await s.testid('launch-decline').trigger('click');
    await flush();
    expect(document.querySelector('[data-testid="decline-dialog"]')).not.toBeNull();
    await s.testid('launch-create-own').trigger('click');
    await flush();
    expect(s.title()).toBe('Create your business');
  });

  it('«Accept and enter» accepts the invitation', async () => {
    const s = await showing(page([], [INVITATION]));
    await s.testid('launch-accept').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/invitations/accept')?.body).toEqual({ id: 'm1' });
  });
});

describe('LaunchPage: one business', () => {
  it('greets, shows the business and opens it, or goes to the panel', async () => {
    const s = await showing(page([row('bakery', 'Panadería López')]));
    expect(s.title()).toBe('Hello, Laura');
    expect(s.wrapper.get('.shell-lead').text()).toBe('What do you want to do?');
    const tile = s.testid('launch-business');
    expect(tile.get('h2').text()).toBe('Panadería López');
    expect(tile.get('.launch-biz__url').text()).toBe('bakery.localhost:8000');
    expect(tile.get('.status-pill').text()).toBe('Active');
    expect(tile.get('.launch-biz__meta').text()).toBe('Plan Starter · Owner');
    const open = s.testid('launch-open');
    expect(open.text()).toContain('Open Panadería López');
    await open.trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(s.testid('launch-foot').text()).toBe('In the panel you manage the business, the team and your account.');
  });

  it('greets by the account alone when the name is an email', async () => {
    const s = await showing(page([row('bakery', 'Bakery')]), {
      session: { user: { id: 'u1', label: 'owner@example.com' }, permissions: [], menu: [], apps: [], language: 'en' },
    });
    expect(s.title()).toBe('Hello');
  });

  it('being prepared: «Open» is disabled with why, and it opens by itself when ready', async () => {
    const s = await showing(page([row('bakery', 'Bakery', PREPARING)]));
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: true });
    expect(s.testid('launch-reason').text()).toBe('We are preparing it. It opens by itself when it is ready.');
    expect(s.wrapper.find('ion-progress-bar').exists()).toBe(true);
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery')]), 2);
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
  });

  it('a preparation the Hub refused: a danger pill, why, and no way to open it', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...PREPARING, open_blocked_reason: 'error', hub_error: 'boom' })]));
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Not prepared');
    expect(s.testid('launch-reason').text()).toBe('We could not prepare it. We keep retrying; if it keeps failing, contact us.');
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: true });
  });

  it('with a payment pending it still opens, and says to pay', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { status: 'past_due', status_label: 'Payment pending' })]));
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Payment due');
    expect(s.testid('launch-reason').text()).toBe('There is an unpaid invoice. It keeps working for 7 more days; pay it so it is not suspended.');
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: false });
  });

  it('suspended: no «Open» at all, and inside the app how to pay without a link', async () => {
    applySurface('mobile');
    const s = await showing(page([row('bakery', 'Bakery', { status: 'suspended', can_open: false, open_blocked_reason: 'suspended' })]));
    expect(s.testid('launch-open').exists()).toBe(false);
    expect(s.testid('launch-reason').text()).toBe(
      'Suspended because of an unpaid invoice. Your data is safe. To pay it, go to erplora.com in your browser.',
    );
    expect(s.testid('launch-reason').find('a').exists()).toBe(false);
    expect(s.testid('launch-panel').exists()).toBe(true);
  });
});

describe('LaunchPage: several businesses', () => {
  const ROWS = [
    row('bakery', 'Panadería López', { last_opened_at: '2026-10-13T09:12:00Z' }),
    row('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', plan: { slug: 'free', name: 'Free' } }),
    row('cafe', 'Café Central', PREPARING),
  ];

  it('lists them in the server’s order (the last opened first), each with its «Open»', async () => {
    const s = await showing(page(ROWS));
    expect(s.title()).toBe('Where are you working today?');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Choose a business to open it.');
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles.map((tile) => tile.get('h2').text())).toEqual(['Panadería López', 'Peluquería Ana', 'Café Central']);
    expect(tiles[0].get('.tag-recent').text()).toBe('Last opened');
    expect(tiles[1].find('.tag-recent').exists()).toBe(false);
    expect(tiles[1].get('.launch-biz__meta').text()).toBe('Manager');
    // With several, nothing opens by itself: the person chooses.
    expect(tiles[2].get('.launch-biz__why').text()).toBe('Ready in a few seconds');
    const opens = s.wrapper.findAll('[data-testid="launch-open"]');
    expect(opens.map((b) => accessibleName(b))).toEqual(['Open Panadería López', 'Open Peluquería Ana', 'Open Café Central']);
    expect(ionProps(opens[2], 'disabled')).toEqual({ disabled: true });
    await opens[1].trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'salon', next: '/' }]);
  });

  it('offers to create another business in the panel', async () => {
    const s = await showing(page(ROWS));
    await s.testid('launch-create-another').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/businesses?create=1');
  });

  it('points to a pending invitation above the businesses', async () => {
    const s = await showing(page(ROWS, [INVITATION]));
    expect(s.testid('launch-invitation').text()).toContain('You have been invited to Peluquería Ana');
    await s.testid('launch-invitation-open').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/invitations/m1');
  });
});

describe('LaunchPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await showing(page([row('bakery', 'Panadería López')]), { locale: 'es' });
    expect(s.title()).toBe('Hola, Laura');
    expect(s.testid('launch-open').text()).toContain('Abrir Panadería López');
    expect(s.testid('launch-panel').text()).toBe('Ir al panel');
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Activo');
    expect(document.title).toBe('Entrar - ERPlora');
  });
});

describe('LaunchPage: the stream', () => {
  it('a closed stream reopens on its own (nothing to do on the page)', async () => {
    const s = await showing(page([row('bakery', 'Bakery')]));
    s.call.push(BYE);
    await flush();
    expect(s.testid('launch-business').exists()).toBe(true);
  });
});
