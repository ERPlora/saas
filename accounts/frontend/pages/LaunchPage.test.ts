// The launcher (`/launch`), the entry of erplora.com, ported from ERPlora/saas `accounts/launch.html`
// and the view `handoff.launch`: it reads the account's hubs (`accounts.hub.list`) and, with ONE, jumps
// straight to it; with several, lists them (the jump of each one is a Django page, `/hub-login/`,
// so it is a full navigation); with none, says so. «Sign Out» posts Django's logout form.
import { ApiError } from '@erplora/ui/sdk';
import { IonButton, IonItem, IonList } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { mountAccountPage, SIGNED_IN } from '../__tests__/mount-account-page';
import LaunchPage from './LaunchPage.vue';

const A = { slug: 'a', host: 'a.localhost:8000', url: '/hub-login/?hub=a&next=/' };
const B = { slug: 'b', host: 'b.localhost:8000', url: '/hub-login/?hub=b&next=/' };

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const answering = (hubs: unknown[]) => vi.fn(() => Promise.resolve({ hubs }));

function mountLaunch(options: { call?: ReturnType<typeof vi.fn>; locale?: 'en' | 'es'; path?: string } = {}) {
  return mountAccountPage(LaunchPage, { path: '/launch', session: SIGNED_IN, ...options });
}

describe('LaunchPage: the page of the template', () => {
  it('asks the server for the hubs of the account (accounts.hub.list), once', async () => {
    const { call } = await mountLaunch({ call: answering([A, B]) });
    expect(call).toHaveBeenCalledExactlyOnceWith('accounts.hub.list', {});
  });

  it('says «Choose a business» under the logo and in the tab, as the template did', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A, B]) });
    expect(wrapper.get('.biz-sub').text()).toBe('Choose a business');
    expect(document.title).toBe('Choose a business - ERPlora Cloud');
  });

  it('shows a spinner until the hubs arrive', async () => {
    const { wrapper } = await mountLaunch();
    expect(wrapper.find('[data-testid="launch-loading"] ion-spinner').exists()).toBe(true);
    expect(wrapper.find('[data-testid="launch-hubs"]').exists()).toBe(false);
  });

  it('speaks Spanish with the translations of the template', async () => {
    const { wrapper } = await mountLaunch({ call: answering([]), locale: 'es' });
    expect(wrapper.get('.biz-sub').text()).toBe('Elige un negocio');
    expect(wrapper.get('[data-testid="launch-empty"]').text()).toContain(
      'Tu cuenta aún no pertenece a ningún negocio. Pide a quien gestione uno que te invite.',
    );
    expect(wrapper.get('[data-testid="launch-logout"]').text()).toBe('Cerrar Sesión');
  });
});

describe('LaunchPage: the hubs of the account', () => {
  it('with no hub, says so (empty state) and goes nowhere', async () => {
    const { wrapper } = await mountLaunch({ call: answering([]) });
    const empty = wrapper.get('[data-testid="launch-empty"]');
    expect(empty.text()).toContain("Your account doesn't belong to any business yet. Ask whoever manages one to invite you.");
    expect(wrapper.find('[data-testid="launch-hubs"]').exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('with ONE hub, jumps straight to it (a full navigation: /hub-login/ is a Django page)', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A]) });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a&next=/');
    expect(wrapper.get('[data-testid="launch-loading"]').text()).toContain('Opening your business…');
    expect(wrapper.find('[data-testid="launch-hubs"]').exists()).toBe(false);
  });

  it('with several, lists them by slug and host, each one a link to its jump', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A, B]) });
    const items = wrapper.findAllComponents(IonItem);
    expect(items.map((i) => [i.find('h2').text(), i.find('p').text(), i.props('href'), i.props('detail')])).toEqual([
      ['a', 'a.localhost:8000', '/hub-login/?hub=a&next=/', true],
      ['b', 'b.localhost:8000', '/hub-login/?hub=b&next=/', true],
    ]);
    // Ionic's props are DOM properties: read through the component.
    expect(wrapper.getComponent(IonList).props('lines')).toBe('full');
    expect(assign).not.toHaveBeenCalled();
  });
});

describe('LaunchPage: the notice of the 2FA settings (`?notice=mfa_unavailable`)', () => {
  it('says 2FA is not available yet, as a status, above the hubs', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A, B]), path: '/launch?notice=mfa_unavailable' });
    // InlineFeedback announces its box as a status (`role="status"` inside its root).
    const notice = wrapper.get('[data-testid="launch-notice"] [role="status"]');
    expect(notice.text()).toContain('Two-factor authentication is not available on this account yet.');
    expect(wrapper.findAllComponents(IonItem)).toHaveLength(2);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A, B]), path: '/launch?notice=mfa_unavailable', locale: 'es' });
    expect(wrapper.get('[data-testid="launch-notice"]').text()).toContain(
      'La autenticación en dos pasos aún no está disponible en esta cuenta.',
    );
  });

  it('keeps a single hub on screen instead of jumping to it, or the notice would never be read', async () => {
    const { wrapper } = await mountLaunch({ call: answering([A]), path: '/launch?notice=mfa_unavailable' });
    expect(assign).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="launch-notice"]').exists()).toBe(true);
    expect(wrapper.findAllComponents(IonItem)).toHaveLength(1);
  });

  it('shows nothing for an unknown notice, nor without one', async () => {
    const unknown = await mountLaunch({ call: answering([A, B]), path: '/launch?notice=other' });
    expect(unknown.wrapper.find('[data-testid="launch-notice"]').exists()).toBe(false);
    const none = await mountLaunch({ call: answering([A, B]) });
    expect(none.wrapper.find('[data-testid="launch-notice"]').exists()).toBe(false);
  });
});

describe('LaunchPage: when the hubs cannot be read', () => {
  it('says so and tries again on demand', async () => {
    const call = vi.fn().mockRejectedValueOnce(new ApiError(0, 'network_error', 'Network error'));
    call.mockResolvedValueOnce({ hubs: [A, B] });
    const { wrapper } = await mountLaunch({ call });
    const error = wrapper.get('[data-testid="launch-error"]');
    expect(error.text()).toContain('We could not load your businesses. Please try again.');
    await error.findComponent(IonButton).trigger('click');
    await flushPromises();
    expect(call).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[data-testid="launch-error"]').exists()).toBe(false);
    expect(wrapper.findAllComponents(IonItem)).toHaveLength(2);
  });

  it('sends a session that ended meanwhile to the sign-in, coming back here', async () => {
    const call = vi.fn().mockRejectedValue(new ApiError(401, 'unauthorized', 'Authentication required'));
    await mountLaunch({ call });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/login?next=%2Flaunch');
  });
});

describe('LaunchPage: «Sign Out»', () => {
  it("posts Django's logout form with the CSRF token, and lands on the sign-in", async () => {
    const { wrapper } = await mountLaunch({ call: answering([A, B]) });
    const form = wrapper.get('form[data-testid="launch-logout"]');
    expect([form.attributes('method'), form.attributes('action')]).toEqual(['post', '/accounts/logout/']);
    const hidden = Object.fromEntries(
      form.findAll('input[type="hidden"]').map((i) => [i.attributes('name'), (i.element as HTMLInputElement).value]),
    );
    expect(hidden).toEqual({ csrfmiddlewaretoken: 'tok-123', next: '/login' });
    const button = form.findComponent(IonButton);
    expect([button.props('type'), button.props('fill'), button.props('expand'), button.text()]).toEqual([
      'submit',
      'clear',
      'block',
      'Sign Out',
    ]);
  });
});
