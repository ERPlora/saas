// `/login/error?code=…`: the one page of every refused sign-in or jump to a hub, ported from the
// templates `accounts/hub_link_invalid.html` (invalid_hub), `accounts/hub_access_denied.html`
// (not_a_member) and allauth's `socialaccount/authentication_error.html` and `login_cancelled.html`,
// and the refused «connect» of Google (google_link_refused: the message the adapter used to leave).
// Same texts, in the auth frame of the sign-in, with the way back: to the sign-in (keeping `next`),
// or to the launcher when there is a session. `google_no_account` is gone: an unknown Google
// address now creates its account, as an unknown address on the sign-in does.
import { IonButton } from '@ionic/vue';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { mountAccountPage, SIGNED_IN } from '../__tests__/mount-account-page';
import { SUPPORT_EMAIL_ID } from '../support';
import LoginErrorPage from './LoginErrorPage.vue';

/** The support address the SaaS embeds beside spa-config (base/spa.py, `SUPPORT_EMAIL`; PUBLIC-F18). */
function embedSupport(email: string | null): void {
  document.getElementById(SUPPORT_EMAIL_ID)?.remove();
  if (email === null) return;
  const script = document.createElement('script');
  script.type = 'application/json';
  script.id = SUPPORT_EMAIL_ID;
  script.textContent = JSON.stringify(email);
  document.body.append(script);
}

beforeEach(() => embedSupport('help@erplora.test'));
afterEach(() => embedSupport(null));

type Options = Parameters<typeof mountAccountPage>[1];

async function mountError(query: string, options: Options = {}) {
  const { wrapper } = await mountAccountPage(LoginErrorPage, { path: `/login/error?${query}`, ...options });
  const primary = wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === 'login-error-action')!;
  const links = wrapper.findAll('[data-testid="login-error-links"] a').map((a) => [a.text(), a.attributes('href')]);
  return {
    wrapper,
    badge: () => wrapper.find('[data-testid="login-error-badge"]'),
    heading: () => wrapper.get('h2.auth-title').text(),
    message: () => wrapper.get('p.auth-lead').text(),
    primary: () => [primary.text(), primary.props('href')],
    links,
  };
}

describe('LoginErrorPage: the texts of each template', () => {
  it('invalid_hub: the sign-in link does not lead to a hub (400 of /hub-login/)', async () => {
    const page = await mountError('code=invalid_hub');
    expect(page.badge().text()).toBe('400 · Invalid link');
    expect(page.heading()).toBe("This sign-in link doesn't lead to a hub");
    expect(page.message()).toBe(
      'The address it wanted to return to is not an ERPlora hub, so we stopped here. Open your hub and start the sign-in from its own screen.',
    );
    expect(page.primary()).toEqual(['Home', '/launch']);
    expect(page.links).toEqual([['Contact Support', 'mailto:help@erplora.test']]);
    expect(document.title).toBe('Invalid sign-in link - ERPlora Cloud');
  });

  it('not_a_member: names the host of the hub (never its business) and links back to it', async () => {
    const page = await mountError('code=not_a_member&hub=a', { session: SIGNED_IN });
    expect(page.badge().text()).toBe('403 · No access');
    expect(page.heading()).toBe("You don't have access to this hub");
    expect(page.message()).toBe(
      'This account is not a member of a.localhost:8000. Ask whoever manages that hub to invite you, or sign in with the account that has access.',
    );
    expect(page.primary()).toEqual(['Home', '/launch']);
    expect(page.links).toEqual([
      ['Back to the hub', 'http://a.localhost:8000/'],
      ['Contact Support', 'mailto:help@erplora.test'],
    ]);
    expect(document.title).toBe('No access to this hub - ERPlora Cloud');
  });

  it('not_a_member with something that is no hub slug says the link is invalid, echoing nothing', async () => {
    const page = await mountError(`code=not_a_member&hub=${encodeURIComponent('evil.example/x')}`);
    expect(page.heading()).toBe("This sign-in link doesn't lead to a hub");
    expect(page.wrapper.text()).not.toContain('evil');
  });

  it('not_a_member names a hub that starts with a digit: one DNS label, the rule of live.slugs', async () => {
    const page = await mountError('code=not_a_member&hub=0day');
    expect(page.heading()).toBe("You don't have access to this hub");
    expect(page.message()).toContain('0day.localhost:8000');
  });

  it.each(['abc-', '-abc', 'ab', 'a'.repeat(64)])('not_a_member with %s (no DNS label) says the link is invalid', async (hub) => {
    const page = await mountError(`code=not_a_member&hub=${hub}`);
    expect(page.heading()).toBe("This sign-in link doesn't lead to a hub");
    expect(page.wrapper.text()).not.toContain('.localhost');
  });

  it('authentication_error: Google failed; back to the sign-in', async () => {
    const page = await mountError('code=authentication_error');
    expect(page.heading()).toBe('We could not sign you in with Google');
    expect(page.message()).toBe(
      'Something went wrong while signing in with Google. Try again, or sign in with your email and password.',
    );
    expect(page.primary()).toEqual(['Back to sign in', '/launch']);
  });

  it('login_cancelled: the Google sign-in was cancelled; back to the sign-in', async () => {
    const page = await mountError('code=login_cancelled');
    expect(page.heading()).toBe('Sign-in cancelled');
    expect(page.message()).toBe(
      'You cancelled signing in with Google. Try again, or sign in with your email and password.',
    );
    expect(page.primary()).toEqual(['Back to sign in', '/launch']);
    expect(document.title).toBe('Sign-in cancelled - ERPlora Cloud');
  });

  it('google_link_refused: Google is linked by signing in with it; back home (the launcher, signed in)', async () => {
    const page = await mountError('code=google_link_refused&next=%2Faccount%2Fsecurity', { session: SIGNED_IN });
    expect(page.badge().exists()).toBe(false);
    expect(page.heading()).toBe('Google was not linked');
    expect(page.message()).toBe('Google can only be linked by signing in with the Google account of your email.');
    expect(page.primary()).toEqual(['Home', '/launch']);
    expect(page.links).toEqual([]);
    expect(document.title).toBe('Google was not linked - ERPlora Cloud');
  });

  it.each(['', 'code=', 'code=nope', 'code=google_no_account&email=stranger%40gmail.com'])(
    'a code it does not know (or without what it needs) is a failed Google sign-in, echoing nothing (%s)',
    async (query) => {
      const page = await mountError(query);
      expect(page.heading()).toBe('We could not sign you in with Google');
      expect(page.wrapper.text()).not.toContain('stranger');
    },
  );
});

