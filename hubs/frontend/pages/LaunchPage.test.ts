// The entry (`/launch`): a centred card without the
// menu that never enters by itself. No business → create the first
// one here (or, invited, the invitation is the card), then «Preparing» and it opens by itself.
// Live: `hubs.business.list` (also the invitations).
// clock: data only — no code under test compares these dates with now.
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { apiError, BYE, describeCall, enterView, errorFrame, flush, subId } from '../__tests__/mount-hubs';
import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import { business } from '../__tests__/businesses';
import { INVITATION, OPENED, page, PREPARING, setup, setUpLaunchPage, showing } from '../__tests__/launch-page';

const row = business;

setUpLaunchPage();

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

  it('the stream gone before any answer (no network, /api/live down): an error with «Retry» after the time limit, never a spinner for ever', async () => {
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
    expect(s.router.currentRoute.value.path).toBe('/dashboard/businesses');
  });

  it('after creating it, shows its preparation and opens it by itself once it is ready', async () => {
    const s = await showing(page([]));
    s.wrapper.findComponent(BusinessCreateForm).vm.$emit('created', { id: 'bakery', name: 'Bakery', status: 'preparing' }, { typeName: 'Bakery and pastry' });
    await flush();
    expect(s.title()).toBe('Preparing Bakery');
    expect(s.wrapper.get('ol.deploy-steps').text()).toContain('Setting up your business: Bakery and pastry');
    expect(s.testid('launch-panel').text()).toBe('Go to the panel meanwhile');
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', PREPARING)]), 2);
    expect(s.opened()).toEqual([]);
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery')]), 3);
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(s.navigate).toHaveBeenCalledOnce();
  });
});

describe('LaunchPage: the preparation paused for maintenance', () => {
  const maintenance = { frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' };

  /** The launcher of an account without a business, right after creating Bakery here. */
  async function createdBakery() {
    const s = await showing(page([]));
    s.wrapper.findComponent(BusinessCreateForm).vm.$emit('created', { id: 'bakery', name: 'Bakery', status: 'preparing' }, { typeName: null });
    await flush();
    return s;
  }

  it('passes the real maintenance to the preparing card instead of calling it failed', async () => {
    const s = await createdBakery();
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', { ...PREPARING, maintenance })]), 2);
    expect(s.wrapper.find('[data-testid="preparing-maintenance"]').exists()).toBe(true);
    expect(s.wrapper.find('[data-testid="launch-failed"]').exists()).toBe(false);
    expect(s.opened()).toEqual([]);
  });

  it('promises no seconds while the pause lasts, and says «a few seconds» again once it lifts', async () => {
    const s = await createdBakery();
    expect(s.wrapper.get('.shell-lead').text()).toBe('It usually takes a few seconds.');
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', { ...PREPARING, maintenance })]), 2);
    expect(s.wrapper.find('[data-testid="preparing-maintenance"]').exists()).toBe(true);
    expect(s.wrapper.find('.shell-lead').exists()).toBe(false);
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery', { ...PREPARING, maintenance: null })]), 3);
    expect(s.wrapper.find('[data-testid="preparing-maintenance"]').exists()).toBe(false);
    expect(s.wrapper.get('.shell-lead').text()).toBe('It usually takes a few seconds.');
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

  it('«Accept and enter» keeps spinning while the business it joined opens', async () => {
    const s = await showing(page([], [INVITATION]), {
      api: (call) => {
        const c = describeCall(call);
        if (c.path === '/api/hubs/invitations/accept') return Response.json({ ...INVITATION.hub, can_open: true });
        return Response.json(c.path === '/api/hubs/businesses/open' ? OPENED : {});
      },
    });
    await s.testid('launch-accept').trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'ana', next: '/' }]);
    expect(s.testid('launch-accept').find('ion-spinner').exists()).toBe(true);
  });

  it('«Decline» opens the confirmation, closed until then', async () => {
    const s = await showing(page([], [INVITATION]));
    const confirm = () => document.querySelector('[data-testid="decline-dialog-submit"]');
    expect(confirm()).toBeNull();
    await s.testid('launch-decline').trigger('click');
    await flush();
    expect(confirm()).not.toBeNull();
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
