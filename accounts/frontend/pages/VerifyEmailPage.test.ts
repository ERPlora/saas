// `/verify-email`: the one page of the codes allauth mails, over allauth.headless, in the frame of the
// template `account/confirm_email_verification_code.html` (ERPlora/saas). Every sign-in with a password
// waits there (Ioan, 2026-10-15): for the code that proves the address of a sign-up or of an address never
// proven (`verify_email`, posted to `…/auth/email/verify`), or for the sign-in code mailed to every other
// account (`login_by_code`, posted to `…/auth/code/confirm`). The page reads which from the session. Then
// the visitor leaves the SPA for `next` or the launcher, as the sign-in does. «Send a new code» only where
// allauth sends one (`verify_email`); a sign-in code is renewed by signing in again. «Use a different
// email» ends the waiting login (allauth would resume the stage otherwise) and goes back to the sign-in.
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
import { enterView, mountAccountPage } from '../__tests__/mount-account-page';
import VerifyEmailPage from './VerifyEmailPage.vue';

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

interface Options {
  path?: string;
  locale?: 'en' | 'es';
  /** The address the sign-in typed, handed over in the history state (never in the URL). */
  email?: string;
  /** The code the sign-in left waiting for, handed over the same way. */
  flow?: string;
}

async function mountPage(options: Options = {}) {
  const state = { ...(options.email ? { email: options.email } : {}), ...(options.flow ? { flow: options.flow } : {}) };
  const mounted = await mountAccountPage(VerifyEmailPage, {
    path: options.path ?? '/verify-email',
    locale: options.locale,
    state: Object.keys(state).length ? state : undefined,
  });
  const { wrapper } = mounted;
  async function verify(code = '123456') {
    await wrapper.getComponent(IonInput).setValue(code);
    await wrapper.get('form[data-testid="verify-email-form"]').trigger('submit');
    await flushPromises();
  }
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid)!;
  async function click(testid: string) {
    await button(testid).trigger('click');
    await flushPromises();
  }
  const failure = () => wrapper.find('.non-field-error');
  const notice = () => wrapper.find('[data-testid="verify-email-notice"]');
  return { ...mounted, verify, button, click, failure, notice };
}

describe('VerifyEmailPage: the page of the template', () => {
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
      ['Terms', 'https://erplora.com/legal/terms/'],
      ['Privacy Policy', 'https://erplora.com/legal/privacy/'],
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

describe('VerifyEmailPage: the sign-in code of every password sign-in (`login_by_code`)', () => {
  it('asks for the code mailed to the account, with no «Send a new code»: signing in again mails one', async () => {
    fakeAllauth({ 'GET /auth/session': pendingLoginCode });
    const { wrapper, button } = await mountPage({ email: 'owner@example.com' });
    expect(wrapper.get('h2.auth-title').text()).toBe('Check your email');
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to owner@example.com');
    expect(button('verify-email-resend')).toBeUndefined();
    expect(wrapper.get('[data-testid="verify-email-help"]').text()).toBe(
      "The code lasts 3 minutes. Didn't get it? Sign in again and we will email you a new one.",
    );
    expect(button('verify-email-other').text()).toBe('Use a different email');
  });

  it('never offers «Send a new code» for it, not even before the session answers (the form says which code)', async () => {
    const session = held(pendingLoginCode);
    fakeAllauth({ 'GET /auth/session': session.answer });
    const { button, wrapper } = await mountPage({ flow: 'login_by_code' });
    expect(button('verify-email-resend')).toBeUndefined();
    expect(wrapper.find('[data-testid="verify-email-help"]').exists()).toBe(true);
    session.release();
  });

  it('offers neither while it does not know which code waits (a reload whose session cannot be read)', async () => {
    fakeAllauth({ 'GET /auth/session': offline });
    const { button, wrapper } = await mountPage();
    expect(button('verify-email-resend')).toBeUndefined();
    expect(wrapper.find('[data-testid="verify-email-help"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    fakeAllauth({ 'GET /auth/session': pendingLoginCode });
    const { wrapper } = await mountPage({ email: 'owner@example.com', locale: 'es' });
    expect(wrapper.get('[data-testid="verify-email-help"]').text()).toBe(
      'El código dura 3 minutos. ¿No te ha llegado? Vuelve a iniciar sesión y te enviaremos uno nuevo.',
    );
  });

  it("posts the code to allauth's confirmation and leaves for next, with the new session", async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'POST /auth/code/confirm': signedIn });
    const { verify } = await mountPage({ path: '/verify-email?next=%2Fhub-login%2F%3Fhub%3Da' });
    await verify('482913');
    expect(server.callsTo('POST /auth/code/confirm').map((c) => c.body)).toEqual([{ code: '482913' }]);
    expect(server.callsTo('POST /auth/email/verify')).toEqual([]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it('paints a wrong code under the input and stays', async () => {
    fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'POST /auth/code/confirm': rejected('Incorrect code.', 'code', 'incorrect_code') });
    const { wrapper, verify, failure } = await mountPage();
    await verify('000000');
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes on to the 2FA page when the account has the authenticator app too', async () => {
    fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'POST /auth/code/confirm': pendingSecondFactor });
    const { verify, router } = await mountPage({ path: '/verify-email?next=%2Faccount' });
    await verify();
    expect(router.currentRoute.value.fullPath).toBe('/2fa/authenticate?next=/account');
  });

  it('goes back to the sign-in saying why when the code expired or was wrong too many times (409)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'POST /auth/code/confirm': conflict });
    const { verify, router } = await mountPage();
    await verify();
    expect(router.currentRoute.value.fullPath).toBe('/launch?notice=code_expired');
    expect(assign).not.toHaveBeenCalled();
  });

  it('«Use a different email» ends the waiting sign-in and goes back to the form', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingLoginCode, 'DELETE /auth/session': anonymous });
    const { click, router } = await mountPage();
    await click('verify-email-other');
    expect(server.callsTo('DELETE /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.fullPath).toBe('/launch');
  });
});

