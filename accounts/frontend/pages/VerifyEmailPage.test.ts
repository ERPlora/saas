// `/verify-email`: the one page of the codes allauth mails, over allauth.headless, in the auth frame.
// Every sign-in with a password
// waits there: for the code that proves the address of a sign-up or of an address never
// proven (`verify_email`, posted to `…/auth/email/verify`), or for the sign-in code mailed to every other
// account (`login_by_code`, posted to `…/auth/code/confirm`). The page reads which from the session. Then
// the visitor leaves the SPA for `next` or the launcher, as the sign-in does. «Send a new code» only where
// allauth sends one (`verify_email`); a sign-in code is renewed by signing in again. «Use a different
// email» ends the waiting login (allauth would resume the stage otherwise) and goes back to the sign-in.
import { applySurface, ionIconSrc } from '@erplora/ui/shell';
import { IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  anonymous,
  conflict,
  fakeAllauth,
  held,
  offline,
  ok,
  pendingEmailVerification,
  pendingLoginCode,
  pendingSecondFactor,
  rejected,
  signedIn,
  tooManyRequests,
} from '../__tests__/allauth-server';
import { forgetRecaptcha, withRecaptcha } from '../__tests__/recaptcha-page';
import { assign, type Control, mountPage, setUpVerifyEmailPage } from '../__tests__/verify-email-page';

setUpVerifyEmailPage();

describe('VerifyEmailPage: the page of the template', () => {
  it('inside the installed app the terms open in app mode, with a way back (PUBLIC-F26)', async () => {
    applySurface('mobile');
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper } = await mountPage({ email: 'new@example.com' });
    expect(wrapper.get('.foot').findAll('a').map((a) => a.attributes('href'))).toEqual([
      '/legal/terms/?surface=mobile',
      '/legal/privacy/?surface=mobile',
    ]);
  });

  it('asks for the code mailed to the address that signed up, under «Check your email»', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper, button } = await mountPage({ email: 'new@example.com' });
    expect(wrapper.get('.biz-sub').text()).toBe('Global panel');
    expect(wrapper.get('h2.auth-title').text()).toBe('Check your email');
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to new@example.com');
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:mail-check'));
    const input = wrapper.getComponent(IonInput);
    expect([input.props('label'), input.props('autocomplete'), input.attributes('mode'), input.props('fill')]).toEqual([
      'Verification code',
      'one-time-code',
      'md',
      'outline',
    ]);
    const submit = button('verify-email-submit');
    expect([submit.props('type'), submit.props('color'), submit.props('size'), submit.props('expand'), submit.text()]).toEqual([
      'submit',
      'primary',
      'large',
      'block',
      'Verify',
    ]);
    const resend = button('verify-email-resend');
    expect([resend.props('fill'), resend.props('expand'), resend.text()]).toEqual(['clear', 'block', 'Send a new code']);
    const other = button('verify-email-other');
    expect([other.props('fill'), other.props('expand'), other.text()]).toEqual(['clear', 'block', 'Use a different email']);
    expect(wrapper.get('.foot').findAll('a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['Terms', '/legal/terms/'],
      ['Privacy Policy', '/legal/privacy/'],
    ]);
    expect(document.title).toBe('Check your email - ERPlora Cloud');
  });

  it('says where the code went without naming the address when it does not know it (a reload)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper } = await mountPage();
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to your email address.');
  });

  it('prints the address as text, never as markup', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper } = await mountPage({ email: '<b>x</b>@example.com' });
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to <b>x</b>@example.com');
    expect(wrapper.find('p.auth-lead b').exists()).toBe(false);
  });

  it('speaks Spanish with the translations of the template', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper, button } = await mountPage({ locale: 'es', email: 'new@example.com' });
    expect(wrapper.get('h2.auth-title').text()).toBe('Revisa tu correo electrónico');
    expect(wrapper.get('p.auth-lead').text()).toBe('Te hemos enviado un código a new@example.com');
    expect(button('verify-email-submit').text()).toBe('Verificar');
    expect(button('verify-email-resend').text()).toBe('Enviar un código nuevo');
    expect(button('verify-email-other').text()).toBe('Usar otro correo electrónico');
  });
});