describe('LoginErrorPage: the way back', () => {
  it('«Contact Support» writes to the support address of the SaaS, and without one offers no address (PUBLIC-F18)', async () => {
    embedSupport(null);
    const page = await mountError('code=invalid_hub');
    expect(page.links).toEqual([]);
  });

  it('goes to the launcher when there is a session', async () => {
    const page = await mountError('code=authentication_error&next=%2Flaunch', { session: SIGNED_IN });
    expect(page.primary()).toEqual(['Back to sign in', '/launch']);
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/\\evil.example.com'])(
    'never carries a next that leaves the site (%s)',
    async (next) => {
      const page = await mountError(`code=login_cancelled&next=${encodeURIComponent(next)}`);
      expect(page.primary()).toEqual(['Back to sign in', '/launch']);
    },
  );

  it('keeps the jump to a hub as next (the sign-in goes on to it)', async () => {
    const next = '/hub-login/?hub=a&next=/sales/';
    const page = await mountError(`code=authentication_error&next=${encodeURIComponent(next)}`);
    expect(page.primary()).toEqual(['Back to sign in', `/launch?next=${encodeURIComponent(next)}`]);
  });
});

describe('LoginErrorPage: in Spanish, with the translations of the templates', () => {
  it('google_link_refused', async () => {
    const page = await mountError('code=google_link_refused', { session: SIGNED_IN, locale: 'es' });
    expect(page.heading()).toBe('Google no se ha vinculado');
    expect(page.message()).toBe('Google solo se vincula entrando con la cuenta de Google de tu correo.');
    expect(page.primary()).toEqual(['Inicio', '/launch']);
  });

  it('not_a_member', async () => {
    const page = await mountError('code=not_a_member&hub=a', { locale: 'es' });
    expect(page.badge().text()).toBe('403 · Sin acceso');
    expect(page.heading()).toBe('No tienes acceso a este hub');
    expect(page.message()).toBe(
      'Esta cuenta no es miembro de a.localhost:8000. Pide a quien gestiona ese hub que te invite, o entra con la cuenta que sí tiene acceso.',
    );
    expect(page.primary()).toEqual(['Inicio', '/launch']);
    expect(page.links.map(([text]) => text)).toEqual(['Volver al hub', 'Contactar Soporte']);
  });
});
