// The form of the launcher (`/launch`, the entrance; Ioan, 2026-10-15), over allauth.headless, with two strict
// tabs (FIX-LAUNCH-TABS): «Sign in» (the default) and «Create account» (`?tab=signup`). «Sign in» is the form
// of the old template login (ERPlora/saas `templates/account/login.html`): email and password in outlined md
// inputs, «Forgot your password?», its button and «Continue with Google» when it is configured; it never
// creates an account (gh:saas#1018). «Create account» is allauth's sign-up and never signs in. Every password
// sign-in then waits for the code mailed to the account (`verify_email` for a new or unproven address,
// `login_by_code` for the rest), typed at `/verify-email`; the 2FA step at `/2fa/authenticate`. Signed in, the
// launcher loads again with the new session (or `next`, a path of this site).
import { IonButton, IonIcon, IonInput, IonSegment } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  anonymous,
  conflict,
  fakeAllauth,
  held,
  json,
  offline,
  pendingEmailVerification,
  pendingLoginCode,
  pendingSecondFactor,
  rejected,
  signedIn,
  tooManyRequests,
} from '../__tests__/allauth-server';
import { mountAccountPage } from '../__tests__/mount-account-page';
import { forgetRecaptcha, withRecaptcha } from '../__tests__/recaptcha-page';
import { choose } from '../__tests__/mount-panel';
import SignInForm from './SignInForm.vue';

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
  googleEnabled?: boolean;
}

async function mountForm(options: Options = {}) {
  const mounted = await mountAccountPage(SignInForm, {
    path: options.path ?? '/launch',
    locale: options.locale,
    config: options.googleEnabled === undefined ? {} : { googleEnabled: options.googleEnabled },
  });
  const { wrapper } = mounted;
  const input = (name: 'email' | 'password') =>
    wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
  async function signIn(email = 'owner@example.com', password = 'owner') {
    await input('email').setValue(email);
    await input('password').setValue(password);
    await wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flushPromises();
  }
  const failure = () => wrapper.find('.non-field-error');
  /** Picks a tab of the segment above the form, as a person taps it. */
  const chooseTab = (tab: 'signin' | 'signup') => choose(wrapper.get('[data-testid="login-tabs"]').element, { value: tab });
  const tab = () => wrapper.findComponent(IonSegment).props('value');
  // In jsdom, Ionic's segment button hides its label from `textContent` (its slot patches): read the markup.
  const tabLabel = (value: 'signin' | 'signup') =>
    wrapper.get(`[data-testid="login-tab-${value}"]`).element.innerHTML.replace(/<[^>]*>/g, '').trim();
  return { ...mounted, input, signIn, failure, chooseTab, tab, tabLabel };
}

