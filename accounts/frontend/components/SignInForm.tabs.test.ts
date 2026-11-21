// The launcher's form, its two strict tabs: the segment and the link under the form switch between «Sign in» and
// «Create account» (`?tab=signup`); «Sign in» never creates an account and «Create account» never signs in.
import { IonButton } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import {
  anonymous,
  conflict,
  fakeAllauth,
  held,
  offline,
  pendingEmailVerification,
  pendingLoginCode,
  rejected,
  signedIn,
  tooManyRequests,
} from '../__tests__/allauth-server';
import { assign, mountForm, setUpSignInForm } from '../__tests__/sign-in-form';

setUpSignInForm();

describe('SignInForm: the tabs «Sign in» and «Create account»', () => {
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

  it('follows the address on /shell as well, where the installed app opens it', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const { router, tab } = await mountForm({ path: '/shell' });
    await router.replace('/shell?tab=signup');
    await flushPromises();
    expect(tab()).toBe('signup');
  });

  // The installed app opens the launcher at /shell/; the pages that send back write `/launch` (LAUNCHER): one page.
  it.each(['/shell', '/shell/'])(
    'opened at %s, follows every address of the launcher when the page comes back (Ionic reuses it)',
    async (opened) => {
      fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
      const { wrapper, signIn, router, tab } = await mountForm({ path: `${opened}?tab=signup` });
      await signIn('new@example.com', 'a long pass phrase');
      expect(router.currentRoute.value.path).toBe('/verify-email');
      await router.replace('/launch?notice=code_expired');
      await flushPromises();
      expect(tab()).toBe('signin');
      expect(wrapper.find('[data-testid="login-notice"]').exists()).toBe(true);
      await router.replace(opened === '/shell' ? '/shell/?tab=signup' : '/shell?tab=signup');
      await flushPromises();
      expect(tab()).toBe('signup');
      expect(wrapper.find('[data-testid="login-notice"]').exists()).toBe(false);
    },
  );

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

  it('speaks Spanish in both tabs', async () => {
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

describe('SignInForm: «Sign in» never creates an account', () => {
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

  // Ionic animates the page out (and keeps it in its stack) once the address is already the code's, which has no
  // `?tab=`: the leaving form must not turn into «Sign in» for an instant on its way out (saas#291).
  it.each([
    ['en', 'Create account', "Enter your email and choose a password. We'll email you a code to confirm it."],
    ['es', 'Crear cuenta', 'Introduce tu email y elige una contraseña. Te enviaremos un código para confirmarlo.'],
  ] as const)('stays «Create account» while it leaves for the code, in %s (saas#291)', async (locale, label, intro) => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
    const { wrapper, signIn, router, tab } = await mountForm({ path: '/launch?tab=signup', locale });
    await signIn('new@example.com', 'a long pass phrase');
    expect(router.currentRoute.value.path).toBe('/verify-email');
    expect(tab()).toBe('signup');
    expect(wrapper.get('.intro').text()).toBe(intro);
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe(label);
    expect(wrapper.find('[data-testid="login-forgot"]').exists()).toBe(false);
  });

  it('follows the address again when the page comes back on screen (Ionic reuses it)', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
    const { wrapper, signIn, router, tab } = await mountForm({ path: '/launch?tab=signup' });
    await signIn('new@example.com', 'a long pass phrase');
    // The code page sends back without a tab when the code is gone: the sign-in starts again, and says why.
    await router.replace('/launch?notice=code_expired');
    await flushPromises();
    expect(tab()).toBe('signin');
    expect(wrapper.find('[data-testid="login-notice"]').exists()).toBe(true);
    await router.replace('/launch?tab=signup');
    await flushPromises();
    expect(tab()).toBe('signup');
    expect(wrapper.find('[data-testid="login-notice"]').exists()).toBe(false);
  });
});
