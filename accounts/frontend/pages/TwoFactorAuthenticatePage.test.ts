// The second step of a sign-in with two-factor authentication (`/2fa/authenticate`), the page of
// the template `mfa/authenticate.html` over allauth.headless: the login waits in the session
// (`mfa_authenticate` pending) until a code from the authenticator app or a recovery code is right.
// Right → it leaves the SPA for `next` or the launcher, as the login does; «Back to sign in» ends
// the waiting login (allauth would resume the stage on the login page otherwise). «Trust this browser for 14 days»
// (ACCOUNTS-F05) answers allauth's `mfa_trust` stage that follows a right code, with the same «Verify».
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type Answer,
  anonymous,
  fakeAllauth,
  held,
  json,
  offline,
  pendingSecondFactor,
  pendingTrust,
  rejected,
  signedIn,
} from '../__tests__/allauth-server';
import { mountAccountPage } from '../__tests__/mount-account-page';
import { forgetRecaptcha, withRecaptcha } from '../__tests__/recaptcha-page';
import { choose } from '../__tests__/mount-panel';
import TwoFactorAuthenticatePage from './TwoFactorAuthenticatePage.vue';

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function mountPage(options: { path?: string; locale?: 'en' | 'es' } = {}) {
  const mounted = await mountAccountPage(TwoFactorAuthenticatePage, {
    path: options.path ?? '/2fa/authenticate',
    locale: options.locale,
  });
  const { wrapper } = mounted;
  async function verify(code = '123456', options: { trust?: boolean } = {}) {
    if (options.trust) await choose(wrapper.getComponent(IonCheckbox).element, { checked: true });
    await wrapper.getComponent(IonInput).setValue(code);
    await wrapper.get('form[data-testid="mfa-form"]').trigger('submit');
    await flushPromises();
  }
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid)!;
  return { ...mounted, verify, button };
}

describe('TwoFactorAuthenticatePage: the page of the template', () => {
  it('asks for the code under «Two-factor authentication», with the shield of the template', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { wrapper, button } = await mountPage();
    expect(wrapper.get('.biz-sub').text()).toBe('Two-factor authentication');
    expect(wrapper.get('h2.auth-title').text()).toBe('Two-factor authentication');
    expect(wrapper.get('p.auth-lead').text()).toBe(
      'Enter the 6-digit code from your authenticator app, or one of your recovery codes.',
    );
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:shield-check'));
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Verification code');
    const submit = button('mfa-submit');
    expect([submit.props('type'), submit.props('color'), submit.props('size'), submit.props('expand'), submit.text()]).toEqual([
      'submit',
      'primary',
      'large',
      'block',
      'Verify',
    ]);
    const back = button('mfa-back');
    expect([back.props('fill'), back.props('expand'), back.text()]).toEqual(['clear', 'block', 'Back to sign in']);
    expect(document.title).toBe('Two-factor authentication - ERPlora Cloud');
  });

  it('speaks Spanish with the translations of the template', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { wrapper, button } = await mountPage({ locale: 'es' });
    expect(wrapper.get('h2.auth-title').text()).toBe('Verificación en dos pasos');
    expect(button('mfa-submit').text()).toBe('Verificar');
    expect(button('mfa-back').text()).toBe('Volver a iniciar sesión');
  });
});

describe('TwoFactorAuthenticatePage: arriving', () => {
  it('stays while the login waits for its second factor', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { router } = await mountPage();
    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(assign).not.toHaveBeenCalled();
  });

  it('sends a visitor who is already signed in on to next at once', async () => {
    fakeAllauth({ 'GET /auth/session': signedIn });
    await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('sends one without a waiting login back to the sign-in, keeping next', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { router } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
  });

  it('says it could not sign in when the session cannot be read', async () => {
    fakeAllauth({ 'GET /auth/session': offline });
    const { wrapper, router } = await mountPage();
    expect(wrapper.get('.non-field-error').text()).toBe('We could not sign you in. Please try again.');
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
  });
});