describe('SignInForm: the form of the template', () => {
  it('opens on «Sign in»: says to enter the email and password', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, tab } = await mountForm();
    expect(tab()).toBe('signin');
    expect(wrapper.get('.intro').text()).toBe('Enter your email and password.');
  });

  it('asks for email and password in outlined md inputs, with the password toggle', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, input } = await mountForm();
    const email = input('email');
    const password = input('password');
    // `mode` is not a prop of Ionic Vue's proxies: it reaches the element as an attribute.
    expect([email.props('type'), email.props('label'), email.props('fill'), email.attributes('mode')]).toEqual([
      'email',
      'Email',
      'outline',
      'md',
    ]);
    expect([email.props('labelPlacement'), email.props('placeholder'), email.props('autocomplete')]).toEqual([
      'floating',
      'you@example.com',
      'username',
    ]);
    expect([password.props('type'), password.props('label'), password.props('fill'), password.attributes('mode')]).toEqual([
      'password',
      'Password',
      'outline',
      'md',
    ]);
    expect(password.props('autocomplete')).toBe('current-password');
    expect(wrapper.find('ion-input-password-toggle[slot="end"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Sign in');
  });

  it('opens the reset page from «Forgot your password?» inside the SPA', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, router } = await mountForm();
    const forgot = wrapper.get('[data-testid="login-forgot"]');
    expect([forgot.text(), forgot.attributes('href')]).toEqual(['Forgot your password?', '/password/reset']);
    await forgot.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe('/password/reset');
  });

  it('says the password was changed when it comes from a reset (?notice=password_reset)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ path: '/launch?notice=password_reset' });
    expect(wrapper.get('[data-testid="login-notice"]').text()).toBe('Your password has been changed successfully.');
    const es = await mountForm({ path: '/launch?notice=password_reset', locale: 'es' });
    expect(es.wrapper.get('[data-testid="login-notice"]').text()).toBe('Tu contraseña ha sido cambiada exitosamente.');
  });

  it('says why the sign-in starts again when a mailed code expired or was wrong too many times (?notice=code_expired)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ path: '/launch?notice=code_expired' });
    expect(wrapper.get('[data-testid="login-notice"]').text()).toBe(
      'Your code expired or was typed wrong too many times. Sign in again and we will email you a new one.',
    );
    const es = await mountForm({ path: '/launch?notice=code_expired', locale: 'es' });
    expect(es.wrapper.get('[data-testid="login-notice"]').text()).toBe(
      'Tu código ha caducado o se ha escrito mal demasiadas veces. Vuelve a iniciar sesión y te enviaremos uno nuevo.',
    );
  });

  it('shows no notice otherwise, nor for a notice it does not know', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    expect((await mountForm()).wrapper.find('[data-testid="login-notice"]').exists()).toBe(false);
    expect((await mountForm({ path: '/launch?notice=nope' })).wrapper.find('[data-testid="login-notice"]').exists()).toBe(false);
  });

  it('speaks Spanish with the translations of the template', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, input } = await mountForm({ locale: 'es' });
    expect(input('email').props('label')).toBe('Correo electrónico');
    expect(input('password').props('label')).toBe('Contraseña');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Entrar');
    expect(wrapper.get('[data-testid="login-forgot"]').text()).toBe('¿Olvidaste tu contraseña?');
  });
});

describe('SignInForm: «Continue with Google»', () => {
  it('is hidden unless spa-config says Google is configured', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    expect((await mountForm()).wrapper.find('[data-testid="login-google"]').exists()).toBe(false);
    expect((await mountForm({ googleEnabled: false })).wrapper.find('[data-testid="login-google"]').exists()).toBe(false);
  });

  it("posts allauth.headless's provider redirect, a plain form, coming back to the destination", async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ googleEnabled: true, path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    const form = wrapper.get('form[data-testid="login-google"]');
    expect([form.attributes('method'), form.attributes('action')]).toEqual(['post', '/_allauth/browser/v1/auth/provider/redirect']);
    const hidden = Object.fromEntries(
      form.findAll('input[type="hidden"]').map((i) => [i.attributes('name'), (i.element as HTMLInputElement).value]),
    );
    expect(hidden).toEqual({
      provider: 'google',
      process: 'login',
      callback_url: '/hub-login/?hub=a',
      csrfmiddlewaretoken: 'tok-123',
    });
    const button = form.findComponent(IonButton);
    expect([button.props('type'), button.text()]).toEqual(['submit', 'Continue with Google']);
    const icon = form.findComponent(IonIcon);
    expect(icon.props('name')).toBe('logo-google');
    // The template's Iconify icon was 1em, not the 1.35em ion-button gives a slotted ion-icon.
    expect(icon.classes()).toContain('google-icon');
    expect(wrapper.text()).toContain('or');
  });

  it('comes back to the launcher when there is no destination, as the password does', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ googleEnabled: true });
    const callback = wrapper.get('form[data-testid="login-google"] input[name="callback_url"]');
    expect((callback.element as HTMLInputElement).value).toBe('/launch');
  });

  it.each(['https://evil.example.com/', '//evil.example.com'])('never comes back to another site (%s)', async (next) => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ googleEnabled: true, path: `/launch?next=${encodeURIComponent(next)}` });
    const callback = wrapper.get('form[data-testid="login-google"] input[name="callback_url"]');
    expect((callback.element as HTMLInputElement).value).toBe('/launch');
  });
});

