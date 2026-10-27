// «Sign out of erplora.com?» (`/logout`, ACCOUNTS-F09): where the Hub's «Sign out» lands on a device without the PIN
// pad (BASE-F61), as the old SaaS's `account/logout.html` did. Opening the page closes nothing (a loose link never signs
// anybody out); «Sign out» ends the session with allauth.headless (`DELETE …/auth/session`) and loads the launcher, as
// the user menu does; «Stay signed in» goes to the launcher with the session as it was. Signed out, the launcher at once.
import { type SessionMe } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { anonymous, fakeAllauth, held, offline, signedIn } from '../__tests__/allauth-server';
import { ANONYMOUS, mountAccountPage } from '../__tests__/mount-account-page';
import SignOutPage from './SignOutPage.vue';

type Control = HTMLElement & { disabled?: boolean };

const ANA: SessionMe = { ...ANONYMOUS, user: { id: 'u1', label: 'Ana López', email: 'ana@example.com' } };

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.title = '';
});

async function mountPage(options: { session?: SessionMe; locale?: 'en' | 'es' } = {}) {
  const mounted = await mountAccountPage(SignOutPage, { path: '/logout', session: options.session ?? ANA, locale: options.locale });
  const { wrapper } = mounted;
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid);
  async function click(testid: string) {
    await button(testid)!.trigger('click');
    await flushPromises();
  }
  const disabled = (testid: string) => (wrapper.get(`[data-testid="${testid}"]`).element as Control).disabled;
  return { ...mounted, button, click, disabled };
}

describe('SignOutPage: the question', () => {
  it('asks whether to close erplora.com’s session, naming the account, and closes nothing by being opened', async () => {
    const server = fakeAllauth({ 'DELETE /auth/session': anonymous });
    const { wrapper, button, router } = await mountPage();
    expect(wrapper.get('.biz-sub').text()).toBe('Global panel');
    expect(wrapper.get('h2.auth-title').text()).toBe('Sign out of erplora.com?');
    expect(wrapper.get('[data-testid="sign-out-lead"]').text()).toBe(
      'You are still signed in to erplora.com in this browser as ana@example.com.',
    );
    expect(button('sign-out-confirm')!.text()).toBe('Sign out');
    expect(button('sign-out-stay')!.text()).toBe('Stay signed in');
    expect(server.calls).toEqual([]);
    expect(assign).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/logout');
    expect(document.title).toBe('Sign out of erplora.com? - ERPlora Cloud');
  });

  it('names the account by its label when it has no address', async () => {
    fakeAllauth();
    const { wrapper } = await mountPage({ session: { ...ANONYMOUS, user: { id: 'u1', label: 'Ana López' } } });
    expect(wrapper.get('[data-testid="sign-out-lead"]').text()).toBe(
      'You are still signed in to erplora.com in this browser as Ana López.',
    );
  });

  it('asks in Spanish', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage({ locale: 'es' });
    expect(wrapper.get('.biz-sub').text()).toBe('Panel global');
    expect(wrapper.get('h2.auth-title').text()).toBe('¿Cerrar la sesión de erplora.com?');
    expect(wrapper.get('[data-testid="sign-out-lead"]').text()).toBe(
      'Sigues conectado a erplora.com en este navegador como ana@example.com.',
    );
    expect(button('sign-out-confirm')!.text()).toBe('Cerrar sesión');
    expect(button('sign-out-stay')!.text()).toBe('Seguir conectado');
  });

  it('sends a visitor without a session to the launcher at once: there is nothing to close', async () => {
    const server = fakeAllauth({ 'DELETE /auth/session': anonymous });
    const { router } = await mountPage({ session: ANONYMOUS });
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(server.calls).toEqual([]);
  });
});

describe('SignOutPage: «Sign out»', () => {
  it('ends erplora.com’s session, then loads the launcher', async () => {
    const server = fakeAllauth({ 'DELETE /auth/session': anonymous });
    const { click } = await mountPage();
    await click('sign-out-confirm');
    expect(server.callsTo('DELETE /auth/session')).toHaveLength(1);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('disables both buttons while the request is on its way', async () => {
    const answer = held(anonymous);
    fakeAllauth({ 'DELETE /auth/session': answer.answer });
    const { click, disabled } = await mountPage();
    await click('sign-out-confirm');
    expect(['sign-out-confirm', 'sign-out-stay'].map(disabled)).toEqual([true, true]);
    answer.release();
    await flushPromises();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it.each([
    ['the request fails', offline],
    ['the session is still open after it', signedIn],
  ])('stays and says so when %s', async (_case, answer) => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeAllauth({ 'DELETE /auth/session': answer });
    const { wrapper, click, disabled, router } = await mountPage();
    await click('sign-out-confirm');
    expect(assign).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/logout');
    expect(wrapper.get('[role="alert"]').text()).toBe('Could not sign out. Try again.');
    expect(['sign-out-confirm', 'sign-out-stay'].map(disabled)).toEqual([false, false]);
  });

  it('says it in Spanish too', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeAllauth({ 'DELETE /auth/session': offline });
    const { wrapper, click } = await mountPage({ locale: 'es' });
    await click('sign-out-confirm');
    expect(wrapper.get('[role="alert"]').text()).toBe('No se ha podido cerrar la sesión. Inténtalo de nuevo.');
  });
});

describe('SignOutPage: «Stay signed in»', () => {
  it('goes to the launcher with the session as it was, replacing this page in the history', async () => {
    const server = fakeAllauth({ 'DELETE /auth/session': anonymous });
    const { click, router } = await mountPage();
    const replace = vi.spyOn(router, 'replace');
    await click('sign-out-stay');
    expect(replace).toHaveBeenCalledExactlyOnceWith('/launch');
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(server.calls).toEqual([]);
    expect(assign).not.toHaveBeenCalled();
  });
});
