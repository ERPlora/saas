// Google's notice of reCAPTCHA Enterprise under every sign-in form that sends its token (accounts/frontend/recaptcha.ts):
// the badge Google paints is hidden, which its terms allow only with this text where the person is (reCAPTCHA FAQ).
// Showing it also loads Google's script, so it watches the page before the submit. Nothing without a site key.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetRecaptcha } from '../../../frontend/recaptcha';
import { mountAccountPage } from '../__tests__/mount-account-page';
import RecaptchaNotice from './RecaptchaNotice.vue';

afterEach(() => {
  resetRecaptcha();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const mountNotice = (siteKey: string, locale: 'en' | 'es' = 'en') =>
  mountAccountPage(RecaptchaNotice, { locale, props: { siteKey } });

describe('RecaptchaNotice', () => {
  it('says the form is protected by reCAPTCHA, with Google’s privacy policy and terms', async () => {
    vi.stubGlobal('grecaptcha', { enterprise: { ready: (callback: () => void) => callback(), execute: vi.fn() } });
    const { wrapper } = await mountNotice('site-key');

    const notice = wrapper.get('[data-testid="recaptcha-notice"]');
    expect(notice.text()).toBe(
      'This site is protected by reCAPTCHA and the Google Privacy Policy and Terms of Service apply.',
    );
    expect(notice.findAll('a').map((a) => [a.attributes('href'), a.text(), a.attributes('target')])).toEqual([
      ['https://policies.google.com/privacy', 'Privacy Policy', '_blank'],
      ['https://policies.google.com/terms', 'Terms of Service', '_blank'],
    ]);
  });

  it('speaks Spanish', async () => {
    vi.stubGlobal('grecaptcha', { enterprise: { ready: (callback: () => void) => callback(), execute: vi.fn() } });
    const { wrapper } = await mountNotice('site-key', 'es');

    expect(wrapper.get('[data-testid="recaptcha-notice"]').text()).toBe(
      'Este sitio está protegido por reCAPTCHA y se aplican la Política de Privacidad y las Condiciones del Servicio de Google.',
    );
  });

  /** The scripts the page would insert, kept out of happy-dom (it would fetch Google). */
  function inserted(): HTMLScriptElement[] {
    const scripts: HTMLScriptElement[] = [];
    vi.spyOn(document.head, 'append').mockImplementation((...nodes) => {
      scripts.push(...(nodes as HTMLScriptElement[]));
    });
    return scripts;
  }

  it('loads Google’s script with the site key as it shows', async () => {
    const scripts = inserted();

    await mountNotice('site-key');

    expect(scripts.map((script) => script.src)).toEqual(['https://www.google.com/recaptcha/enterprise.js?render=site-key']);
  });

  it('shows and loads nothing when reCAPTCHA is off', async () => {
    const scripts = inserted();

    const { wrapper } = await mountNotice('');

    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(false);
    expect(scripts).toEqual([]);
  });
});
