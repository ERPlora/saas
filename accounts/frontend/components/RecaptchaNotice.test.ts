// Google's notice of reCAPTCHA Enterprise under every sign-in form that sends its token (accounts/frontend/recaptcha.ts):
// the badge Google paints is hidden, which its terms allow only with this text where the person is (reCAPTCHA FAQ).
// Showing it also loads Google's script, so it watches the page before the submit. Nothing without a site key.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetRecaptcha } from '../../../frontend/recaptcha';
import { mountAccountPage } from '../__tests__/mount-account-page';
import RecaptchaNotice from './RecaptchaNotice.vue';

afterEach(() => {
  resetRecaptcha();
  // The style that hides Google's badge, put in the real head by the tests that do not hold `append`.
  document.head.querySelectorAll('style[data-recaptcha-badge]').forEach((style) => style.remove());
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

  /** What the page would insert in its head, kept out of happy-dom (it would fetch Google). */
  function inserted(): Node[] {
    const nodes: Node[] = [];
    vi.spyOn(document.head, 'append').mockImplementation((...given) => {
      nodes.push(...(given as Node[]));
    });
    return nodes;
  }

  const scriptsOf = (nodes: Node[]) => nodes.filter((node): node is HTMLScriptElement => node instanceof HTMLScriptElement);
  const stylesOf = (nodes: Node[]) => nodes.filter((node): node is HTMLStyleElement => node instanceof HTMLStyleElement);

  it('loads Google’s script with the site key as it shows', async () => {
    const nodes = inserted();

    await mountNotice('site-key');

    expect(scriptsOf(nodes).map((script) => script.src)).toEqual([
      'https://www.google.com/recaptcha/enterprise.js?render=site-key',
    ]);
  });

  it('hides Google’s badge only with Google’s script: no CSS of it in the bundle', async () => {
    const nodes = inserted();

    await mountNotice('site-key');

    expect(stylesOf(nodes).map((style) => style.textContent)).toEqual(['.grecaptcha-badge { visibility: hidden; }']);
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'RecaptchaNotice.vue'), 'utf8');
    expect(source).not.toContain('grecaptcha-badge');
  });

  it('shows and loads nothing when reCAPTCHA is off', async () => {
    const nodes = inserted();

    const { wrapper } = await mountNotice('');

    expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(false);
    expect(nodes).toEqual([]);
  });

  it('shows and loads nothing when the page names no site key (spa-config while reCAPTCHA is off, base/spa.py)', async () => {
    const config = document.createElement('script');
    config.id = 'spa-config';
    config.type = 'application/json';
    config.textContent = JSON.stringify({ csrfCookieName: 'csrftoken', lang: 'en' });
    document.body.append(config);
    const nodes = inserted();

    try {
      const { wrapper } = await mountAccountPage(RecaptchaNotice, {});

      expect(wrapper.find('[data-testid="recaptcha-notice"]').exists()).toBe(false);
      expect(nodes).toEqual([]);
    } finally {
      config.remove();
    }
  });
});
