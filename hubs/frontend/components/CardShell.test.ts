// The centred-card frame of the launcher and the invitation (mockups `launch.html`, `invitation.html`;
// old SaaS `_shell_styles.html`): no menu, the ERPlora lockup INSIDE the card above the title, the
// state's icon and title (the page's heading), a lead under it, the content, and under the card
// «Signed in as … · Sign out» (allauth.headless ends the session, then the sign-in, as the user menu does).
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { ANONYMOUS, flush, mountHubs } from '../__tests__/mount-hubs';
import CardShell from './CardShell.vue';

const SESSION = '/_allauth/browser/v1/auth/session';
const signedOut = () =>
  Response.json({ status: 401, data: { flows: [{ id: 'login' }] }, meta: { is_authenticated: false } }, { status: 401 });

let fetchMock: ReturnType<typeof vi.fn>;
let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(signedOut()));
  vi.stubGlobal('fetch', fetchMock);
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

async function mountShell(options: Parameters<typeof mountHubs>[1] = {}) {
  const Host = {
    render: () =>
      h(CardShell, { icon: 'ion:storefront-outline', title: 'Create your business', lead: 'Free and no card.' }, () =>
        h('p', { 'data-testid': 'content' }, 'The form'),
      ),
  };
  return mountHubs(Host, options);
}

describe('CardShell', () => {
  it('paints the lockup inside the card, then the icon, the title as the heading and the lead', async () => {
    const { wrapper } = await mountShell();
    const card = wrapper.get('ion-card.shell-card');
    expect(card.get('[role="img"]').attributes('aria-label')).toBe('ERPlora');
    expect(card.get('.erp-wordmark').text()).toBe('ERPlora');
    const title = card.get('ion-card-title');
    expect(title.attributes('role')).toBe('heading');
    expect(title.attributes('aria-level')).toBe('1');
    expect(title.text()).toBe('Create your business');
    expect(card.get('.shell-lead').text()).toBe('Free and no card.');
    expect(card.get('[data-testid="content"]').text()).toBe('The form');
    // The lockup comes first, above the title (README §5).
    const html = card.html();
    expect(html.indexOf('erp-lockup')).toBeLessThan(html.indexOf('ion-card-title'));
  });

  it('has one main landmark, Ionic’s content (`role="main"`): the card’s frame is no second `main` inside it (audit 2 R-22)', async () => {
    const { wrapper } = await mountShell();
    expect(wrapper.find('.ion-page ion-content .shell-page').exists()).toBe(true);
    expect(wrapper.find('main').exists()).toBe(false);
  });

  it('says who is signed in and signs out through allauth.headless, back to the sign-in of the launcher', async () => {
    document.cookie = 'csrftoken=tok123';
    const { wrapper } = await mountShell();
    const account = wrapper.get('[data-testid="shell-account"]');
    expect(account.text()).toContain('Signed in as laura@example.com');
    const button = account.get('ion-button');
    expect(button.text()).toBe('Sign out');

    await button.trigger('click');
    await flush();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect([url, init.method]).toEqual([SESSION, 'DELETE']);
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBe('tok123');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('says so and stays when the session could not be ended', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const { wrapper } = await mountShell();

    await wrapper.get('[data-testid="shell-account"] ion-button').trigger('click');
    await flush();

    expect(assign).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Could not sign out. Try again.');
  });

  it('has no account line without a session', async () => {
    const { wrapper } = await mountShell({ session: ANONYMOUS });
    expect(wrapper.find('[data-testid="shell-account"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountShell({ locale: 'es' });
    expect(wrapper.get('[data-testid="shell-account"]').text()).toContain('Conectado como laura@example.com');
    expect(wrapper.get('[data-testid="shell-account"] ion-button').text()).toBe('Cerrar sesión');
  });
});
