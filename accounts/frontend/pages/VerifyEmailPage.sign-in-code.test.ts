// The page of the codes with the sign-in code mailed to every account that signs in with a password
// (`login_by_code`, posted to `…/auth/code/confirm`): no «Send a new code», signing in again mails one.
import { IonInput } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import {
  anonymous,
  conflict,
  fakeAllauth,
  held,
  offline,
  pendingLoginCode,
  pendingSecondFactor,
  rejected,
  signedIn,
} from '../__tests__/allauth-server';
import { assign, type Control, mountPage, setUpVerifyEmailPage } from '../__tests__/verify-email-page';

setUpVerifyEmailPage();

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