describe('VerifyEmailPage: arriving', () => {
  it('stays while the sign-up waits for its code', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { router, failure } = await mountPage();
    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.path).toBe('/verify-email');
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('sends a visitor who is already signed in on to next at once', async () => {
    fakeAllauth({ 'GET /auth/session': signedIn });
    await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('sends one without a waiting sign-up back to the sign-in of the launcher, keeping next', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { router } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
  });

  it('sends one whose login waits for its second factor on to the 2FA page, keeping next', async () => {
    fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { router } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
  });

  it('says it could not sign in when the session cannot be read', async () => {
    fakeAllauth({ 'GET /auth/session': offline });
    const { failure, router } = await mountPage();
    expect(failure().text()).toBe('We could not sign you in. Please try again.');
    expect(router.currentRoute.value.path).toBe('/verify-email');
  });
});

describe('VerifyEmailPage: verifying', () => {
  it("posts the code as allauth's key and leaves for the launcher, with the new session", async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': signedIn });
    const { verify } = await mountPage();
    await verify('654321');
    expect(server.callsTo('POST /auth/email/verify').map((c) => c.body)).toEqual([{ key: '654321' }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes to next when it is a path of this site, never elsewhere', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': signedIn });
    const { verify } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
    assign.mockClear();
    const evil = await mountPage({ path: `/verify-email?next=${encodeURIComponent('//evil.example.com')}` });
    await evil.verify();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('paints a wrong or expired code under the input, marks it invalid and stays', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': rejected('Incorrect code.', 'key') });
    const { wrapper, verify, failure } = await mountPage();
    await verify('000000');
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('paints an error of the whole form above the input', async () => {
    fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'POST /auth/email/verify': rejected('This email address is already in use.', undefined, 'email_taken'),
    });
    const { verify, failure } = await mountPage();
    await verify();
    expect(failure().text()).toBe('This email address is already in use.');
  });

  it('disables «Verify» while the code is on its way', async () => {
    const answer = held(signedIn);
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': answer.answer });
    const { wrapper, verify } = await mountPage();
    await verify();
    const submit = () => wrapper.get('[data-testid="verify-email-submit"]').element as Control;
    expect(submit().disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(assign).toHaveBeenCalledOnce();
  });

  it('goes on to the 2FA page, keeping next, when the account asks for its second factor next', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': pendingSecondFactor });
    const { verify, router } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes back to the sign-in, keeping next and saying why, when the waiting sign-up is gone (409: expired, too many tries)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': conflict });
    const { verify, router } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify();
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a', notice: 'code_expired' });
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes to the sign-in when the address is verified but the session is not opened (401, nothing pending)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': anonymous });
    const { verify, router } = await mountPage();
    await verify();
    expect(router.currentRoute.value.fullPath).toBe('/launch');
  });

  it('says to wait when there were too many attempts (429)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': tooManyRequests });
    const { verify, failure } = await mountPage();
    await verify();
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
  });

  it('says it could not sign in when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': offline });
    const { verify, failure } = await mountPage({ locale: 'es' });
    await verify();
    expect(failure().text()).toBe('No hemos podido iniciar tu sesión. Vuelve a intentarlo.');
    expect(assign).not.toHaveBeenCalled();
  });
});

