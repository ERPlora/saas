// `/password/reset/key/:resetKey`: the page the reset link of the mail opens (allauth's
// `HEADLESS_FRONTEND_URLS`), over allauth.headless: ERPlora/saas's `account/password_reset_from_key.html`,
// same structure and texts. It checks the key first (an expired or used link says so and offers a new
// one), then asks for the new password; the password rules are allauth's (Django's validators), whose
// messages paint under the input. Done → the sign-in with «Your password has been changed», or on at
// once when the server signs the person in.
import { IonButton, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  anonymous,
  fakeAllauth,
  held,
  offline,
  ok,
  pendingSecondFactor,
  rejected,
  signedIn,
  tooManyRequests,
} from '../__tests__/allauth-server';
import { mountAccountPage } from '../__tests__/mount-account-page';
import PasswordResetKeyPage from './PasswordResetKeyPage.vue';

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

const KEY = '1-ab3cde-0123456789abcdef';
const USER = { id: 1, email: 'owner@example.com', display: 'Owner', has_usable_password: true };
const validKey = ok({ user: USER });
const invalidKey = rejected('The password reset token was invalid.', 'key', 'token_invalid');

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  document.cookie = 'csrftoken=tok-123';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function mountPage(options: { locale?: 'en' | 'es' } = {}) {
  const mounted = await mountAccountPage(PasswordResetKeyPage, {
    path: `/password/reset/key/${KEY}`,
    props: { resetKey: KEY },
    locale: options.locale,
  });
  const { wrapper } = mounted;
  const input = () => wrapper.getComponent(IonInput);
  async function change(password = 'a new long password') {
    await input().setValue(password);
    await wrapper.get('form[data-testid="password-reset-key-form"]').trigger('submit');
    await flushPromises();
  }
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid);
  const failure = () => wrapper.find('.non-field-error');
  const form = () => wrapper.find('form[data-testid="password-reset-key-form"]');
  return { ...mounted, input, change, button, failure, form };
}

describe('PasswordResetKeyPage: the page of the template', () => {
  it('checks the key of the link, then asks for the new password under «Set a new password»', async () => {
    const server = fakeAllauth({ 'GET /auth/password/reset': validKey });
    const { wrapper, input, button, form } = await mountPage();
    const checks = server.callsTo('GET /auth/password/reset');
    expect(checks).toHaveLength(1);
    expect(checks[0].headers['X-Password-Reset-Key']).toBe(KEY);
    expect(wrapper.get('.biz-sub').text()).toBe('Set a new password');
    expect(form().exists()).toBe(true);
    const password = input();
    expect([password.props('type'), password.props('label'), password.props('fill'), password.attributes('mode')]).toEqual([
      'password',
      'New Password',
      'outline',
      'md',
    ]);
    expect([password.props('labelPlacement'), password.props('autocomplete')]).toEqual(['floating', 'new-password']);
    expect(wrapper.find('ion-input-password-toggle[slot="end"]').exists()).toBe(true);
    const submit = button('password-reset-key-submit')!;
    expect([submit.props('type'), submit.props('color'), submit.props('size'), submit.props('expand'), submit.text()]).toEqual([
      'submit',
      'primary',
      'large',
      'block',
      'Change Password',
    ]);
    const foot = wrapper.get('.foot');
    expect(foot.text()).toBe('Remember your password? Sign in');
    expect(foot.get('a').attributes('href')).toBe('/launch');
    expect(document.title).toBe('Set New Password - ERPlora Cloud');
  });

  // ACCOUNTS-G121: the rules in sight, as the template's page and Account's «Change password» (one hint, the
  // same words): only a hint, the server's validators decide and say which one failed under the input.
  it('says the rules under the new password and how strong it looks while it is typed, against its email', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey });
    const { input } = await mountPage();
    expect(input().props('helperText')).toBe('At least 8 characters; better long, and without your email.');
    await input().setValue('abc');
    expect(input().props('helperText')).toBe('Too short: at least 8 characters.');
    await input().setValue('owner-panaderia');
    expect(input().props('helperText')).toBe('Weak: avoid your email and use several kinds of characters.');
    await input().setValue('Pan-de-centeno-26');
    expect(input().props('helperText')).toBe('Strong.');
    expect(input().classes()).toContain('strength-strong');
  });

  it('says the rules in Spanish', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey });
    const { input } = await mountPage({ locale: 'es' });
    expect(input().props('helperText')).toBe('Al menos 8 caracteres; mejor larga y sin tu correo.');
  });

  it('says it is checking the link until the server answers', async () => {
    const answer = held(validKey);
    fakeAllauth({ 'GET /auth/password/reset': answer.answer });
    const { wrapper, form } = await mountPage();
    expect(wrapper.get('[data-testid="password-reset-key-checking"]').text()).toBe('Checking your link…');
    expect(form().exists()).toBe(false);
    answer.release();
    await flushPromises();
    expect(wrapper.find('[data-testid="password-reset-key-checking"]').exists()).toBe(false);
    expect(form().exists()).toBe(true);
  });

  it('speaks Spanish with the translations of the template', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey });
    const { wrapper, input, button } = await mountPage({ locale: 'es' });
    expect(wrapper.get('.biz-sub').text()).toBe('Establece una nueva contraseña');
    expect(input().props('label')).toBe('Nueva Contraseña');
    expect(button('password-reset-key-submit')!.text()).toBe('Cambiar contraseña');
  });
});

