// The panel: the user menu (Account, Help, Sign out) and the surface the server keeps.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
vi.mock('@erplora/ui/components', async (original) => (await import('./__tests__/main-doubles')).componentsDouble(original));
vi.mock('@erplora/ui/sdk', async (original) => (await import('./__tests__/main-doubles')).sdkDouble(original));

import { ApiError, createAllauthClient } from '@erplora/ui/sdk';

import { assign, fakeShell, importBoot, main, ME, renderShellHtml, setUpMain, shellOptions } from './__tests__/main-boot';
import { sdk } from './__tests__/main-doubles';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..');

setUpMain();

describe('the panel', () => {
  /** The user menu's «Sign out», as the shell's App.vue calls it. */
  async function signOut(): Promise<void> {
    await shellOptions().userMenu!.logout!();
  }

  it('hands the shell the user menu: Account, Report a problem, Help at /help and Sign out', async () => {
    fakeShell();
    await main.boot({});
    const { userMenu } = shellOptions();
    expect(userMenu?.items).toEqual([
      { id: 'account', labelKey: 'saas.userMenu.account', icon: 'ion:person-outline', to: '/dashboard/account' },
      // ACCOUNTS-F38: nothing is sold there, so it shows on the app surfaces too.
      { id: 'report', labelKey: 'saas.userMenu.reportProblem', icon: 'ion:chatbubbles-outline', to: '/dashboard/report-a-problem' },
    ]);
    expect(userMenu?.helpPath).toBe('/help');
    expect(userMenu?.logout).toBeTypeOf('function');
  });

  it('signs out through allauth.headless (DELETE of the session), then loads the launcher, the sign-in', async () => {
    vi.mocked(sdk.auth.logout).mockResolvedValue({ authenticated: false, flows: [] });
    fakeShell();
    await main.boot({});
    expect(createAllauthClient).toHaveBeenCalledWith(expect.objectContaining({ csrfCookieName: 'csrftoken' }));
    await signOut();
    expect(sdk.auth.logout).toHaveBeenCalledOnce();
    // A full load: the next page embeds an empty session (and the server forgot the surface).
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('a sign out that fails rejects, so the shell shows its toast, and the page stays', async () => {
    vi.mocked(sdk.auth.logout).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    fakeShell();
    await main.boot({});
    await expect(signOut()).rejects.toThrow('Network error');
    expect(assign).not.toHaveBeenCalled();
  });

  it('a sign out the server did not honour (still signed in) rejects too', async () => {
    vi.mocked(sdk.auth.logout).mockResolvedValue({ authenticated: true, user: { id: 1, email: 'ana@example.com' } });
    fakeShell();
    await main.boot({});
    await expect(signOut()).rejects.toThrow('still signed in');
    expect(assign).not.toHaveBeenCalled();
  });

  it('trusts the script URLs of Stripe.js only while reCAPTCHA is off (spa-config names no site key)', async () => {
    fakeShell();
    await main.boot({});
    // The `default` Trusted Types policy admits these origins' script URLs and no other; the CSP's
    // `script-src` still decides page by page (the account surface's names no Stripe). reCAPTCHA is off by
    // default (the WAF on the load balancer and the attempt limits keep bots out): nothing of Google's.
    expect(shellOptions().trustedScriptOrigins).toEqual(['https://js.stripe.com']);
  });

  it('trusts reCAPTCHA’s two script paths too while it is on (spa-config.recaptchaSiteKey)', async () => {
    renderShellHtml(ME, { recaptchaSiteKey: 'site-key' });
    fakeShell();
    await main.boot({});
    // Our code inserts `www.google.com/recaptcha/enterprise.js`, which inserts its release from `www.gstatic.com`
    // (frontend/recaptcha.ts). reCAPTCHA by path only: nothing else of www.google.com or www.gstatic.com.
    expect(shellOptions().trustedScriptOrigins).toEqual([
      'https://js.stripe.com',
      'https://www.google.com/recaptcha/',
      'https://www.gstatic.com/recaptcha/',
    ]);
  });

  it('passes the shell the account surface the server keeps in the session (spa-config.surface)', async () => {
    renderShellHtml(ME, { surface: 'account' });
    fakeShell();
    await main.boot({});
    expect(shellOptions().surface).toBe('account');
  });

  it("otherwise leaves the surface to the shell's own detection (the Tauri bridge, the user agent, ?surface=)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().surface).toBeUndefined();
    renderShellHtml(ME, { surface: 'nonsense' });
    await main.boot({});
    expect(shellOptions().surface).toBeUndefined();
  });

  it("paints the AA contrast (primary #0e78ad with white, dark text on the dark one) and has no Home of the shell (the SaaS's landing is its own)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().contrast).toBe('aa');
    expect(shellOptions().home).toBeUndefined();
  });

  it("translates the user menu's Account in en and es (the entry's own catalogue, frontend/locale)", () => {
    const messages = importBoot.messages as Record<string, { saas: { userMenu: { account: string } } }>;
    expect([messages.en.saas.userMenu.account, messages.es.saas.userMenu.account]).toEqual(['Account', 'Cuenta']);
    const report = importBoot.messages as Record<string, { saas: { userMenu: { reportProblem: string } } }>;
    expect([report.en.saas.userMenu.reportProblem, report.es.saas.userMenu.reportProblem]).toEqual([
      'Report a problem',
      'Reportar un problema',
    ]);
  });

  it("keeps the entry's catalogue under `saas`, with the same keys in en and es; anything else only overrides the shell's own texts", () => {
    const read = (lang: string) => JSON.parse(readFileSync(join(HERE, 'locale', `${lang}.json`), 'utf8')) as object;
    const shell = JSON.parse(readFileSync(join(SAAS_DIR, 'packages', 'ui', 'src', 'shell', 'locales', 'en.json'), 'utf8')) as object;
    const keys = (value: unknown, prefix = ''): string[] =>
      typeof value === 'object' && value !== null
        ? Object.entries(value).flatMap(([key, child]) => keys(child, `${prefix}${key}.`))
        : [prefix.slice(0, -1)];
    expect(Object.keys(read('en'))).toEqual(['saas', 'notFound', 'notInApp']);
    expect(keys(read('es'))).toEqual(keys(read('en')));
    const overrides = keys(read('en')).filter((key) => !key.startsWith('saas.'));
    expect(overrides.filter((key) => !keys(shell).includes(key))).toEqual([]);
  });

  it("the panel's home is Businesses: the menu's brand, «not found» and «not in the app» lead there, never to the public `/` the SPA does not have", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().homePath).toBe('/dashboard/businesses');
  });

  it('a page that does not exist speaks of the panel, not of a hub', () => {
    const messages = importBoot.messages as Record<string, { notFound: { body: string; action: string }; notInApp: { action: string } }>;
    expect(messages.en.notFound.body).toBe(
      'The address you opened is not part of the panel. It may be an old or mistyped link: your businesses, billing and account are in the menu.',
    );
    expect(messages.es.notFound.body).toBe(
      'La dirección que has abierto no forma parte del panel. Puede ser un enlace antiguo o mal copiado: tus negocios, la facturación y tu cuenta están en el menú.',
    );
    expect([messages.en.notFound.action, messages.es.notFound.action]).toEqual(['Go to my businesses', 'Ir a mis negocios']);
    expect([messages.en.notInApp.action, messages.es.notInApp.action]).toEqual(['Go to my businesses', 'Ir a mis negocios']);
    for (const language of ['en', 'es']) expect(JSON.stringify(messages[language].notFound)).not.toMatch(/\bhub\b/);
  });
});
