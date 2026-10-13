// The SaaS's sign-in page in Ionic Vue, over allauth.headless (browser client). The same page as the
// template login (`templates/account/login.html`): logo, «ERPlora Cloud» and «Global panel», email
// and password in outlined md inputs, «Forgot your password?», «Continue», «Continue with Google»
// only when it is configured, and the terms. A rejected login paints each message under its input;
// a signed-in one leaves the SPA for `next` (a path of this site) or the launcher.
import { createShellI18n, ionIconSrc, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { IonButton, IonIcon, IonInput } from '@ionic/vue';
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import en from '../locale/en.json';
import es from '../locale/es.json';
import LoginPage from './LoginPage.vue';

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

const ANONYMOUS: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const SIGNED_IN: SessionMe = { ...ANONYMOUS, user: { id: 'u1', label: 'Owner' } };
const USER = { id: 1, email: 'owner@example.com', display: 'Owner', has_usable_password: true };
const CONFIG = {
  csrfCookieName: 'csrftoken',
  csrfHeader: 'X-CSRFToken',
  liveUrl: '/api/live',
  apiBase: '/api',
  lang: 'en',
  deviceIdStorageKey: 'erplora.device_id',
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const signedIn = () => json(200, { status: 200, data: { user: USER, methods: [] }, meta: { is_authenticated: true } });

let fetchMock: ReturnType<typeof vi.fn>;
let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(signedIn()));
  vi.stubGlobal('fetch', fetchMock);
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
  session?: SessionMe;
  googleEnabled?: boolean;
}

async function mountLogin(options: Options = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/login');
  await router.isReady();
  const app = createApp({});
  provideSession(ref(options.session ?? ANONYMOUS), ref('live'), { app });
  const config = options.googleEnabled === undefined ? CONFIG : { ...CONFIG, googleEnabled: options.googleEnabled };
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: { config } },
    },
  });
  await flushPromises();
  const input = (name: 'email' | 'password') =>
    wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
  async function signIn(email = 'owner@example.com', password = 'owner') {
    await input('email').setValue(email);
    await input('password').setValue(password);
    await wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flushPromises();
  }
  return { wrapper, input, signIn, router };
}