describe('SignInForm: a login waiting for its second factor', () => {
  // Google comes back to `next` (or the launcher) with the login waiting for the code of the app; without
  // a session that page sends here, which goes on to the code, as the template login resumed it.
  it('goes on to /2fa/authenticate at once, keeping next', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingSecondFactor });
    const { router } = await mountForm({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    expect(server.callsTo('POST /auth/login')).toEqual([]);
  });

  it('stays when nothing waits', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous });
    const { router } = await mountForm();
    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
    expect(router.currentRoute.value.path).toBe('/launch');
  });

  it('stays when the session cannot be read: signing in starts a new login', async () => {
    fakeAllauth({ 'GET /auth/session': offline });
    const { router, failure } = await mountForm();
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(failure().exists()).toBe(false);
  });

  it.each([pendingEmailVerification, pendingLoginCode])(
    'leaves a mailed code to its own page: only the second factor is resumed here',
    async (pending) => {
      fakeAllauth({ 'GET /auth/session': pending });
      const { router } = await mountForm();
      expect(router.currentRoute.value.path).toBe('/launch');
    },
  );
});

describe('SignInForm: signing in', () => {
  it('posts the credentials to allauth.headless and loads the launcher again, with the new session', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': signedIn });
    const { signIn } = await mountForm();
    await signIn();
    const [call] = server.callsTo('POST /auth/login');
    expect(call.body).toEqual({ email: 'owner@example.com', password: 'owner' });
    expect(call.headers['X-CSRFToken']).toBe('tok-123');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes to next when it is a path of this site (the jump to a hub)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': signedIn });
    const { signIn } = await mountForm({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da%26next%3D%2Fsales' });
    await signIn();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a&next=/sales');
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/\\evil.example.com', 'javascript:alert(1)'])(
    'never follows a next that leaves the site (%s): the launcher instead',
    async (next) => {
      fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': signedIn });
      const { signIn } = await mountForm({ path: `/launch?next=${encodeURIComponent(next)}` });
      await signIn();
      expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
    },
  );

  it('disables «Sign in» while the login is on its way', async () => {
    const answer = held(signedIn);
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': answer.answer });
    const { wrapper, signIn } = await mountForm();
    await signIn();
    const submit = () => wrapper.get('[data-testid="login-submit"]').element as Control;
    expect(submit().disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(submit().disabled).toBe(false);
  });

  it('paints each rejection under its input, marks it invalid and stays', async () => {
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': rejected('The email address and/or password you specified are not correct.', 'password', 'email_password_mismatch'),
    });
    const { input, signIn, failure } = await mountForm();
    await signIn('owner@example.com', 'wrong');
    const password = input('password');
    expect((password.element as Control).errorText).toBe('The email address and/or password you specified are not correct.');
    expect(password.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(input('email').classes()).not.toContain('ion-invalid');
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('clears the old errors on the next attempt', async () => {
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': [rejected('Enter a valid email address.', 'email'), signedIn],
    });
    const { input, signIn } = await mountForm();
    await signIn('nope', 'x');
    expect(input('email').classes()).toContain('ion-invalid');
    await signIn();
    expect(input('email').classes()).not.toContain('ion-invalid');
  });

  it('paints an error of the whole form above the inputs', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': rejected('Too many failed login attempts.') });
    const { signIn, failure } = await mountForm();
    await signIn();
    expect(failure().text()).toBe('Too many failed login attempts.');
    expect(failure().attributes('role')).toBe('alert');
  });

  it('says it could not sign in when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': offline });
    const { signIn, failure } = await mountForm({ locale: 'es' });
    await signIn();
    expect(failure().text()).toBe('No hemos podido iniciar tu sesión. Vuelve a intentarlo.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('sends on to the 2FA page when the login needs a second factor, keeping next', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingSecondFactor });
    const { signIn, router, failure } = await mountForm({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    await signIn();
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('carries no next to the 2FA page when there is none', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingSecondFactor });
    const { signIn, router } = await mountForm();
    await signIn();
    expect(router.currentRoute.value.fullPath).toBe('/2fa/authenticate');
  });

  // Every password sign-in waits for a mailed code: the one that proves a new (or never proven) address,
  // or the sign-in code of every other account. Both are typed on the same page.
  it.each([
    ['a new account (verify_email)', pendingEmailVerification],
    ['the sign-in code (login_by_code)', pendingLoginCode],
  ])('goes to /verify-email for %s, keeping next and handing over the address', async (_, pending) => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pending });
    const { signIn, router, failure } = await mountForm({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    await signIn('ana@example.com', 'a long password');
    expect(router.currentRoute.value.path).toBe('/verify-email');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    // In the history state, never in the URL: the address and which code it waits for.
    const state = router.options.history.state as Record<string, unknown>;
    expect([state.email, state.flow]).toEqual(['ana@example.com', pending === pendingLoginCode ? 'login_by_code' : 'verify_email']);
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('carries no next to /verify-email when there is none', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode });
    const { signIn, router } = await mountForm();
    await signIn();
    expect(router.currentRoute.value.fullPath).toBe('/verify-email');
  });

  it('says it could not sign in when the login needs a step this SPA does not have', async () => {
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': () =>
        json(401, { status: 401, data: { flows: [{ id: 'provider_signup', is_pending: true }] }, meta: { is_authenticated: false } }),
    });
    const { signIn, router, failure } = await mountForm();
    await signIn();
    expect(failure().text()).toBe('We could not sign you in. Please try again.');
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(assign).not.toHaveBeenCalled();
  });

  it('says to wait when there were too many attempts (the sign-up limit answers 429 without a message)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': tooManyRequests });
    const { signIn, failure } = await mountForm();
    await signIn('new@example.com', 'a new long password');
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes on when a session was opened meanwhile in another tab (allauth answers 409)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': conflict });
    const { signIn, failure } = await mountForm();
    await signIn();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
    expect(failure().exists()).toBe(false);
  });

  it('makes «Sign in» and «Continue with Google» the large buttons of the template (touch targets over 44 px)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ googleEnabled: true });
    const sizes = wrapper.findAllComponents(IonButton).map((button) => button.props('size'));
    expect(sizes).toEqual(['large', 'large']);
  });
});

