// The entry (`/launch`, round 17 §2.2; mockups `launch.html`, README §5): a centred card without the
// menu that never enters by itself. Signed out → sign in and come back; no business → create the first
// one here (or, invited, the invitation is the card), then «Preparing» and it opens by itself; one
// business → «Open X» or «Go to the panel», with why it does not open; several → the last opened first.
// Live: `hubs.business.list` (also the invitations).
import { applySurface } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
import { anonymous, fakeAllauth, pendingEmailVerification, pendingLoginCode, signedIn } from '../../../accounts/frontend/__tests__/allauth-server';
import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
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

describe('LaunchPage: signed out, the sign-in itself', () => {
  // The entrance holds the form with the tabs «Sign in» and «Create account» (Ioan, 2026-10-15;
  // FIX-LAUNCH-TABS), in the frame of the old template login (`AuthShell`): logo, «ERPlora Cloud», «Global
  // panel», the card and the terms.
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    document.cookie = 'csrftoken=tok-123';
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is the old login card with the form, and subscribes to nothing', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    await flush();
    expect(s.wrapper.get('h1.biz-name').text()).toBe('ERPlora Cloud');
    expect(s.wrapper.get('.biz-sub').text()).toBe('Global panel');
    const card = s.wrapper.get('ion-card.glass');
    expect(card.find('form[data-testid="login-form"]').exists()).toBe(true);
    expect(card.find('[data-testid="login-tabs"]').exists()).toBe(true);
    expect(card.text()).toContain('Enter your email and password.');
    for (const testid of ['login-email', 'login-password', 'login-submit']) expect(card.find(`[data-testid="${testid}"]`).exists()).toBe(true);
    expect(card.get('[data-testid="login-submit"]').text()).toBe('Sign in');
    expect(s.wrapper.find('ion-card-title').exists()).toBe(false);
    expect(s.client.stream.subscriptions('hubs.business.list')).toEqual([]);
    expect(document.title).toBe('Sign In - ERPlora Cloud');
  });

  it('carries the terms under the card, as the template login did', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    const foot = s.wrapper.get('.foot');
    expect(foot.text()).toContain('By continuing you agree to our');
    expect(foot.findAll('a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['Terms', '/legal/terms/'],
      ['Privacy Policy', '/legal/privacy/'],
    ]);
  });

  it('inside the installed app the terms open in app mode, with a way back (PUBLIC-F26)', async () => {
    applySurface('desktop');
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    expect(s.wrapper.get('.foot').findAll('a').map((a) => a.attributes('href'))).toEqual([
      '/legal/terms/?surface=desktop',
      '/legal/privacy/?surface=desktop',
    ]);
  });

  it('signs in and loads the launcher again with the new session', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': signedIn });
    const s = await setup({ session: ANONYMOUS });
    const input = (name: string) => s.wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
    await input('email').setValue('owner@example.com');
    await input('password').setValue('owner');
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(server.callsTo('POST /auth/login').map((call) => call.body)).toEqual([{ email: 'owner@example.com', password: 'owner' }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('asks for the mailed code next, carrying where the person was going', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode });
    const s = await setup({ session: ANONYMOUS, path: '/launch?next=%2Faccount' });
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/verify-email?next=/account');
  });

  it('speaks Spanish', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS, locale: 'es' });
    expect(s.wrapper.get('.biz-sub').text()).toBe('Panel global');
    expect(s.wrapper.get('[data-testid="login-submit"]').text()).toBe('Entrar');
    expect(document.title).toBe('Iniciar Sesión - ERPlora Cloud');
  });

  // Where the old sign-up pages lead (gh:saas#894, gh:saas#943): the same card, on «Create account».
  it('opens «Create account» from /launch?tab=signup, and creates the account there', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
    const s = await setup({ session: ANONYMOUS, path: '/launch?tab=signup&next=%2Faccount' });
    const card = s.wrapper.get('ion-card.glass');
    expect(card.get('[data-testid="login-submit"]').text()).toBe('Create account');
    const input = (name: string) => s.wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
    await input('email').setValue('new@example.com');
    await input('password').setValue('a long pass phrase');
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(server.callsTo('POST /auth/signup').map((call) => call.body)).toEqual([{ email: 'new@example.com', password: 'a long pass phrase' }]);
    expect(server.callsTo('POST /auth/login')).toEqual([]);
    expect(s.router.currentRoute.value.fullPath).toBe('/verify-email?next=/account');
  });
});