describe('LoginPage: the page of the template', () => {
  it('paints the logo, «ERPlora Cloud», «Global panel» and the introduction', async () => {
    const { wrapper } = await mountLogin();
    const logo = wrapper.get('.erp-logo.lg');
    expect(logo.attributes('aria-label')).toBe('ERPlora Cloud');
    expect(logo.findAll('i').map((i) => i.classes()[0])).toEqual([
      'erp-nw',
      'erp-n',
      'erp-ne',
      'erp-w',
      'erp-hub',
      'erp-e',
      'erp-sw',
      'erp-s',
      'erp-se',
    ]);
    expect(wrapper.get('h1.biz-name').text()).toBe('ERPlora Cloud');
    expect(wrapper.get('.biz-sub').text()).toBe('Global panel');
    expect(wrapper.get('ion-card.glass').text()).toContain(
      "Enter your email and password. New here? We'll create your account.",
    );
  });

  it('asks for email and password in outlined md inputs, with the password toggle', async () => {
    const { wrapper, input } = await mountLogin();
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
  });

  it('links «Forgot your password?», the terms and the privacy policy, and the way back home', async () => {
    const { wrapper } = await mountLogin();
    const forgot = wrapper.get('[data-testid="login-forgot"]');
    // The page of allauth until its Vue page exists (a SPA route without a page would be a 404).
    expect([forgot.text(), forgot.attributes('href')]).toEqual(['Forgot your password?', '/accounts/password/reset/']);
    const foot = wrapper.get('.foot');
    expect(foot.text()).toContain('By continuing you agree to our');
    expect(foot.findAll('a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['Terms', 'https://erplora.com/legal/terms/'],
      ['Privacy Policy', 'https://erplora.com/legal/privacy/'],
    ]);
    // Ionic's `href` and `type` are props, set as DOM properties: read through the component.
    const back = wrapper.findAllComponents(IonButton).find((b) => b.classes().includes('auth-back'))!;
    expect([back.props('href'), back.attributes('aria-label')]).toEqual(['/', 'Back to home']);
    // The template's arrow is Lucide's, not Ionicons' (`account/_auth_header.html`).
    expect(back.findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:arrow-left'));
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Continue');
  });

  it('titles the browser tab as the template does', async () => {
    await mountLogin({ locale: 'es' });
    expect(document.title).toBe('Iniciar Sesión - ERPlora Cloud');
  });

  it('speaks Spanish with the translations of the template', async () => {
    const { wrapper, input } = await mountLogin({ locale: 'es' });
    expect(wrapper.get('.biz-sub').text()).toBe('Panel global');
    expect(input('email').props('label')).toBe('Correo electrónico');
    expect(input('password').props('label')).toBe('Contraseña');
    expect(wrapper.get('[data-testid="login-submit"]').text()).toBe('Continuar');
    expect(wrapper.get('[data-testid="login-forgot"]').text()).toBe('¿Olvidaste tu contraseña?');
  });
});

describe('LoginPage: «Continue with Google»', () => {
  it('is hidden unless spa-config says Google is configured', async () => {
    expect((await mountLogin()).wrapper.find('[data-testid="login-google"]').exists()).toBe(false);
    expect((await mountLogin({ googleEnabled: false })).wrapper.find('[data-testid="login-google"]').exists()).toBe(false);
  });

  it("posts a plain form to Django's /auth/google/login/ with the CSRF token and the destination", async () => {
    const { wrapper } = await mountLogin({ googleEnabled: true, path: '/login?next=%2Fhub-login%2F%3Fhub%3Da' });
    const form = wrapper.get('form[data-testid="login-google"]');
    expect([form.attributes('method'), form.attributes('action')]).toEqual(['post', '/auth/google/login/']);
    const hidden = Object.fromEntries(
      form.findAll('input[type="hidden"]').map((i) => [i.attributes('name'), (i.element as HTMLInputElement).value]),
    );
    expect(hidden).toEqual({ csrfmiddlewaretoken: 'tok-123', next: '/hub-login/?hub=a' });
    const button = form.findComponent(IonButton);
    expect([button.props('type'), button.text()]).toEqual(['submit', 'Continue with Google']);
    const icon = form.findComponent(IonIcon);
    expect(icon.props('name')).toBe('logo-google');
    // The template's Iconify icon was 1em, not the 1.35em ion-button gives a slotted ion-icon.
    expect(icon.classes()).toContain('google-icon');
    expect(wrapper.text()).toContain('or');
  });

  it('carries no destination when there is none', async () => {
    const { wrapper } = await mountLogin({ googleEnabled: true });
    expect(wrapper.find('form[data-testid="login-google"] input[name="next"]').exists()).toBe(false);
  });
});

describe('LoginPage: signing in', () => {
  it('posts the credentials to allauth.headless and leaves for the launcher, with the new session', async () => {
    const { signIn } = await mountLogin();
    await signIn();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect([url, init.method]).toEqual(['/_allauth/browser/v1/auth/login', 'POST']);
    expect(JSON.parse(init.body as string)).toEqual({ email: 'owner@example.com', password: 'owner' });
    expect((init.headers as Record<string, string>)['X-CSRFToken']).toBe('tok-123');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('goes to next when it is a path of this site (the jump to a hub)', async () => {
    const { signIn } = await mountLogin({ path: '/login?next=%2Fhub-login%2F%3Fhub%3Da%26next%3D%2Fsales' });
    await signIn();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a&next=/sales');
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/\\evil.example.com', 'javascript:alert(1)'])(
    'never follows a next that leaves the site (%s): the launcher instead',
    async (next) => {
      const { signIn } = await mountLogin({ path: `/login?next=${encodeURIComponent(next)}` });
      await signIn();
      expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
    },
  );

  it('disables «Continue» while the login is on its way', async () => {
    let answer!: (res: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (answer = resolve)));
    const { wrapper, signIn } = await mountLogin();
    await signIn();
    const submit = () => wrapper.get('[data-testid="login-submit"]').element as Control;
    expect(submit().disabled).toBe(true);
    answer(signedIn());
    await flushPromises();
    expect(submit().disabled).toBe(false);
  });

  it('paints each rejection under its input, marks it invalid and stays', async () => {
    fetchMock.mockResolvedValue(
      json(400, {
        status: 400,
        errors: [
          {
            message: 'The email address and/or password you specified are not correct.',
            code: 'email_password_mismatch',
            param: 'password',
          },
        ],
      }),
    );
    const { wrapper, input, signIn } = await mountLogin();
    await signIn('owner@example.com', 'wrong');
    const password = input('password');
    expect((password.element as Control).errorText).toBe('The email address and/or password you specified are not correct.');
    expect(password.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(input('email').classes()).not.toContain('ion-invalid');
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('clears the old errors on the next attempt', async () => {
    fetchMock.mockResolvedValueOnce(
      json(400, { status: 400, errors: [{ message: 'Enter a valid email address.', code: 'invalid', param: 'email' }] }),
    );
    const { input, signIn } = await mountLogin();
    await signIn('nope', 'x');
    expect(input('email').classes()).toContain('ion-invalid');
    await signIn();
    expect(input('email').classes()).not.toContain('ion-invalid');
  });

  it('paints an error of the whole form above the inputs', async () => {
    fetchMock.mockResolvedValue(
      json(400, { status: 400, errors: [{ message: 'Too many failed login attempts.', code: 'too_many_login_attempts' }] }),
    );
    const { wrapper, signIn } = await mountLogin();
    await signIn();
    expect(wrapper.get('.non-field-error').text()).toBe('Too many failed login attempts.');
  });

  it('says it could not sign in when the server is out of reach, in the language of the page', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const { wrapper, signIn } = await mountLogin({ locale: 'es' });
    await signIn();
    expect(wrapper.get('.non-field-error').text()).toBe('No hemos podido iniciar tu sesión. Vuelve a intentarlo.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('sends on to the 2FA page when the login needs a second factor, keeping next', async () => {
    fetchMock.mockResolvedValue(
      json(401, { status: 401, data: { flows: [{ id: 'mfa_authenticate', is_pending: true }] }, meta: {} }),
    );
    const { wrapper, signIn, router } = await mountLogin({ path: '/login?next=%2Fhub-login%2F%3Fhub%3Da' });
    await signIn();
    expect(router.currentRoute.value.path).toBe('/2fa/authenticate');
    expect(router.currentRoute.value.query).toEqual({ next: '/hub-login/?hub=a' });
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });

  it('carries no next to the 2FA page when there is none', async () => {
    fetchMock.mockResolvedValue(
      json(401, { status: 401, data: { flows: [{ id: 'mfa_authenticate', is_pending: true }] }, meta: {} }),
    );
    const { signIn, router } = await mountLogin();
    await signIn();
    expect(router.currentRoute.value.fullPath).toBe('/2fa/authenticate');
  });

  it('says it could not sign in when the login needs a step this SPA does not have (email verification)', async () => {
    fetchMock.mockResolvedValue(
      json(401, { status: 401, data: { flows: [{ id: 'verify_email', is_pending: true }] }, meta: {} }),
    );
    const { wrapper, signIn, router } = await mountLogin();
    await signIn();
    expect(wrapper.get('.non-field-error').text()).toBe('We could not sign you in. Please try again.');
    expect(router.currentRoute.value.path).toBe('/login');
    expect(assign).not.toHaveBeenCalled();
  });

  it('goes on when a session was opened meanwhile in another tab (allauth answers 409)', async () => {
    fetchMock.mockResolvedValue(json(409, { status: 409 }));
    const { wrapper, signIn } = await mountLogin();
    await signIn();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
  });

  it('sends a visitor who is already signed in on to next at once, as the template login does', async () => {
    await mountLogin({ session: SIGNED_IN, path: '/login?next=%2Fhub-login%2F%3Fhub%3Da' });
    expect(assign).toHaveBeenCalledExactlyOnceWith('/hub-login/?hub=a');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