describe('SignInForm: the tabs «Sign in» and «Create account» (FIX-LAUNCH-TABS)', () => {
  it('names both tabs above the form, «Sign in» chosen', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, tab, tabLabel } = await mountForm();
    expect(tab()).toBe('signin');
    expect([tabLabel('signin'), tabLabel('signup')]).toEqual(['Sign in', 'Create account']);
    expect(wrapper.get('[data-testid="login-switch"]').text()).toBe('First time here? Create your account');
  });

  it('opens «Create account» from ?tab=signup: its intro, a new password, its button and no «Forgot your password?»', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, input, tab } = await mountForm({ path: '/launch?tab=signup&next=%2Faccount' });
    expect(tab()).toBe('signup');
    expect(wrapper.get('.intro').text()).toBe("Enter your email and choose a password. We'll email you a code to confirm it.");
    expect(input('email').props('autocomplete')).toBe('username');
    expect(input('password').props('autocomplete')).toBe('new-password');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Create account');
    expect(wrapper.find('[data-testid="login-forgot"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="login-switch"]').text()).toBe('Already have an account? Sign in');
  });

  it('switches the form with the segment and writes the tab in the address, keeping next', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, router, chooseTab, tab } = await mountForm({ path: '/launch?next=%2Faccount' });
    await chooseTab('signup');
    expect(tab()).toBe('signup');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Create account');
    expect(router.currentRoute.value.query).toEqual({ next: '/account', tab: 'signup' });
    await chooseTab('signin');
    expect(tab()).toBe('signin');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Sign in');
    expect(router.currentRoute.value.query).toEqual({ next: '/account' });
  });

  it('switches the form with the link under it, both ways', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, router, tab } = await mountForm({ path: '/launch?next=%2Faccount' });
    await wrapper.get('[data-testid="login-switch-action"]').trigger('click');
    await flushPromises();
    expect([tab(), router.currentRoute.value.query.tab]).toEqual(['signup', 'signup']);
    await wrapper.get('[data-testid="login-switch-action"]').trigger('click');
    await flushPromises();
    expect([tab(), router.currentRoute.value.query.tab]).toEqual(['signin', undefined]);
  });

  it('follows the address when it changes (a link of the page, the way back)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { router, tab } = await mountForm();
    await router.replace('/launch?tab=signup');
    await flushPromises();
    expect(tab()).toBe('signup');
  });

  it('leaves the errors of one tab behind when the other is chosen', async () => {
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': rejected('The email address and/or password you specified are not correct.', 'password', 'email_password_mismatch'),
    });
    const { wrapper, signIn, chooseTab, failure, input } = await mountForm();
    await signIn();
    expect(input('password').classes()).toContain('ion-invalid');
    await chooseTab('signup');
    expect(failure().exists()).toBe(false);
    expect(input('password').classes()).not.toContain('ion-invalid');
    expect(wrapper.find('[data-testid="login-error-signup"]').exists()).toBe(false);
  });

  it('keeps «Continue with Google» in both tabs', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper } = await mountForm({ path: '/launch?tab=signup', googleEnabled: true });
    expect(wrapper.find('form[data-testid="login-google"]').exists()).toBe(true);
  });

  it('speaks Spanish in both tabs (gh:saas#1425)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { wrapper, chooseTab, tabLabel } = await mountForm({ locale: 'es' });
    expect([tabLabel('signin'), tabLabel('signup')]).toEqual(['Entrar', 'Crear cuenta']);
    expect(wrapper.get('.intro').text()).toBe('Introduce tu email y tu contraseña.');
    expect(wrapper.get('[data-testid="login-switch"]').text()).toBe('¿Es tu primera vez? Crea tu cuenta');
    await chooseTab('signup');
    expect(wrapper.get('.intro').text()).toBe('Introduce tu email y elige una contraseña. Te enviaremos un código para confirmarlo.');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Crear cuenta');
    expect(wrapper.get('[data-testid="login-switch"]').text()).toBe('¿Ya tienes cuenta? Entra');
  });
});

