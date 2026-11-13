// «Confirm it's you» (ReauthModal): the dialog a command opens when the server wants a recent sign-in. With a
// password, the password (allauth.headless `auth/reauthenticate`); with the authenticator, its code
// (`auth/2fa/reauthenticate`); an account that only signs in with Google signs in with Google again (a form POST
// to allauth.headless's provider redirect that comes back to this page).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Window } from 'happy-dom';
import { parse } from 'vue/compiler-sfc';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { fakeAllauth, ok, rejected } from '../__tests__/allauth-server';
import { flush, ionProps, mountPanel, typeInto } from '../__tests__/mount-panel';
import type { ReauthRequest } from '../reauth';
import ReauthModal from './ReauthModal.vue';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.cookie = 'csrftoken=; max-age=0';
});

async function setup(request: ReauthRequest, path = '/dashboard/account/api-keys') {
  const asked = ref<ReauthRequest | null>(request);
  const confirmed = vi.fn(() => (asked.value = null));
  const cancelled = vi.fn(() => (asked.value = null));
  const Host = { render: () => h(ReauthModal, { request: asked.value, onConfirmed: confirmed, onCancel: cancelled }) };
  const mounted = await mountPanel(Host, { path });
  await flush();
  return { ...mounted, asked, confirmed, cancelled };
}

describe('ReauthModal', () => {
  it('asks for the password, as a dialog named after what it asks', async () => {
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    expect(s.q('reauth-modal')?.getAttribute('aria-label')).toBe("Confirm it's you");
    expect(s.q('reauth-modal')?.textContent).toContain('enter your password again');
    expect(ionProps(s.q('reauth-password'), 'type', 'mode', 'fill', 'autocomplete')).toEqual({
      type: 'password',
      mode: 'md',
      fill: 'outline',
      autocomplete: 'current-password',
    });
    expect(s.q('reauth-use-code')).toBeNull();
    expect(s.q('reauth-google')).toBeNull();
  });

  it('confirms with the password and tells the page, which runs its command again', async () => {
    const server = fakeAllauth({ 'POST /auth/reauthenticate': ok({}) });
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    await typeInto(s.q('reauth-password'), 'owner-secret');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(server.callsTo('POST /auth/reauthenticate').map((call) => call.body)).toEqual([{ password: 'owner-secret' }]);
    expect(s.confirmed).toHaveBeenCalledTimes(1);
  });

  it('keeps a wrong password in the dialog, said under the field', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': rejected('Incorrect password.', 'password') });
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    await typeInto(s.q('reauth-password'), 'nope');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(ionProps(s.q('reauth-password'), 'errorText')).toEqual({ errorText: 'Incorrect password.' });
    expect(s.confirmed).not.toHaveBeenCalled();
  });

  it('does not send an empty password', async () => {
    const server = fakeAllauth({});
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    expect(ionProps(s.q('reauth-modal-submit'), 'disabled')).toEqual({ disabled: true });
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(server.calls).toEqual([]);
  });

  it('offers the authenticator code when the account has one, and confirms with it', async () => {
    const server = fakeAllauth({ 'POST /auth/2fa/reauthenticate': ok({}) });
    const s = await setup({ flows: ['reauthenticate', 'mfa_reauthenticate'], providers: [] });
    s.q('reauth-use-code')?.click();
    await flush();
    expect(s.q('reauth-password')).toBeNull();
    await typeInto(s.q('code'), '123456');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(server.callsTo('POST /auth/2fa/reauthenticate').map((call) => call.body)).toEqual([{ code: '123456' }]);
    expect(s.confirmed).toHaveBeenCalledTimes(1);
  });

  it('sends an account that only signs in with Google to Google, back to this page', async () => {
    document.cookie = 'csrftoken=tok123';
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => undefined);
    const s = await setup({ flows: ['provider_redirect'], providers: ['google'] }, '/dashboard/account/api-keys');
    expect(s.q('reauth-password')).toBeNull();
    expect(s.q('reauth-modal')?.textContent).toContain('signing in with Google again');
    expect(s.q('reauth-modal-submit')?.textContent).toContain('Continue with Google');
    s.q('reauth-modal-submit')?.click();
    await flush();
    const form = s.q('reauth-google') as unknown as HTMLFormElement;
    expect(form.getAttribute('action')).toBe('/_allauth/browser/v1/auth/provider/redirect');
    expect(form.getAttribute('method')).toBe('post');
    expect(Object.fromEntries(new FormData(form).entries())).toEqual({
      provider: 'google',
      process: 'login',
      callback_url: '/dashboard/account/api-keys',
      csrfmiddlewaretoken: 'tok123',
    });
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('offers Google as the other way when the account has a password too', async () => {
    const s = await setup({ flows: ['reauthenticate', 'provider_redirect'], providers: ['google'] });
    expect(s.q('reauth-password')).not.toBeNull();
    s.q('reauth-use-google')?.click();
    await flush();
    expect(s.q('reauth-password')).toBeNull();
    expect(s.q('reauth-modal-submit')?.textContent).toContain('Continue with Google');
  });

  it('closing it gives up, and says so to the page', async () => {
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    s.q('reauth-modal-cancel')?.click();
    await flush();
    expect(s.cancelled).toHaveBeenCalledTimes(1);
    expect(s.confirmed).not.toHaveBeenCalled();
  });

  it('speaks Spanish', async () => {
    const asked = ref<ReauthRequest | null>({ flows: ['reauthenticate'], providers: [] });
    const Host = { render: () => h(ReauthModal, { request: asked.value }) };
    const s = await mountPanel(Host, { locale: 'es' });
    await flush();
    expect(s.q('reauth-modal')?.getAttribute('aria-label')).toBe('Confirma que eres tú');
  });
});

