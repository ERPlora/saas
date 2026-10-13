// «Confirm it's you» (`/reauthenticate`): the step before changing the sign-in security, when
// allauth asks for a recent login (`reauthentication_required`). The pages of the templates
// `account/reauthenticate.html` (password) and `mfa/reauthenticate.html` (authenticator code or
// recovery code) in one card: `?method=totp|password` picks the first one, and each one offers the
// other when allauth listed it (`?flows=`). Confirmed → back to `next` (a path of this site, `/2fa`
// by default) with a full page load, as the sign-in leaves: `next` can be a Django route (the
// backend sends `/hub-login/` here when the jump to a hub needs a recent login).
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { anonymous, fakeAllauth, held, offline, rejected, signedIn } from '../__tests__/allauth-server';
import { mountAccountPage, SIGNED_IN } from '../__tests__/mount-account-page';
import ReauthenticatePage from './ReauthenticatePage.vue';

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

const BOTH = 'reauthenticate,mfa_reauthenticate';

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function mountPage(query = '', locale: 'en' | 'es' = 'en') {
  const mounted = await mountAccountPage(ReauthenticatePage, {
    path: `/reauthenticate${query}`,
    session: SIGNED_IN,
    locale,
  });
  const { wrapper } = mounted;
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid);
  async function confirm(value: string) {
    await wrapper.getComponent(IonInput).setValue(value);
    await wrapper.get('form[data-testid="reauth-form"]').trigger('submit');
    await flushPromises();
  }
  async function click(testid: string) {
    await button(testid)!.trigger('click');
    await flushPromises();
  }
  return { ...mounted, button, confirm, click };
}

describe('ReauthenticatePage: with the password (account/reauthenticate.html)', () => {
  it('asks for the password under «Account security», with the lock of the template', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage();
    expect(wrapper.get('.biz-sub').text()).toBe('Account security');
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:lock'));
    expect(wrapper.get('h2.auth-title').text()).toBe("Confirm it's you");
    expect(wrapper.get('[data-testid="reauth-lead"]').text()).toBe('Enter your password to change your sign-in security.');
    const input = wrapper.getComponent(IonInput);
    expect([input.attributes('mode'), input.props('type'), input.props('label'), input.props('fill')]).toEqual([
      'md',
      'password',
      'Password',
      'outline',
    ]);
    expect([input.props('labelPlacement'), input.props('placeholder'), input.props('autocomplete')]).toEqual([
      'floating',
      '••••••••••',
      'current-password',
    ]);
    expect(wrapper.find('ion-input-password-toggle[slot="end"]').exists()).toBe(true);
    const submit = button('reauth-submit')!;
    expect([submit.props('type'), submit.props('color'), submit.props('size'), submit.text()]).toEqual([
      'submit',
      'primary',
      'large',
      'Confirm',
    ]);
    expect(document.title).toBe("Confirm it's you - ERPlora Cloud");
  });

  it('links «Back to settings» to the 2FA settings', async () => {
    fakeAllauth();
    const { wrapper } = await mountPage();
    const back = wrapper.get('.foot a');
    expect([back.text(), back.attributes('href')]).toEqual(['Back to settings', '/2fa']);
  });

  it('posts the password and leaves for next, a Django route too (the jump to a hub)', async () => {
    const server = fakeAllauth({ 'POST /auth/reauthenticate': signedIn });
    const { confirm } = await mountPage('?next=%2Fhub-login%2F%3Fhub%3Da');
    await confirm('owner');
    expect(server.callsTo('POST /auth/reauthenticate').map((c) => c.body)).toEqual([{ password: 'owner' }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('leaves for /2fa without a next, or with one that leaves the site', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': signedIn });
    const plain = await mountPage();
    await plain.confirm('owner');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/2fa');
    assign.mockClear();
    const evil = await mountPage(`?next=${encodeURIComponent('//evil.example.com')}`);
    await evil.confirm('owner');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/2fa');
  });

  it('paints a wrong password under its input, marks it invalid and stays', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': rejected('Incorrect password.', 'password', 'incorrect_password') });
    const { wrapper, confirm, router } = await mountPage();
    await confirm('wrong');
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect password.');
    expect(input.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
    expect(router.currentRoute.value.path).toBe('/reauthenticate');
    expect(assign).not.toHaveBeenCalled();
  });

  it('paints an error of the whole form above the input', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': rejected('Too many attempts.', undefined, 'too_many_requests') });
    const { wrapper, confirm } = await mountPage();
    await confirm('owner');
    expect(wrapper.get('.non-field-error').text()).toBe('Too many attempts.');
  });

  it('says something went wrong when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': offline });
    const { wrapper, confirm } = await mountPage('', 'es');
    await confirm('owner');
    expect(wrapper.get('.non-field-error').text()).toBe('Algo ha ido mal. Inténtalo de nuevo.');
  });

  it('disables «Confirm» while the password is on its way', async () => {
    const answer = held(signedIn);
    fakeAllauth({ 'POST /auth/reauthenticate': answer.answer });
    const { wrapper, confirm } = await mountPage();
    await confirm('owner');
    expect((wrapper.get('[data-testid="reauth-submit"]').element as Control).disabled).toBe(true);
    answer.release();
    await flushPromises();
  });

  it('sends a session that ended to the sign-in, coming back here afterwards', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': anonymous });
    const { confirm, router } = await mountPage('?next=%2F2fa');
    await confirm('owner');
    expect(router.currentRoute.value.path).toBe('/login');
    expect(router.currentRoute.value.query).toEqual({ next: '/reauthenticate?next=%2F2fa' });
    expect(assign).not.toHaveBeenCalled();
  });
});