describe('SignInForm: «Sign in» never creates an account (gh:saas#1018)', () => {
  it('posts only to the login, never to the sign-up', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode, 'POST /auth/signup': signedIn });
    const { signIn } = await mountForm();
    await signIn('new@example.com', 'a long password');
    expect(server.callsTo('POST /auth/login')).toHaveLength(1);
    expect(server.callsTo('POST /auth/signup')).toEqual([]);
  });

  // allauth answers an unknown address exactly as a wrong password (`email_password_mismatch`): the hint shows
  // for both, so it says nothing about which addresses hold an account.
  it('adds «First time here? Create your account» to the error of a wrong email or password, which opens «Create account»', async () => {
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': rejected('The email address and/or password you specified are not correct.', 'password', 'email_password_mismatch'),
    });
    const { wrapper, signIn, tab, router, input } = await mountForm({ path: '/launch?next=%2Faccount' });
    await signIn('new@example.com', 'a long password');
    expect(wrapper.get('[data-testid="login-error-signup"]').text()).toBe('First time here? Create your account');
    // The same generic error as a wrong password, under the password.
    expect(input('password').props('errorText')).toBe('The email address and/or password you specified are not correct.');
    await wrapper.get('[data-testid="login-error-signup"] button').trigger('click');
    await flushPromises();
    expect(tab()).toBe('signup');
    expect(router.currentRoute.value.query).toEqual({ next: '/account', tab: 'signup' });
  });

  it('adds no hint to any other error', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': rejected('Enter a valid email address.', 'email') });
    const { wrapper, signIn } = await mountForm();
    await signIn('not-an-email', 'x');
    expect(wrapper.find('[data-testid="login-error-signup"]').exists()).toBe(false);
  });
});