describe('VerifyEmailPage: «Send a new code»', () => {
  it('asks allauth for another code and says it was sent', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': ok() });
    const { click, notice, failure } = await mountPage();
    await click('verify-email-resend');
    expect(server.callsTo('POST /auth/email/verify/resend')).toHaveLength(1);
    expect(notice().text()).toBe('We sent you a new code.');
    expect(failure().exists()).toBe(false);
  });

  it('clears an earlier wrong code when the new one is sent', async () => {
    fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'POST /auth/email/verify': rejected('Incorrect code.', 'key'),
      'POST /auth/email/verify/resend': ok(),
    });
    const { wrapper, verify, click } = await mountPage();
    await verify('000000');
    await click('verify-email-resend');
    expect(wrapper.getComponent(IonInput).classes()).not.toContain('ion-invalid');
  });

  it('says no more codes can be sent when the server refuses another one (409) and the sign-up still waits', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': conflict });
    const { click, notice, failure, router } = await mountPage();
    await click('verify-email-resend');
    expect(failure().text()).toBe('We could not send a new code. Please try again later.');
    expect(notice().exists()).toBe(false);
    expect(router.currentRoute.value.path).toBe('/verify-email');
  });

  it('goes back to the sign-in when the waiting sign-up is gone (409 and nothing pending)', async () => {
    fakeAllauth({
      'GET /auth/session': [pendingEmailVerification, anonymous],
      'POST /auth/email/verify/resend': conflict,
    });
    const { click, router } = await mountPage();
    await click('verify-email-resend');
    expect(router.currentRoute.value.path).toBe('/launch');
  });

  it('says to wait when codes were asked for too often (429)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': tooManyRequests });
    const { click, failure } = await mountPage();
    await click('verify-email-resend');
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
  });

  it('says it could not send one when the server is out of reach', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': offline });
    const { click, failure } = await mountPage();
    await click('verify-email-resend');
    expect(failure().text()).toBe('We could not send a new code. Please try again later.');
  });

  it('disables the buttons while the request is on its way', async () => {
    const answer = held(ok());
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': answer.answer });
    const { wrapper, click } = await mountPage();
    await click('verify-email-resend');
    const disabled = (testid: string) => (wrapper.get(`[data-testid="${testid}"]`).element as Control).disabled;
    expect(['verify-email-submit', 'verify-email-resend', 'verify-email-other'].map(disabled)).toEqual([true, true, true]);
    answer.release();
    await flushPromises();
    expect(['verify-email-submit', 'verify-email-resend', 'verify-email-other'].map(disabled)).toEqual([false, false, false]);
  });
});

describe('VerifyEmailPage: «Use a different email»', () => {
  it('ends the waiting sign-up first, then goes to the sign-in keeping next', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'DELETE /auth/session': anonymous });
    const { click, router } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    await click('verify-email-other');
    expect(server.callsTo('DELETE /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
  });

  it('leaves by replacing the page in the history: Ionic drops it instead of keeping it under the sign-in', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'DELETE /auth/session': anonymous });
    const { click, router } = await mountPage({ path: '/verify-email?next=%2Faccount' });
    const replace = vi.spyOn(router, 'replace');
    const push = vi.spyOn(router, 'push');
    await click('verify-email-other');
    expect(replace).toHaveBeenCalledExactlyOnceWith({ path: '/launch', query: { next: '/account' } });
    expect(push).not.toHaveBeenCalled();
  });

  it('stays and says so when the waiting sign-up could not be ended', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'DELETE /auth/session': offline });
    const { click, router, failure } = await mountPage();
    await click('verify-email-other');
    expect(router.currentRoute.value.path).toBe('/verify-email');
    expect(failure().text()).toBe('We could not sign you in. Please try again.');
  });
});

describe('VerifyEmailPage: reCAPTCHA, invisible (accounts/frontend/recaptcha.ts)', () => {
  afterEach(forgetRecaptcha);

  it('posts the address’s code with the token of `verify_email` and says reCAPTCHA protects the form', async () => {
    withRecaptcha();
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify': signedIn });
    const { verify, wrapper } = await mountPage();

    await verify('654321');

    expect(server.callsTo('POST /auth/email/verify').map((c) => c.body)).toEqual([
      { key: '654321', recaptcha_token: 'token-for-verify_email' },
    ]);
    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(true);
  });

  it('posts the sign-in’s code with the token of `login_code`', async () => {
    withRecaptcha();
    const server = fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'POST /auth/code/confirm': signedIn });
    const { verify } = await mountPage({ flow: 'login_by_code' });

    await verify('482913');

    expect(server.callsTo('POST /auth/code/confirm').map((c) => c.body)).toEqual([
      { code: '482913', recaptcha_token: 'token-for-login_code' },
    ]);
  });

  it('asks another code with the token of `verify_email_resend`', async () => {
    withRecaptcha();
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification, 'POST /auth/email/verify/resend': ok() });
    const { click } = await mountPage();

    await click('verify-email-resend');

    expect(server.callsTo('POST /auth/email/verify/resend').map((c) => c.body)).toEqual([
      { recaptcha_token: 'token-for-verify_email_resend' },
    ]);
  });
});