describe('PasswordResetKeyPage: a link that does not work', () => {
  it('says the link expired or is not valid and offers a new one, without the form', async () => {
    fakeAllauth({ 'GET /auth/password/reset': invalidKey });
    const { wrapper, button, form, router } = await mountPage();
    expect(form().exists()).toBe(false);
    expect(wrapper.get('[data-testid="password-reset-key-invalid"]').text()).toBe(
      'This password reset link has expired or is not valid.',
    );
    expect(wrapper.find('.foot').exists()).toBe(false);
    const again = button('password-reset-key-request')!;
    expect([again.props('color'), again.props('expand'), again.text()]).toEqual(['primary', 'block', 'Request New Link']);
    await again.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe('/password/reset');
  });

  it('goes back to the sign-in from «Back to Login»', async () => {
    fakeAllauth({ 'GET /auth/password/reset': invalidKey });
    const { button, router } = await mountPage();
    const back = button('password-reset-key-back')!;
    expect([back.props('fill'), back.text()]).toEqual(['clear', 'Back to Login']);
    await back.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe('/launch');
  });

  it('says something went wrong, and checks again on demand, when the server is out of reach', async () => {
    const server = fakeAllauth({ 'GET /auth/password/reset': [offline, validKey] });
    const { failure, form, button } = await mountPage();
    expect(failure().text()).toBe('Something went wrong. Please try again.');
    expect(form().exists()).toBe(false);
    await button('password-reset-key-retry')!.trigger('click');
    await flushPromises();
    expect(server.callsTo('GET /auth/password/reset')).toHaveLength(2);
    expect(failure().exists()).toBe(false);
    expect(form().exists()).toBe(true);
  });
});

describe('PasswordResetKeyPage: changing the password', () => {
  it('posts the key and the new password, then goes to the sign-in with the notice of the change', async () => {
    const server = fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': anonymous });
    const { change, router } = await mountPage();
    await change('a new long password');
    expect(server.callsTo('POST /auth/password/reset').map((c) => c.body)).toEqual([{ key: KEY, password: 'a new long password' }]);
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ notice: 'password_reset' });
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes on to the launcher at once when the server signs the person in', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': signedIn });
    const { change } = await mountPage();
    await change();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes on to the 2FA page when the sign-in that follows waits for a second factor', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': pendingSecondFactor });
    const { change, router } = await mountPage();
    await change();
    expect(router.currentRoute.value.fullPath).toBe('/2fa/authenticate');
  });

  it("paints the validators' messages under the password, marks it invalid and stays", async () => {
    fakeAllauth({
      'GET /auth/password/reset': validKey,
      'POST /auth/password/reset': () =>
        new Response(
          JSON.stringify({
            status: 400,
            errors: [
              { message: 'This password is too short.', code: 'password_too_short', param: 'password' },
              { message: 'This password is too common.', code: 'password_too_common', param: 'password' },
            ],
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
    });
    const { change, input, failure, router } = await mountPage();
    await change('abc');
    expect((input().element as Control).errorText).toBe('This password is too short. This password is too common.');
    expect(input().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(failure().exists()).toBe(false);
    expect(router.currentRoute.value.path).toBe(`/password/reset/key/${KEY}`);
  });

  it('says the link no longer works when its key was used meanwhile', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': invalidKey });
    const { wrapper, change, form } = await mountPage();
    await change();
    expect(form().exists()).toBe(false);
    expect(wrapper.find('[data-testid="password-reset-key-invalid"]').exists()).toBe(true);
  });

  it('says to wait after too many attempts (429)', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': tooManyRequests });
    const { change, failure } = await mountPage();
    await change();
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
  });

  it('says something went wrong when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': offline });
    const { change, failure, form } = await mountPage({ locale: 'es' });
    await change();
    expect(failure().text()).toBe('Algo ha ido mal. Inténtalo de nuevo.');
    expect(form().exists()).toBe(true);
  });

  it('disables «Change Password» while the change is on its way', async () => {
    const answer = held(anonymous);
    fakeAllauth({ 'GET /auth/password/reset': validKey, 'POST /auth/password/reset': answer.answer });
    const { wrapper, change, router } = await mountPage();
    await change();
    expect((wrapper.get('[data-testid="password-reset-key-submit"]').element as Control).disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/launch');
  });
});
