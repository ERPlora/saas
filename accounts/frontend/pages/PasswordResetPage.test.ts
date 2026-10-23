// `/password/reset` («Forgot your password?»), over allauth.headless: the pages of ERPlora/saas's
// templates `account/password_reset.html` (the address) and `password_reset_done.html` (check your
// email), same structure and texts. allauth mails the link (to `/password/reset/key/<key>`) and
// answers the same whether the address has an account or not, and so does the page: it never says
// which.
import { IonButton, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fakeAllauth, held, offline, ok, rejected, tooManyRequests } from '../__tests__/allauth-server';
import { mountAccountPage } from '../__tests__/mount-account-page';
import { forgetRecaptcha, withRecaptcha } from '../__tests__/recaptcha-page';
import PasswordResetPage from './PasswordResetPage.vue';

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

beforeEach(() => {
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function mountPage(options: { locale?: 'en' | 'es' } = {}) {
  const mounted = await mountAccountPage(PasswordResetPage, { path: '/password/reset', locale: options.locale });
  const { wrapper } = mounted;
  const input = () => wrapper.getComponent(IonInput);
  async function send(email = 'owner@example.com') {
    await input().setValue(email);
    await wrapper.get('form[data-testid="password-reset-form"]').trigger('submit');
    await flushPromises();
  }
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid);
  const failure = () => wrapper.find('.non-field-error');
  return { ...mounted, input, send, button, failure };
}

describe('PasswordResetPage: the page of the template', () => {
  it('asks for the address under «Reset your password», with the way back to the sign-in', async () => {
    fakeAllauth();
    const { wrapper, input, button } = await mountPage();
    expect(wrapper.get('.biz-sub').text()).toBe('Reset your password');
    const email = input();
    expect([email.props('type'), email.props('label'), email.props('fill'), email.attributes('mode')]).toEqual([
      'email',
      'Email',
      'outline',
      'md',
    ]);
    expect([email.props('labelPlacement'), email.props('placeholder'), email.props('autocomplete')]).toEqual([
      'floating',
      'you@example.com',
      'email',
    ]);
    const submit = button('password-reset-submit')!;
    expect([submit.props('type'), submit.props('color'), submit.props('size'), submit.props('expand'), submit.text()]).toEqual([
      'submit',
      'primary',
      'large',
      'block',
      'Send Reset Link',
    ]);
    const foot = wrapper.get('.foot');
    expect(foot.text()).toBe('Remember your password? Sign in');
    expect(foot.get('a').attributes('href')).toBe('/launch');
    expect(document.title).toBe('Reset Password - ERPlora Cloud');
  });

  it('speaks Spanish with the translations of the template', async () => {
    fakeAllauth();
    const { wrapper, input, button } = await mountPage({ locale: 'es' });
    expect(wrapper.get('.biz-sub').text()).toBe('Restablece tu contraseña');
    expect(input().props('label')).toBe('Correo electrónico');
    expect(button('password-reset-submit')!.text()).toBe('Enviar Enlace');
    expect(wrapper.get('.foot').text()).toBe('¿Recuerdas tu contraseña? Iniciar sesión');
  });
});

describe('PasswordResetPage: sending the link', () => {
  it('posts the address to allauth.headless and says to check the email, never whether the account exists', async () => {
    const server = fakeAllauth({ 'POST /auth/password/request': ok() });
    const { wrapper, send, button } = await mountPage();
    await send('someone@example.com');
    expect(server.callsTo('POST /auth/password/request').map((c) => c.body)).toEqual([{ email: 'someone@example.com' }]);
    expect(wrapper.find('form[data-testid="password-reset-form"]').exists()).toBe(false);
    expect(wrapper.get('.biz-sub').text()).toBe('Check your email');
    expect(wrapper.get('[data-testid="password-reset-sent"]').text()).toBe(
      "We've sent password reset instructions to your email address. Check your inbox (and spam folder).",
    );
    expect(wrapper.text()).not.toContain('someone@example.com');
    expect(button('password-reset-back')!.text()).toBe('Back to Login');
    expect(wrapper.get('.foot').text()).toBe("Didn't get the email? Try again");
    expect(document.title).toBe('Check Your Email - ERPlora Cloud');
  });

  it('goes back to the sign-in from «Back to Login»', async () => {
    fakeAllauth({ 'POST /auth/password/request': ok() });
    const { send, button, router } = await mountPage();
    await send();
    await button('password-reset-back')!.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe('/launch');
  });

  it('asks again from «Try again», with the address kept', async () => {
    fakeAllauth({ 'POST /auth/password/request': ok() });
    const { wrapper, send, input } = await mountPage();
    await send('someone@example.com');
    await wrapper.get('[data-testid="password-reset-again"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('form[data-testid="password-reset-form"]').exists()).toBe(true);
    expect(input().props('modelValue')).toBe('someone@example.com');
    expect(wrapper.get('.biz-sub').text()).toBe('Reset your password');
    expect(document.title).toBe('Reset Password - ERPlora Cloud');
  });

  it('paints an invalid address under its input, marks it invalid and stays', async () => {
    fakeAllauth({ 'POST /auth/password/request': rejected('Enter a valid email address.', 'email') });
    const { wrapper, send, input, failure } = await mountPage();
    await send('nope');
    expect((input().element as Control).errorText).toBe('Enter a valid email address.');
    expect(input().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(failure().exists()).toBe(false);
    expect(wrapper.find('[data-testid="password-reset-sent"]').exists()).toBe(false);
  });

  it('says to wait when links were asked for too often (429)', async () => {
    fakeAllauth({ 'POST /auth/password/request': tooManyRequests });
    const { send, failure } = await mountPage();
    await send();
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
  });

  it('says something went wrong when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'POST /auth/password/request': offline });
    const { wrapper, send, failure } = await mountPage({ locale: 'es' });
    await send();
    expect(failure().text()).toBe('Algo ha ido mal. Inténtalo de nuevo.');
    expect(wrapper.find('[data-testid="password-reset-sent"]').exists()).toBe(false);
  });

  it('disables «Send Reset Link» while the request is on its way', async () => {
    const answer = held(ok());
    fakeAllauth({ 'POST /auth/password/request': answer.answer });
    const { wrapper, send } = await mountPage();
    await send();
    expect((wrapper.get('[data-testid="password-reset-submit"]').element as Control).disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(wrapper.find('[data-testid="password-reset-sent"]').exists()).toBe(true);
  });
});

describe('PasswordResetPage: reCAPTCHA, invisible (accounts/frontend/recaptcha.ts; Ioan, 2026-10-22)', () => {
  afterEach(forgetRecaptcha);

  it('asks the link with the token of `password_reset` and says reCAPTCHA protects the form', async () => {
    withRecaptcha();
    const server = fakeAllauth({ 'POST /auth/password/request': ok() });
    const { send, wrapper } = await mountPage();
    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(true);

    await send('someone@example.com');

    expect(server.callsTo('POST /auth/password/request').map((c) => c.body)).toEqual([
      { email: 'someone@example.com', recaptcha_token: 'token-for-password_reset' },
    ]);
  });
});