describe('SignInForm: «Create account» never signs in', () => {
  it('posts the email and password to the sign-up, never to the login, and goes on to the code that proves the address, keeping next', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification, 'POST /auth/login': signedIn });
    const { signIn, router, failure } = await mountForm({ path: '/launch?tab=signup&next=%2Faccount' });
    await signIn('new@example.com', 'a long pass phrase');
    const [call] = server.callsTo('POST /auth/signup');
    expect(call.body).toEqual({ email: 'new@example.com', password: 'a long pass phrase' });
    expect(server.callsTo('POST /auth/login')).toEqual([]);
    expect(router.currentRoute.value.path).toBe('/verify-email');
    expect(router.currentRoute.value.query).toEqual({ next: '/account' });
    const state = router.options.history.state as Record<string, unknown>;
    expect([state.email, state.flow]).toEqual(['new@example.com', 'verify_email']);
    expect(failure().exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('disables «Create account» while the sign-up is on its way', async () => {
    const answer = held(pendingEmailVerification);
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': answer.answer });
    const { wrapper, input } = await mountForm({ path: '/launch?tab=signup' });
    const submit = () => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === 'login-submit')!.props();
    await input('email').setValue('new@example.com');
    await input('password').setValue('a long pass phrase');
    await wrapper.get('form[data-testid="login-form"]').trigger('submit');
    expect(submit().disabled).toBe(true);
    answer.release();
    await flushPromises();
    expect(submit().disabled).toBe(false);
  });

  it('paints a refused password under its input and stays', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': rejected('This password is too short.', 'password', 'password_too_short') });
    const { signIn, input, router } = await mountForm({ path: '/launch?tab=signup' });
    await signIn('new@example.com', 'short');
    expect(input('password').props('errorText')).toBe('This password is too short.');
    expect(router.currentRoute.value.path).toBe('/launch');
  });

  it('says it could not create the account when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': offline });
    const { signIn, failure } = await mountForm({ path: '/launch?tab=signup' });
    await signIn('new@example.com', 'a long pass phrase');
    expect(failure().text()).toBe('We could not create your account. Please try again.');
    const es = await mountForm({ path: '/launch?tab=signup', locale: 'es' });
    await es.signIn('new@example.com', 'a long pass phrase');
    expect(es.failure().text()).toBe('No hemos podido crear tu cuenta. Inténtalo de nuevo.');
  });

  it('says to wait when the sign-ups of an address are limited (429)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': tooManyRequests });
    const { signIn, failure } = await mountForm({ path: '/launch?tab=signup' });
    await signIn('new@example.com', 'a long pass phrase');
    expect(failure().text()).toBe('Too many attempts. Please wait a few minutes and try again.');
  });

  it('goes on when a session was opened meanwhile in another tab (allauth answers 409)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': conflict });
    const { signIn } = await mountForm({ path: '/launch?tab=signup' });
    await signIn('new@example.com', 'a long pass phrase');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });
});

describe('SignInForm: reCAPTCHA, invisible (accounts/frontend/recaptcha.ts; Ioan, 2026-10-22)', () => {
  afterEach(forgetRecaptcha);

  it('signs in with Google’s token of `login` and says reCAPTCHA protects the form', async () => {
    withRecaptcha();
    const { callsTo } = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode });
    const { wrapper, signIn } = await mountForm();

    await signIn();

    expect(callsTo('POST /auth/login')[0].body).toEqual({
      email: 'owner@example.com',
      password: 'owner',
      recaptcha_token: 'token-for-login',
    });
    expect(wrapper.get('[data-testid="recaptcha-notice"]').text()).toContain('This site is protected by reCAPTCHA');
  });

  it('creates the account with the token of `signup`', async () => {
    withRecaptcha();
    const { callsTo } = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
    const { signIn } = await mountForm({ path: '/launch?tab=signup' });

    await signIn('new@example.com', 'a long new password');

    expect(callsTo('POST /auth/signup')[0].body).toMatchObject({ recaptcha_token: 'token-for-signup' });
  });

  it('paints the server’s refusal for the whole form', async () => {
    withRecaptcha();
    fakeAllauth({
      'GET /auth/session': anonymous,
      'POST /auth/login': rejected('We could not check that you are a person. Try again.', undefined, 'recaptcha_failed'),
    });
    const { signIn, failure } = await mountForm();

    await signIn();

    expect(failure().text()).toBe('We could not check that you are a person. Try again.');
  });

  it('without reCAPTCHA sends no token and shows no notice', async () => {
    const { callsTo } = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode });
    const { wrapper, signIn } = await mountForm();

    await signIn();

    expect(callsTo('POST /auth/login')[0].body).toEqual({ email: 'owner@example.com', password: 'owner' });
    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(false);
  });
});