describe('VerifyEmailPage: coming back to it (Ionic keeps the page and shows it again)', () => {
  type Mounted = Awaited<ReturnType<typeof mountPage>>;

  /** The visitor goes to the sign-in and comes back to `to` (a location of the router, with its history state). */
  async function comeBack({ wrapper, router }: Mounted, to: Parameters<Mounted['router']['push']>[0]): Promise<void> {
    if (router.currentRoute.value.path !== '/launch') await router.push('/launch');
    await router.push(to);
    enterView(wrapper);
    await flushPromises();
  }

  it("after «Use a different email», the real account finds its own address and code, never the typo's", async () => {
    const server = fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'DELETE /auth/session': anonymous,
      'POST /auth/code/confirm': signedIn,
    });
    const mounted = await mountPage({ email: 'typo@exmaple.com', flow: 'verify_email' });
    const { wrapper, router, click, verify, button } = mounted;
    await wrapper.getComponent(IonInput).setValue('111111');
    await click('verify-email-other');
    expect(router.currentRoute.value.fullPath).toBe('/launch');

    // The sign-in of the real account: a code to the account, handed over as the launcher's form does.
    server.serve({ 'GET /auth/session': pendingLoginCode });
    await comeBack(mounted, { path: '/verify-email', state: { email: 'owner@example.com', flow: 'login_by_code' } });

    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to owner@example.com');
    expect(wrapper.getComponent(IonInput).props('modelValue')).toBe('');
    expect(button('verify-email-resend')).toBeUndefined();
    expect(wrapper.find('[data-testid="verify-email-help"]').exists()).toBe(true);
    await verify('482913');
    expect(server.callsTo('POST /auth/code/confirm').map((c) => c.body)).toEqual([{ code: '482913' }]);
    expect(server.callsTo('POST /auth/email/verify')).toEqual([]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('reads the session again and leaves nothing of the last visit: no digits, no error, no notice', async () => {
    const server = fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'POST /auth/email/verify': rejected('Incorrect code.', 'key'),
      'POST /auth/email/verify/resend': ok(),
    });
    const mounted = await mountPage({ email: 'new@example.com' });
    const { wrapper, verify, click, failure, notice } = mounted;
    await click('verify-email-resend');
    expect(notice().exists()).toBe(true);
    await verify('000000');
    expect(wrapper.getComponent(IonInput).classes()).toContain('ion-invalid');

    await comeBack(mounted, { path: '/verify-email', state: { email: 'other@example.com', flow: 'verify_email' } });

    expect(server.callsTo('GET /auth/session')).toHaveLength(2);
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to other@example.com');
    const input = wrapper.getComponent(IonInput);
    expect([input.props('modelValue'), input.classes().includes('ion-invalid')]).toEqual(['', false]);
    expect([failure().exists(), notice().exists()]).toEqual([false, false]);
  });

  it('says where the code went without an address when it comes back with none (a reload, another tab)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const mounted = await mountPage({ email: 'new@example.com' });

    await comeBack(mounted, '/verify-email');

    expect(mounted.wrapper.get('p.auth-lead').text()).toBe('We emailed a code to your email address.');
  });

  it('follows the session it reads again: signed in meanwhile, it leaves for next', async () => {
    fakeAllauth({ 'GET /auth/session': [pendingEmailVerification, signedIn] });
    const mounted = await mountPage({ path: '/verify-email?next=%2Faccount' });

    await comeBack(mounted, '/verify-email?next=%2Faccount');

    expect(assign).toHaveBeenCalledExactlyOnceWith('/account');
  });

  it('reads the session once per arrival: Ionic announces the first one too, around the mount', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper } = await mountPage({ email: 'new@example.com' });

    enterView(wrapper);
    await flushPromises();

    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
  });
});
