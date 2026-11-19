// The entry (`/launch`) before the launcher: signed out it is the sign-in card itself, and signing in or creating
// the account comes back here; signed in with somewhere to go (`?next=`), it goes there at once.
import { applySurface } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { ANONYMOUS, flush } from '../__tests__/mount-hubs';
import { anonymous, fakeAllauth, pendingEmailVerification, pendingLoginCode, signedIn } from '../../../accounts/frontend/__tests__/allauth-server';
import { setup, setUpLaunchPage } from '../__tests__/launch-page';

setUpLaunchPage();

describe('LaunchPage: signed out, the sign-in itself', () => {
  // The entrance holds the form with the tabs «Sign in» and «Create account», in the frame of the old template
  // login (`AuthShell`): logo, «ERPlora Cloud», «Global panel», the card and the terms.
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    document.cookie = 'csrftoken=tok-123';
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is the old login card with the form, and subscribes to nothing', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    await flush();
    expect(s.wrapper.get('h1.biz-name').text()).toBe('ERPlora Cloud');
    expect(s.wrapper.get('.biz-sub').text()).toBe('Global panel');
    const card = s.wrapper.get('ion-card.glass');
    expect(card.find('form[data-testid="login-form"]').exists()).toBe(true);
    expect(card.find('[data-testid="login-tabs"]').exists()).toBe(true);
    expect(card.text()).toContain('Enter your email and password.');
    for (const testid of ['login-email', 'login-password', 'login-submit']) expect(card.find(`[data-testid="${testid}"]`).exists()).toBe(true);
    expect(card.get('[data-testid="login-submit"]').text()).toBe('Sign in');
    expect(s.wrapper.find('ion-card-title').exists()).toBe(false);
    expect(s.client.stream.subscriptions('hubs.business.list')).toEqual([]);
    expect(document.title).toBe('Sign In - ERPlora Cloud');
  });

  it('carries the terms under the card, as the template login did', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    const foot = s.wrapper.get('.foot');
    expect(foot.text()).toContain('By continuing you agree to our');
    expect(foot.findAll('a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['Terms', '/legal/terms/'],
      ['Privacy Policy', '/legal/privacy/'],
    ]);
  });

  it('inside the installed app the terms open in app mode, with a way back (PUBLIC-F26)', async () => {
    applySurface('desktop');
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS });
    expect(s.wrapper.get('.foot').findAll('a').map((a) => a.attributes('href'))).toEqual([
      '/legal/terms/?surface=desktop',
      '/legal/privacy/?surface=desktop',
    ]);
  });

  it('signs in and loads the launcher again with the new session', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': signedIn });
    const s = await setup({ session: ANONYMOUS });
    const input = (name: string) => s.wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
    await input('email').setValue('owner@example.com');
    await input('password').setValue('owner');
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(server.callsTo('POST /auth/login').map((call) => call.body)).toEqual([{ email: 'owner@example.com', password: 'owner' }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('asks for the mailed code next, carrying where the person was going', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/login': pendingLoginCode });
    const s = await setup({ session: ANONYMOUS, path: '/launch?next=%2Faccount' });
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/verify-email?next=/account');
  });

  it('speaks Spanish', async () => {
    fakeAllauth({ 'GET /auth/session': anonymous });
    const s = await setup({ session: ANONYMOUS, locale: 'es' });
    expect(s.wrapper.get('.biz-sub').text()).toBe('Panel global');
    expect(s.wrapper.get('[data-testid="login-submit"]').text()).toBe('Entrar');
    expect(document.title).toBe('Iniciar Sesión - ERPlora Cloud');
  });

  // Where the old sign-up pages lead: the same card, on «Create account».
  it('opens «Create account» from /launch?tab=signup, and creates the account there', async () => {
    const server = fakeAllauth({ 'GET /auth/session': anonymous, 'POST /auth/signup': pendingEmailVerification });
    const s = await setup({ session: ANONYMOUS, path: '/launch?tab=signup&next=%2Faccount' });
    const card = s.wrapper.get('ion-card.glass');
    expect(card.get('[data-testid="login-submit"]').text()).toBe('Create account');
    const input = (name: string) => s.wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
    await input('email').setValue('new@example.com');
    await input('password').setValue('a long pass phrase');
    await s.wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flush();
    expect(server.callsTo('POST /auth/signup').map((call) => call.body)).toEqual([{ email: 'new@example.com', password: 'a long pass phrase' }]);
    expect(server.callsTo('POST /auth/login')).toEqual([]);
    expect(s.router.currentRoute.value.fullPath).toBe('/verify-email?next=/account');
  });
});

describe('LaunchPage: signed in, with somewhere to go (`?next=`)', () => {
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('goes there at once, as the template login sent a signed-in visitor on', async () => {
    await setup({ path: '/launch?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/launch'])('stays for a next elsewhere or here (%s)', async (next) => {
    const s = await setup({ path: `/launch?next=${encodeURIComponent(next)}` });
    expect(assign).not.toHaveBeenCalled();
    expect(s.client.stream.subscriptions('hubs.business.list')).toHaveLength(1);
  });
});