// It opens over the dialog that asked for it (a new key, ACCOUNTS-F31; a new email, ACCOUNTS-F21), and Ionic drops the
// backdrop and the shadow of a modal opened over another one (`ion-modal.modal-default.show-modal ~
// ion-modal.modal-default`, its core.css). FormModal keeps both since ERPlora/ui#112, 0.4 in light and 0.6 in dark. A rule
// of this dialog's own said 0.4 in dark too, as specific as FormModal's, so which one won hung on the order the bundle
// loaded them (saas#379). One rule, FormModal's.
describe('ReauthModal over the dialog that asked for it (saas#379)', () => {
  const HERE = dirname(fileURLToPath(import.meta.url));
  /** The rules of a single-file component that reach outside it (its `<style>` blocks without `scoped`). */
  const unscoped = (file: string): string =>
    parse(readFileSync(file, 'utf8'))
      .descriptor.styles.filter((style) => !style.scoped)
      .map((style) => style.content)
      .join('\n');
  const FORM_MODAL = unscoped(join(HERE, '../../../packages/ui/src/components/FormModal/FormModal.vue'));
  const OWN = unscoped(join(HERE, 'ReauthModal.vue'));
  const IONIC = readFileSync(join(HERE, '../../../node_modules/@ionic/vue/css/core.css'), 'utf8');
  const SHADOW = '0 18px 50px rgba(17, 24, 39, 0.18)';

  /** The dialog as the panel renders it, presented after the open one that asked for it, read with FormModal's
   *  stylesheet, then its own, then Ionic's: what wins has to win by what it says, not by coming last. */
  async function over(dark: boolean) {
    const s = await setup({ flows: ['reauthenticate'], providers: [] });
    const rendered = s.q('reauth-modal');
    if (!rendered) throw new Error('the dialog is not there');
    const win = new Window({ width: 1280, height: 800 });
    if (dark) win.document.documentElement.classList.add('ion-palette-dark');
    win.document.head.innerHTML = `<style>:root { --ep-shadow-modal: ${SHADOW}; }</style><style>${FORM_MODAL}</style><style>${OWN}</style><style>${IONIC}</style>`;
    win.document.body.innerHTML = `<ion-app>
      <ion-modal class="ios modal-default show-modal" data-testid="asked"></ion-modal>
      <ion-modal class="${rendered.className} ios modal-default show-modal" data-size="${rendered.dataset.size}" data-testid="front"></ion-modal>
    </ion-app>`;
    const front = win.document.querySelector('[data-testid=front]');
    if (!front) throw new Error('the dialog is not in the window');
    const style = win.getComputedStyle(front);
    const read = { backdrop: style.getPropertyValue('--backdrop-opacity'), shadow: style.getPropertyValue('--box-shadow') };
    await win.happyDOM.close();
    return read;
  }

  it('dims the dialog behind and keeps its shadow, as FormModal does over any window', async () => {
    expect(await over(false)).toEqual({ backdrop: '0.4', shadow: SHADOW });
  });

  it('dark: the dialog behind as deep as FormModal says, 0.6', async () => {
    expect(await over(true)).toEqual({ backdrop: '0.6', shadow: SHADOW });
  });

  it('has no rule of its own for its window: FormModal is the only one', () => {
    expect(OWN).not.toMatch(/ion-modal/);
  });
});