describe('LaunchPage: signed in, with somewhere to go (`?next=`)', () => {
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('goes there at once, as the template login sent a signed-in visitor on', async () => {
    await setup({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/launch'])('stays for a next elsewhere or here (%s)', async (next) => {
    const s = await setup({ path: `/launch?next=${encodeURIComponent(next)}` });
    expect(assign).not.toHaveBeenCalled();
    expect(s.client.stream.subscriptions('hubs.business.list')).toHaveLength(1);
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

  it('the stream gone before any answer (no network, /api/live down): an error with «Retry» after the time limit, never a spinner for ever (R-08)', async () => {
    const s = await setup();
    const call = await s.live();
    call.push(BYE);
    await flush();
    expect(s.testid('launch-loading').exists()).toBe(true);
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.testid('launch-loading').exists()).toBe(false);
    expect(s.testid('launch-error').text()).toContain('We could not load your businesses.');
    expect(s.testid('launch-error').text()).toContain('Check your connection and try again.');
    const streams = s.net.streams.length;
    await s.testid('launch-retry').trigger('click');
    await s.clock.advance(1);
    expect(s.net.streams.length).toBeGreaterThan(streams);
    expect(s.testid('launch-loading').exists()).toBe(true);
    const again = s.net.lastStream();
    again.push('event: hello\ndata: {"stream":"s-2"}\n\n');
    await s.result(again, 'hubs.business.list', page([row('bakery', 'Panadería López')]));
    expect(s.testid('launch-business').exists()).toBe(true);
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
    // Audit 2 R-25: it breaks only after a dot, never at a hyphen.
    expect(tile.find('.launch-biz__url .host-name').exists()).toBe(true);
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

  it('with a payment pending it still opens, and says to pay (without its date, no number of days: R-06)', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { status: 'past_due', status_label: 'Payment pending' })]));
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Payment due');
    expect(s.testid('launch-reason').text()).toBe('There is an unpaid invoice: pay it so the business is not suspended.');
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

describe('LaunchPage: the way to pay (audit 2026-10-14, R-06 and R-07)', () => {
  const OWED = {
    status: 'past_due',
    status_label: 'Payment pending',
    unpaid_reason: 'payment_failed',
    unpaid_since: '2026-10-10T14:23:00Z',
    pay_url: 'https://invoice.stripe.com/i/bakery',
  };
  const SUSPENDED = { ...OWED, status: 'suspended', status_label: 'Suspended', can_open: false, open_blocked_reason: 'suspended', unpaid_since: '2026-10-09T08:00:00Z' };

  it('past due on the web: its real deadline, «Pay the invoice» first and «Open» second', async () => {
    const s = await showing(page([row('bakery', 'Bakery', OWED)]));
    expect(s.testid('launch-reason').text()).toBe('There is an unpaid invoice. Pay it before Oct 17, 2026 or the business is suspended.');
    expect(ionProps(s.testid('unpaid-pay'), 'href', 'fill', 'size')).toEqual({ href: 'https://invoice.stripe.com/i/bakery', fill: 'solid', size: 'large' });
    expect(ionProps(s.testid('launch-open'), 'fill', 'disabled')).toEqual({ fill: 'outline', disabled: false });
  });

  it('after a declined card: «Change card» first, «Pay» waits', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...OWED, unpaid_reason: 'card_declined' })]));
    expect(s.testid('unpaid-change-card').text()).toContain('Change card');
    expect(ionProps(s.testid('unpaid-pay'), 'disabled')).toEqual({ disabled: true });
  });

  it('suspended on the web: since when, and «Pay the invoice» instead of «Open»', async () => {
    const s = await showing(page([row('bakery', 'Bakery', SUSPENDED)]));
    expect(s.testid('launch-reason').text()).toBe(
      'Suspended because of an unpaid invoice since Oct 9, 2026. Your data is safe: pay the invoice and it works again at once.',
    );
    expect(s.testid('unpaid-pay').exists()).toBe(true);
    expect(s.testid('launch-open').exists()).toBe(false);
  });

  it('inside the app: until when and where to pay, no button to pay, «Open» first', async () => {
    applySurface('desktop');
    const s = await showing(page([row('bakery', 'Bakery', OWED)]));
    expect(s.testid('launch-reason').text()).toBe(
      'There is an unpaid invoice: it keeps working until Oct 17, 2026. To pay it, go to erplora.com in your browser.',
    );
    expect(s.testid('unpaid-pay').exists()).toBe(false);
    expect(ionProps(s.testid('launch-open'), 'fill')).toEqual({ fill: 'solid' });
  });

  it('whoever may not pay it (no `pay_url`) keeps «Open» first, with the deadline', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...OWED, pay_url: null })]));
    expect(s.testid('unpaid-pay').exists()).toBe(false);
    expect(ionProps(s.testid('launch-open'), 'fill')).toEqual({ fill: 'solid' });
  });

  it('with several businesses, the one that owes says until when and offers to pay it', async () => {
    const s = await showing(page([row('salon', 'Peluquería Ana'), row('bakery', 'Bakery', OWED)]), { locale: 'es' });
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles[1].get('.launch-biz__why').text()).toBe('Hay una factura sin pagar. Págala antes del 17 oct 2026 o el negocio se suspende.');
    expect(tiles[1].find('[data-testid="unpaid-pay"]').exists()).toBe(true);
    expect(tiles[0].find('[data-testid="unpaid-pay"]').exists()).toBe(false);
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

describe('LaunchPage: a deleted business is recovered from the card (audit 2 R-07)', () => {
  const DELETED = {
    status: 'deleting',
    status_label: 'Deleted',
    can_open: false,
    open_blocked_reason: 'deleting',
    deletion_requested_at: '2026-10-10T10:00:00Z',
    purge_after: '2027-01-08T10:00:00Z',
    can: { open: false, manage: false, restore: true, delete: false },
  };

  it('one: its owner recovers it, the main action, and it is said; no «Open»', async () => {
    const s = await showing(page([row('bakery', 'Bakery', DELETED)]), {
      api: (call) =>
        describeCall(call).path === '/api/hubs/businesses/restore' ? Response.json({ id: 'bakery', name: 'Bakery', status: 'active' }) : Response.json({}),
    });
    expect(s.testid('launch-reason').text()).toContain('Deleted. You can recover it until Jan 8, 2027');
    const recover = s.testid('recover-business');
    expect(recover.text()).toContain('Recover business');
    expect(ionProps(recover, 'size', 'expand')).toEqual({ size: 'large', expand: 'block' });
    expect(s.testid('launch-open').exists()).toBe(false);
    await recover.trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/restore')?.body).toEqual({ id: 'bakery' });
  });

  it('whoever may not recover it sees why, and no button', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...DELETED, role: 'hub_admin', can: { ...DELETED.can, restore: false } })]));
    expect(s.testid('recover-business').exists()).toBe(false);
    expect(s.testid('launch-panel').exists()).toBe(true);
  });

  it('several: the deleted one offers «Recover», named with its business', async () => {
    const s = await showing(page([row('salon', 'Peluquería Ana', { can: DELETED.can }), row('bakery', 'Bakery', DELETED)]));
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles[0].find('[data-testid="recover-business"]').exists()).toBe(false);
    expect(accessibleName(tiles[1].get('[data-testid="recover-business"]'))).toBe('Recover Bakery');
  });
});

describe('LaunchPage: one filled button per business (audit 2 S-06)', () => {
  it('several: a business that owes keeps the payment filled and «Open» outlined', async () => {
    const OWED = { status: 'past_due', status_label: 'Payment pending', unpaid_reason: 'payment_failed', unpaid_since: '2026-10-10T14:23:00Z', pay_url: 'https://invoice.stripe.com/i/bakery' };
    const s = await showing(page([row('salon', 'Peluquería Ana'), row('bakery', 'Bakery', OWED)]));
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(ionProps(tiles[1].get('[data-testid="unpaid-pay"]'), 'fill')).toEqual({ fill: 'solid' });
    expect(ionProps(tiles[1].get('[data-testid="launch-open"]'), 'fill')).toEqual({ fill: 'outline' });
    expect(ionProps(tiles[0].get('[data-testid="launch-open"]'), 'fill')).toEqual({ fill: 'solid' });
  });
});