describe('TwoFactorAuthenticatePage: verifying', () => {
  it('posts the code to allauth.headless and leaves for the launcher, with the new session', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': signedIn });
    const { verify } = await mountPage();
    await verify('654321');
    expect(server.callsTo('POST /auth/2fa/authenticate').map((c) => c.body)).toEqual([{ code: '654321' }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes to next when it is a path of this site, never elsewhere', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': signedIn });
    const { verify } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
    assign.mockClear();
    const evil = await mountPage({ path: `/2fa/authenticate?next=${encodeURIComponent('//evil.example.com')}` });
    await evil.verify();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('never follows a next with a tab, which the browser would read as another host', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': signedIn });
    const { verify } = await mountPage({ path: '/2fa/authenticate?next=%2F%09%2Fevil.example.com' });
    await verify();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('paints a wrong code under the input, marks it invalid and stays', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': rejected('Incorrect code.', 'code') });
    const { wrapper, verify } = await mountPage();
    await verify('000000');
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('paints an error of the whole form above the input', async () => {
    fakeAllauth({
      'GET /auth/session': pendingSecondFactor,
      'POST /auth/2fa/authenticate': rejected('Too many attempts.', undefined, 'too_many_requests'),
    });
    const { wrapper, verify } = await mountPage();
    await verify();
    expect(wrapper.get('.non-field-error').text()).toBe('Too many attempts.');
  });

  it('disables «Verify» while the code is on its way', async () => {
    const answer = held(signedIn);
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': answer.answer });
    const { wrapper, verify } = await mountPage();
    await verify();
    const submit = () => wrapper.get('[data-testid="mfa-submit"]').element as Control;
    expect(submit().disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(assign).toHaveBeenCalledOnce();
  });

  // With no login waiting, allauth answers 401 with no pending flow (never 409): the session says why.
  it('goes on when another tab finished the sign-in meanwhile (401, and the session is signed in)', async () => {
    const server = fakeAllauth({
      'GET /auth/session': [pendingSecondFactor, signedIn],
      'POST /auth/2fa/authenticate': anonymous,
    });
    const { verify, router } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(server.callsTo('GET /auth/session')).toHaveLength(2);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
  });

  it('goes back to the sign-in, keeping next, when the waiting login is gone (401, expired)', async () => {
    fakeAllauth({
      'GET /auth/session': [pendingSecondFactor, anonymous],
      'POST /auth/2fa/authenticate': anonymous,
    });
    const { verify, router } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    expect(assign).not.toHaveBeenCalled();
  });

  it('says it could not sign in when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': offline });
    const { wrapper, verify } = await mountPage({ locale: 'es' });
    await verify();
    expect(wrapper.get('.non-field-error').text()).toBe('No hemos podido iniciar tu sesión. Vuelve a intentarlo.');
    expect(assign).not.toHaveBeenCalled();
  });
});

// flow: ACCOUNTS-F05 — «Trust this browser for 14 days» (old SAAS_AUTH-F06): opt-in, under the code, answered with
// the same «Verify» (one screen, as Google's and Microsoft's «Don't ask again on this device»).
describe('TwoFactorAuthenticatePage: «Trust this browser for 14 days»', () => {
  const answers = (trust: Answer | Answer[] = signedIn) => ({
    'GET /auth/session': [pendingSecondFactor, signedIn],
    'POST /auth/2fa/authenticate': pendingTrust,
    'POST /auth/2fa/trust': trust,
  });

  it('offers it unticked under the code, in English and in Spanish', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { wrapper } = await mountPage();
    const box = wrapper.getComponent(IonCheckbox);
    expect([box.attributes('data-testid'), box.props('checked'), box.text()]).toEqual([
      'mfa-trust',
      false,
      'Trust this browser for 14 days',
    ]);
    expect(wrapper.get('[data-testid="mfa-trust-hint"]').text()).toBe(
      'You will not be asked for a code from your app here again for 14 days. Not on a shared computer.',
    );
    const es = await mountPage({ locale: 'es' });
    expect(es.wrapper.getComponent(IonCheckbox).text()).toBe('Confiar en este navegador durante 14 días');
    expect(es.wrapper.get('[data-testid="mfa-trust-hint"]').text()).toBe(
      'Aquí no se te volverá a pedir el código de tu app durante 14 días. No lo marques en un ordenador compartido.',
    );
  });

  it('left unticked, a right code says «not now» and leaves with the new session', async () => {
    const server = fakeAllauth(answers());
    const { verify } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify('654321');
    expect(server.callsTo('POST /auth/2fa/authenticate').map((c) => c.body)).toEqual([{ code: '654321' }]);
    expect(server.callsTo('POST /auth/2fa/trust').map((c) => c.body)).toEqual([{ trust: false }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('ticked, a right code trusts this browser, with the CSRF token of the session', async () => {
    const server = fakeAllauth(answers());
    const { verify } = await mountPage();
    await verify('654321', { trust: true });
    const [call] = server.callsTo('POST /auth/2fa/trust');
    expect(call.body).toEqual({ trust: true });
    expect(call.headers).toMatchObject({ 'X-CSRFToken': 'tok-123', 'Content-Type': 'application/json' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('a wrong code asks nothing about the browser', async () => {
    const server = fakeAllauth({
      'GET /auth/session': pendingSecondFactor,
      'POST /auth/2fa/authenticate': rejected('Incorrect code.', 'code'),
    });
    const { verify } = await mountPage();
    await verify('000000', { trust: true });
    expect(server.callsTo('POST /auth/2fa/trust')).toEqual([]);
    expect(assign).not.toHaveBeenCalled();
  });

  it('when the answer is lost, stays on the question without the code and says so; «Verify» answers it again', async () => {
    const server = fakeAllauth(answers([offline, signedIn]));
    const { wrapper, verify } = await mountPage();
    await verify('654321', { trust: true });
    expect(wrapper.get('.non-field-error').text()).toBe('We could not sign you in. Please try again.');
    expect(wrapper.find('[data-testid="code"]').exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
    await wrapper.get('form[data-testid="mfa-form"]').trigger('submit');
    await flushPromises();
    expect(server.callsTo('POST /auth/2fa/trust').map((c) => c.body)).toEqual([{ trust: true }, { trust: true }]);
    expect(server.callsTo('POST /auth/2fa/authenticate')).toHaveLength(1);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  // allauth's answer when no login waits for the question (another tab answered it, or the login expired): a 401
  // without a pending flow, never a 409 (measured on the SaaS: `is_authenticated` null, signed in or not).
  const noLoginWaiting: Answer = () =>
    json(401, { status: 401, data: { flows: [{ id: 'login' }] }, meta: { is_authenticated: null } });

  it('goes on when another tab already answered it (401 without a waiting login, and the session is signed in)', async () => {
    const server = fakeAllauth({
      'GET /auth/session': [pendingSecondFactor, signedIn],
      'POST /auth/2fa/authenticate': pendingTrust,
      'POST /auth/2fa/trust': noLoginWaiting,
    });
    const { wrapper, verify } = await mountPage();
    await verify('654321', { trust: true });
    expect(server.callsTo('POST /auth/2fa/trust').map((c) => c.body)).toEqual([{ trust: true }]);
    expect(server.callsTo('GET /auth/session')).toHaveLength(2);
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes back to the sign-in, keeping next, when the waiting login is gone (401, and the session is anonymous)', async () => {
    fakeAllauth({
      'GET /auth/session': [pendingSecondFactor, anonymous],
      'POST /auth/2fa/authenticate': pendingTrust,
      'POST /auth/2fa/trust': noLoginWaiting,
    });
    const { router, verify } = await mountPage({ path: '/2fa/authenticate?next=%2Faccount' });
    await verify('654321');
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/account' });
    expect(assign).not.toHaveBeenCalled();
  });

  it('takes the session the answer gives, without asking for it again', async () => {
    const server = fakeAllauth(answers());
    const { verify } = await mountPage();
    await verify('654321', { trust: true });
    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('arriving at a login that waits for the question (a reload), asks it without the code', async () => {
    const server = fakeAllauth({ 'GET /auth/session': [pendingTrust, signedIn], 'POST /auth/2fa/trust': signedIn });
    const { wrapper, router } = await mountPage();
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(wrapper.find('[data-testid="code"]').exists()).toBe(false);
    expect(wrapper.findComponent(IonCheckbox).exists()).toBe(true);
    await wrapper.get('form[data-testid="mfa-form"]').trigger('submit');
    await flushPromises();
    expect(server.callsTo('POST /auth/2fa/trust').map((c) => c.body)).toEqual([{ trust: false }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });
});

describe('TwoFactorAuthenticatePage: «Back to sign in»', () => {
  it('ends the waiting login first, then goes to the sign-in keeping next', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'DELETE /auth/session': anonymous });
    const { button, router } = await mountPage({ path: '/2fa/authenticate?next=%2Fhub-login%2F%3Fhub%3Da' });
    await button('mfa-back').trigger('click');
    await flushPromises();
    expect(server.callsTo('DELETE /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
  });

  it('stays and says so when the waiting login could not be ended', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'DELETE /auth/session': offline });
    const { wrapper, button, router } = await mountPage();
    await button('mfa-back').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(wrapper.get('.non-field-error').text()).toBe('We could not sign you in. Please try again.');
  });
});

describe('TwoFactorAuthenticatePage: reCAPTCHA, invisible (accounts/frontend/recaptcha.ts; Ioan, 2026-10-22)', () => {
  afterEach(forgetRecaptcha);

  it('posts the app’s code with the token of `mfa_authenticate` and says reCAPTCHA protects the form', async () => {
    withRecaptcha();
    const server = fakeAllauth({ 'GET /auth/session': pendingSecondFactor, 'POST /auth/2fa/authenticate': signedIn });
    const { verify, wrapper } = await mountPage();
    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(true);

    await verify('654321');

    expect(server.callsTo('POST /auth/2fa/authenticate').map((c) => c.body)).toEqual([
      { code: '654321', recaptcha_token: 'token-for-mfa_authenticate' },
    ]);
  });
});
