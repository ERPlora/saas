// The «Google» row of Account → Security, «Sign-in» (mockups `account.html` «security»; U-63): the Google account the
// person can sign in with (allauth.headless `account/providers`) and «Disconnect», confirmed; or «Connect», the
// provider's handshake as a form post (`process=connect`) that comes back here. Google being the only way in (no
// password) keeps «Disconnect» off and says why. Without Google on the server and nothing linked, no row.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { type Answer, fakeAllauth, ok, reauthenticationRequired, rejected } from '../__tests__/allauth-server';
import { flush, ionProps, mountPanel, typeInto } from '../__tests__/mount-panel';
import ConnectedAccountsRow from './ConnectedAccountsRow.vue';

const GOOGLE = { uid: 'g-1', display: 'laura.martin@gmail.com', provider: { id: 'google', name: 'Google', flows: ['provider_redirect'] } };

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.cookie = 'csrftoken=; max-age=0';
});

async function setup(answers: Record<string, Answer | Answer[]>, props = { hasPassword: true }, config: Record<string, unknown> = {}) {
  const server = fakeAllauth(answers);
  const s = await mountPanel(ConnectedAccountsRow, { props, config });
  await flush();
  return { ...s, server };
}

describe('ConnectedAccountsRow', () => {
  it('says the Google account the person can sign in with', async () => {
    const s = await setup({ 'GET /account/providers': ok([GOOGLE]) });
    expect(s.q('google-row')?.textContent).toContain('You can sign in with laura.martin@gmail.com.');
    expect(ionProps(s.q('google-disconnect'), 'disabled')).toEqual({ disabled: false });
    expect(s.q('google-connect')).toBeNull();
  });

  it('disconnects it after a confirmation that names it', async () => {
    const s = await setup({ 'GET /account/providers': ok([GOOGLE]), 'DELETE /account/providers': ok([]) });
    s.q('google-disconnect')?.click();
    await flush();
    expect(s.q('disconnect-google')?.textContent).toContain('You will no longer sign in with laura.martin@gmail.com');
    s.q('disconnect-google-submit')?.click();
    await flush();
    expect(s.server.callsTo('DELETE /account/providers').map((call) => call.body)).toEqual([{ provider: 'google', account: 'g-1' }]);
    expect(toastSuccess).toHaveBeenCalledWith('Google disconnected');
    expect(s.q('google-row')?.textContent).toContain('Sign in with your Google account too.');
  });

  it('keeps «Disconnect» off when Google is the only way in, and says why', async () => {
    const s = await setup({ 'GET /account/providers': ok([GOOGLE]) }, { hasPassword: false });
    expect(ionProps(s.q('google-disconnect'), 'disabled')).toEqual({ disabled: true });
    expect(s.q('google-row')?.textContent).toContain('It is your only way to sign in: create a password first.');
  });

  it('keeps the server’s refusal in the dialog', async () => {
    const s = await setup({
      'GET /account/providers': ok([GOOGLE]),
      'DELETE /account/providers': rejected('Your account has no password set up.', undefined, 'no_password'),
    });
    s.q('google-disconnect')?.click();
    await flush();
    s.q('disconnect-google-submit')?.click();
    await flush();
    expect(s.q('disconnect-google-error')?.textContent).toContain('Your account has no password set up.');
  });

  it('asks «Confirm it’s you» when allauth wants it, then disconnects', async () => {
    const s = await setup({
      'GET /account/providers': ok([GOOGLE]),
      'DELETE /account/providers': [reauthenticationRequired(['reauthenticate']), ok([])],
      'POST /auth/reauthenticate': ok({}),
    });
    s.q('google-disconnect')?.click();
    await flush();
    s.q('disconnect-google-submit')?.click();
    await flush();
    expect(s.q('disconnect-google-error')).toBeNull();
    await typeInto(s.q('reauth-password'), 'owner-secret');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(s.server.callsTo('DELETE /account/providers')).toHaveLength(2);
    expect(toastSuccess).toHaveBeenCalledWith('Google disconnected');
  });

  it('connects Google with the provider’s handshake, back to Security', async () => {
    document.cookie = 'csrftoken=tok123';
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => undefined);
    const s = await setup({ 'GET /account/providers': ok([]) });
    expect(s.q('google-row')?.textContent).toContain('Sign in with your Google account too.');
    s.q('google-connect')?.click();
    await flush();
    const form = s.q('google-connect-form') as unknown as HTMLFormElement;
    expect(form.getAttribute('action')).toBe('/_allauth/browser/v1/auth/provider/redirect');
    expect(form.getAttribute('method')).toBe('post');
    expect(Object.fromEntries(new FormData(form).entries())).toEqual({
      provider: 'google',
      callback_url: '/account/security',
      process: 'connect',
      csrfmiddlewaretoken: 'tok123',
    });
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('is not painted without Google on the server and nothing linked', async () => {
    const s = await setup({ 'GET /account/providers': ok([]) }, { hasPassword: true }, { googleEnabled: false });
    expect(s.q('google-row')).toBeNull();
  });
});