describe('ReauthenticatePage: with the authenticator (mfa/reauthenticate.html)', () => {
  it('asks for a code with ?method=totp, with the shield of the template', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage('?method=totp');
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:shield-check'));
    expect(wrapper.get('h2.auth-title').text()).toBe("Confirm it's you");
    expect(wrapper.get('[data-testid="reauth-lead"]').text()).toBe(
      'Enter the 6-digit code from your authenticator app, or one of your recovery codes.',
    );
    const input = wrapper.getComponent(IonInput);
    expect([input.props('label'), input.props('autocomplete')]).toEqual(['Verification code', 'one-time-code']);
    expect(button('reauth-submit')!.text()).toBe('Confirm');
  });

  it('posts the code and leaves for next', async () => {
    const server = fakeAllauth({ 'POST /auth/2fa/reauthenticate': signedIn });
    const { confirm } = await mountPage('?method=totp&next=%2Fhub-login%2F%3Fhub%3Da');
    await confirm('123456');
    expect(server.callsTo('POST /auth/2fa/reauthenticate').map((c) => c.body)).toEqual([{ code: '123456' }]);
    expect(server.callsTo('POST /auth/reauthenticate')).toHaveLength(0);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('paints a wrong code under the input (400 incorrect_code on `code`) and stays', async () => {
    fakeAllauth({ 'POST /auth/2fa/reauthenticate': rejected('Incorrect code.', 'code', 'incorrect_code') });
    const { wrapper, confirm } = await mountPage('?method=totp');
    await confirm('000000');
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toContain('ion-invalid');
    expect(assign).not.toHaveBeenCalled();
  });

  it('speaks Spanish with the translations of the templates', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage(`?method=totp&flows=${BOTH}`, 'es');
    expect(wrapper.get('.biz-sub').text()).toBe('Seguridad de la cuenta');
    expect(wrapper.get('h2.auth-title').text()).toBe('Confirma que eres tú');
    expect(wrapper.get('[data-testid="reauth-alternative-lead"]').text()).toBe('¿No puedes usar tu autenticador?');
    expect(button('reauth-use-password')!.text()).toBe('Usa tu contraseña');
    expect(wrapper.get('.foot a').text()).toBe('Volver a configuración');
  });
});

describe('ReauthenticatePage: the other way to confirm', () => {
  it('offers the authenticator from the password, and the password back, when allauth lists both', async () => {
    fakeAllauth();
    const { wrapper, button, click } = await mountPage(`?flows=${BOTH}`);
    expect(wrapper.get('[data-testid="reauth-alternative-lead"]').text()).toBe("Can't use your password?");
    const useApp = button('reauth-use-authenticator')!;
    expect([useApp.props('fill'), useApp.props('expand'), useApp.text()]).toEqual(['outline', 'block', 'Use your authenticator app']);
    await click('reauth-use-authenticator');
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Verification code');
    expect(wrapper.get('[data-testid="reauth-alternative-lead"]').text()).toBe("Can't use your authenticator?");
    await click('reauth-use-password');
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Password');
  });

  it('clears the errors of one way when switching to the other', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': rejected('Too many attempts.') });
    const { wrapper, confirm, click } = await mountPage(`?flows=${BOTH}`);
    await confirm('owner');
    expect(wrapper.find('.non-field-error').exists()).toBe(true);
    await click('reauth-use-authenticator');
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
  });

  it('offers only what allauth lists: no authenticator for an account without one', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage('?flows=reauthenticate');
    expect(button('reauth-use-authenticator')).toBeUndefined();
    expect(wrapper.find('[data-testid="reauth-alternative-lead"]').exists()).toBe(false);
  });

  it('offers no password to an account without one (signed up with Google)', async () => {
    fakeAllauth();
    const { button } = await mountPage('?method=totp&flows=mfa_reauthenticate');
    expect(button('reauth-use-password')).toBeUndefined();
  });

  it('offers both ways when it does not know what allauth lists', async () => {
    fakeAllauth();
    const { button } = await mountPage();
    expect(button('reauth-use-authenticator')).toBeDefined();
    const fromCode = await mountPage('?method=totp');
    expect(fromCode.button('reauth-use-password')).toBeDefined();
  });

  it('starts with the code when allauth lists only the authenticator (the jump to a hub)', async () => {
    fakeAllauth();
    const { wrapper, button } = await mountPage('?flows=mfa_reauthenticate&next=%2Fhub-login%2F%3Fhub%3Da');
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Verification code');
    expect(button('reauth-use-password')).toBeUndefined();
    expect(wrapper.find('[data-testid="reauth-alternative-lead"]').exists()).toBe(false);
  });

  it('never starts with a way allauth does not list, whatever ?method says', async () => {
    fakeAllauth();
    const code = await mountPage('?method=password&flows=mfa_reauthenticate');
    expect(code.wrapper.getComponent(IonInput).props('label')).toBe('Verification code');
    const password = await mountPage('?method=totp&flows=reauthenticate');
    expect(password.wrapper.getComponent(IonInput).props('label')).toBe('Password');
    expect(password.button('reauth-use-authenticator')).toBeUndefined();
  });
});
