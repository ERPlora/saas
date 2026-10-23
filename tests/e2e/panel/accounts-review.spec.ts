// flow: ACCOUNTS-F01 … ACCOUNTS-F24 (F06 aside: Google has no credentials here)
// The review of the `hecho` flows of «create the account, sign in, the second factor, the sessions, the profile and the
// preferences» (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-6): every screen of those flows in English AND in
// Spanish, at the three sizes of the migration (390×844, 834×1112, 1440×900). The flows themselves are played by
// accounts-flows, accounts-security and accounts-profile (in English); here each screen is checked in the language
// the person reads: the page says it (`<html lang>`), its title is the catalogue's text of that language, no text of
// the other language is left on screen (every catalogue of the panel, `accounts`, `hubs`, the shell and @erplora/ui),
// nothing scrolls sideways, and a capture `APP-ACCOUNTS-6-<flow>-<size>-<lang>` stays for the eye. Without a session
// the language is the browser's (`Accept-Language`); with one, the account's own (ACCOUNTS-F22).
// Accounts of this spec: `e2e-acc6-…@example.com`, removed before and after.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { createHmac } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page } from '@playwright/test';

import {
  djangoPrint,
  expect,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  signInThroughPage,
  submitSignInForm,
  test,
  waitForMailCode,
  waitForPasswordResetLink,
  watchPageErrors,
} from './fixtures';
import { PANEL_MFA_URL } from './project';

const PREFIX = 'e2e-acc6-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const LANGUAGES = [
  { lang: 'en', locale: 'en-US' },
  { lang: 'es', locale: 'es-ES' },
] as const;
type Lang = (typeof LANGUAGES)[number]['lang'];

// ── The catalogues of the panel, both languages ───────────────────────────────────────────────

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const COMPONENTS = join(SAAS_DIR, 'packages/ui/src/components');
const CATALOGUE_DIRS = [
  'accounts/frontend/locale',
  'hubs/frontend/locale',
  'frontend/locale',
  'packages/ui/src/shell/locales',
  'packages/ui/src/sdk/locales',
  ...readdirSync(COMPONENTS).map((name) => `packages/ui/src/components/${name}/locales`),
].filter((dir) => existsSync(join(SAAS_DIR, dir, 'en.json')));

function flatten(tree: Record<string, unknown>, prefix = '', into = new Map<string, string>()): Map<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') into.set(path, value);
    else if (value && typeof value === 'object') flatten(value as Record<string, unknown>, path, into);
  }
  return into;
}

function catalogue(lang: Lang): Map<string, string> {
  const all = new Map<string, string>();
  for (const dir of CATALOGUE_DIRS) flatten(JSON.parse(readFileSync(join(SAAS_DIR, dir, `${lang}.json`), 'utf8')), '', all);
  return all;
}

const CATALOGUES: Record<Lang, Map<string, string>> = { en: catalogue('en'), es: catalogue('es') };

/** The text of `key` in `lang`, as the panel shows it. */
function t(lang: Lang, key: string): string {
  const text = CATALOGUES[lang].get(key);
  if (text === undefined) throw new Error(`no ${lang} text for ${key}`);
  return text;
}

/**
 * The whole texts of the other language that a page in `lang` must not show: every message translated differently,
 * without placeholders, that is no text of `lang` itself (a word both languages share, «Email», is no clue).
 */
function foreignTexts(lang: Lang): string[] {
  const other: Lang = lang === 'en' ? 'es' : 'en';
  const own = new Set(CATALOGUES[lang].values());
  const found = new Set<string>();
  for (const [key, text] of CATALOGUES[other]) {
    const mine = CATALOGUES[lang].get(key);
    if (mine === undefined || mine === text || own.has(text) || text.length < 4 || /[{|]/.test(text)) continue;
    found.add(text);
  }
  return [...found];
}

const FOREIGN: Record<Lang, string[]> = { en: foreignTexts('en'), es: foreignTexts('es') };

/** Every visible text node of the page (through open shadow roots) that is a whole text of the other language. */
async function textsOfTheOtherLanguage(page: Page, lang: Lang): Promise<string[]> {
  return page.evaluate((foreign) => {
    const texts = new Set(foreign);
    const found = new Set<string>();
    const visit = (root: Node) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
      for (let node: Node | null = walker.currentNode; node; node = walker.nextNode()) {
        if (node.nodeType === Node.TEXT_NODE) {
          const text = node.textContent?.trim() ?? '';
          const parent = node.parentElement;
          if (texts.has(text) && parent?.checkVisibility({ opacityProperty: true, visibilityProperty: true })) found.add(text);
        } else if ((node as Element).shadowRoot) {
          visit((node as Element).shadowRoot as ShadowRoot);
        }
      }
    };
    visit(document.body);
    return [...found];
  }, FOREIGN[lang]);
}

// ── Accounts ──────────────────────────────────────────────────────────────────────────────────

const address = (name: string, lang: Lang) => `${PREFIX}${name}-${lang}-${Date.now()}@example.com`;

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** An account speaking `lang`, its address proven, as one that signed in before; `staff` makes it a superuser. */
function createAccount(email: string, lang: Lang, options: { staff?: boolean } = {}): { email: string; password: string } {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.${options.staff ? 'create_superuser' : 'create_user'}(email="${email}", password="${PASSWORD}", first_name="Lucía", last_name="Fernández", language="${lang}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

// ── The authenticator app, as the phone computes it (RFC 6238: SHA-1, 6 digits, 30 s) ─────────────

function base32(secret: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const char of secret.replace(/=+$/, '').toUpperCase()) {
    const value = alphabet.indexOf(char);
    if (value < 0) throw new Error(`not a base32 key: ${secret}`);
    bits += value.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let at = 0; at + 8 <= bits.length; at += 8) bytes.push(parseInt(bits.slice(at, at + 8), 2));
  return Buffer.from(bytes);
}

function codeAt(secret: string, counter: number): string {
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const hash = createHmac('sha1', base32(secret)).update(message).digest();
  const offset = hash[hash.length - 1] & 0xf;
  const number = ((hash[offset] & 0x7f) << 24) | (hash[offset + 1] << 16) | (hash[offset + 2] << 8) | hash[offset + 3];
  return String(number % 1_000_000).padStart(6, '0');
}

/** A code of the app the server takes now (±1 period) and was not given before: allauth refuses one twice. */
function freshCode(secret: string, used: Set<string>): string {
  const now = Math.floor(Date.now() / 30_000);
  for (const counter of [now, now + 1, now - 1]) {
    const code = codeAt(secret, counter);
    if (!used.has(code)) {
      used.add(code);
      return code;
    }
  }
  throw new Error('every code of this minute was given already');
}

// ── The review of one screen ──────────────────────────────────────────────────────────────────

/**
 * `ready` at each size, then the checks of every screen: the page says `lang`, no text of the other language,
 * no sideways scroll, and the capture `APP-ACCOUNTS-6-<flow>-<size>-<lang>`; back at 1440 after.
 */
async function review(page: Page, lang: Lang, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    await expect(page.locator('html'), `${flow} says its language`).toHaveAttribute('lang', new RegExp(`^${lang}\\b`));
    expect(await textsOfTheOtherLanguage(page, lang), `${flow} at ${size.name} in ${lang}: text of the other language`).toEqual([]);
    expect(await sidewaysScroll(page), `${flow} scrolls sideways at ${size.name} in ${lang}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-6-${flow}-${size.name}-${lang}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The user menu (`UserMenuPopover`): in the side menu, a drawer behind the topbar's menu button below `lg`. */
async function openUserMenu(page: Page): Promise<void> {
  const trigger = page.getByTestId('user-menu-trigger');
  await expect(trigger).toBeAttached();
  await settled(page);
  if (!(await trigger.isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(trigger).toBeVisible();
  }
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await trigger.click();
  await presented;
  await expect(page.getByTestId('user-menu-logout')).toBeVisible();
}

/** Closes whatever overlay is open (the user menu, a modal) and the side menu, so the next size starts clean. */
async function closeOverlays(page: Page): Promise<void> {
  await page.evaluate(async () => {
    for (const overlay of document.querySelectorAll<HTMLElement & { dismiss: () => Promise<boolean> }>('ion-popover, ion-modal')) {
      await overlay.dismiss();
    }
    const menu = document.querySelector<HTMLElement & { close: () => Promise<boolean> }>('ion-menu');
    await menu?.close();
  });
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

for (const { lang, locale } of LANGUAGES) {
  test.describe(`in ${lang}`, () => {
    test.use({ locale });

    test(`ACCOUNTS-F01 · ACCOUNTS-F02 · ACCOUNTS-F10 (${lang}): «Create account», a refused password and «Check your email», under the terms`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const email = address('signup', lang);

      await page.goto('/launch?tab=signup');
      await review(page, lang, 'ACCOUNTS-F01', async () => {
        await expect(page.getByTestId('login-submit')).toHaveText(t(lang, 'accounts.login.signUp'));
        await expect(page.getByText(t(lang, 'accounts.login.agree'))).toBeVisible();
      });
      await submitSignInForm(page, { email, password: email.split('@')[0] });
      await review(page, lang, 'ACCOUNTS-F01-refused', async () => {
        await expect(page.getByTestId('login-password')).toHaveClass(/ion-invalid/);
      });

      await submitSignInForm(page, { email, password: PASSWORD });
      await expect(page).toHaveURL(/\/verify-email$/);
      await review(page, lang, 'ACCOUNTS-F02', async () => {
        await expect(page.getByRole('heading', { name: t(lang, 'accounts.verifyEmail.title') })).toBeVisible();
        await expect(page.getByTestId('verify-email-resend')).toBeVisible();
      });
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F04 · ACCOUNTS-F11 (${lang}): a wrong password says so, and five stop the account`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('brake', lang), lang);

      await page.goto('/launch');
      await submitSignInForm(page, { email: account.email, password: 'not-the-password-26' });
      await review(page, lang, 'ACCOUNTS-F04', async () => {
        await expect(page.getByTestId('login-password')).toHaveClass(/ion-invalid/);
        await expect(page.getByTestId('login-submit')).toHaveText(t(lang, 'accounts.login.signIn'));
      });
      for (let attempt = 2; attempt <= 6; attempt += 1) {
        await submitSignInForm(page, { email: account.email, password: `not-the-password-${attempt}` });
        await expect(page.getByTestId('login-submit')).toBeEnabled();
      }
      await review(page, lang, 'ACCOUNTS-F11', async () => {
        await expect(page.getByTestId('login-form')).toContainText(lang === 'es' ? 'Demasiados intentos' : 'Too many');
      });
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F07 (${lang}): «Reset your password», the mail sent, the new password and a dead link`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('reset', lang), lang);

      await page.goto('/password/reset');
      await review(page, lang, 'ACCOUNTS-F07-request', async () => {
        await expect(page.getByText(t(lang, 'accounts.passwordReset.subtitle'))).toBeVisible();
      });
      const since = Date.now();
      await page.getByTestId('password-reset-email').locator('input').fill(account.email);
      await page.getByTestId('password-reset-submit').click();
      await review(page, lang, 'ACCOUNTS-F07-sent', async () => {
        await expect(page.getByTestId('password-reset-sent')).toBeVisible();
      });
      const link = await waitForPasswordResetLink(account.email, since);
      await page.goto(link);
      await review(page, lang, 'ACCOUNTS-F07-new', async () => {
        await expect(page.getByText(t(lang, 'accounts.passwordReset.newSubtitle'))).toBeVisible();
      });
      await page.getByTestId('password-reset-key-password').locator('input').fill('Pan-de-centeno-y-sal-2026');
      await page.getByTestId('password-reset-key-submit').click();
      await expect(page).toHaveURL(/\/launch\?notice=password_reset$/);
      await review(page, lang, 'ACCOUNTS-F07-done', async () => {
        await expect(page.getByTestId('login-notice')).toBeVisible();
      });
      await page.goto(link);
      await review(page, lang, 'ACCOUNTS-F07-dead', async () => {
        await expect(page.getByTestId('password-reset-key-invalid')).toHaveText(t(lang, 'accounts.passwordReset.invalidLink'));
      });
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F08 · ACCOUNTS-F09 · ACCOUNTS-F12 · ACCOUNTS-F18 · ACCOUNTS-F21 · ACCOUNTS-F22 · ACCOUNTS-F23 · ACCOUNTS-F24 (${lang}): the account's own pages and its menu`, async ({
      page,
      browser,
    }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('panel', lang), lang);
      await signIn(page.request, account);
      const phone = await browser.newContext({ baseURL: test.info().project.use.baseURL, locale });
      try {
        await signIn(phone.request, account);

        await page.goto('/account/profile');
        await review(page, lang, 'ACCOUNTS-F21', async () => {
          await expect(page.getByText(t(lang, 'accounts.account.profile.heading'), { exact: true })).toBeVisible();
          await expect(page.getByTestId('profile-first-name').locator('input')).toHaveValue('Lucía');
        });
        await page.goto('/account/preferences');
        await review(page, lang, 'ACCOUNTS-F22-F23', async () => {
          await expect(page.getByText(t(lang, 'accounts.account.preferences.appearance'), { exact: true })).toBeVisible();
          await expect(page.getByText(t(lang, 'accounts.account.preferences.hubAlerts'), { exact: true })).toBeVisible();
          // «Security, invoices and payments» cannot be turned off, yet the mails it names read as any text: only
          // its switch is dimmed, not its words (Ionic dims a disabled toggle whole, to 0.3).
          const alwaysOn = page.getByTestId('preferences-invoices');
          await expect(alwaysOn).toBeDisabled();
          expect(await alwaysOn.evaluate((toggle) => getComputedStyle(toggle).opacity), 'the always-on row is dimmed').toBe('1');
          expect(
            await alwaysOn.evaluate((toggle) => Number(getComputedStyle(toggle.shadowRoot?.querySelector('[part~="track"]') as Element).opacity)),
            'the always-on switch looks locked',
          ).toBeLessThan(1);
        });
        await page.goto('/account/security');
        await review(page, lang, 'ACCOUNTS-F18', async () => {
          await expect(page.getByText(t(lang, 'accounts.account.sessions.title'), { exact: true })).toBeVisible();
          await expect(page.getByTestId('sessions-row')).toHaveCount(2);
        });
        await review(page, lang, 'ACCOUNTS-F08', async () => {
          if (!(await page.getByTestId('password-current').isVisible())) await page.getByTestId('password-row-change').click();
          await expect(page.getByText(t(lang, 'accounts.account.password.title'))).toBeVisible();
          await expect(page.getByTestId('password-new')).toBeVisible();
        });
        await closeOverlays(page);
        await review(page, lang, 'ACCOUNTS-F09-F12-F24', async () => {
          await closeOverlays(page);
          await openUserMenu(page);
          await expect(page.getByTestId('user-menu-logout')).toHaveText(t(lang, 'userMenu.logout'));
          await expect(page.getByTestId('user-menu-theme')).toBeVisible();
        });
      } finally {
        await phone.close();
      }
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F13 · ACCOUNTS-F19 · ACCOUNTS-F10 (${lang}): the admin's accounts, an account's page and its sessions`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const staff = createAccount(address('admin', lang), lang, { staff: true });
      await signIn(page.request, staff);
      const id = djangoPrint(
        `from django.contrib.auth import get_user_model\nprint(get_user_model().objects.get(email="${staff.email}").pk)`,
      );

      await page.goto(`/admin/accounts/user/?q=${encodeURIComponent(PREFIX)}`);
      await review(page, lang, 'ACCOUNTS-F13', async () => {
        await expect(page.locator('#changelist')).toContainText(staff.email);
      });
      await page.goto(`/admin/accounts/user/${id}/change/`);
      await review(page, lang, 'ACCOUNTS-F10-admin', async () => {
        await expect(page.locator('#content-main')).toContainText(lang === 'es' ? 'Términos y privacidad' : 'Terms and privacy');
      });
      await page.goto('/admin/usersessions/usersession/');
      await review(page, lang, 'ACCOUNTS-F19', async () => {
        await expect(page.locator('#changelist')).toContainText(staff.email);
      });
      expect(errors).toEqual([]);
    });

    test.describe('with the second factor on', () => {
      test.use({ baseURL: PANEL_MFA_URL });

      test(`ACCOUNTS-F14 · ACCOUNTS-F15 · ACCOUNTS-F16 · ACCOUNTS-F17 · ACCOUNTS-F05 (${lang}): the app set up, its codes, the trusted browsers and its code at the sign-in`, async ({
        page,
      }) => {
        const errors = watchPageErrors(page);
        const account = createAccount(address('mfa', lang), lang);
        const used = new Set<string>();
        await signIn(page.request, account);

        await page.goto('/account/security');
        await review(page, lang, 'ACCOUNTS-F15-off', async () => {
          await expect(page.getByTestId('two-factor-state')).toHaveText(t(lang, 'accounts.twoFactor.off'));
        });
        await page.getByTestId('two-factor-manage').click();
        await expect(page).toHaveURL(/\/2fa$/);
        await page.getByTestId('totp-set-up').click();
        await review(page, lang, 'ACCOUNTS-F14-set-up', async () => {
          await expect(page.getByTestId('totp-qr')).toBeVisible();
          await expect(page.getByText(t(lang, 'accounts.twoFactor.activate.title'))).toBeVisible();
        });
        const secret = (await page.locator('.auth-secret').textContent())?.trim() ?? '';
        await page.getByTestId('activate-form').getByTestId('code').locator('input').fill(freshCode(secret, used));
        await page.getByTestId('activate-submit').click();
        await review(page, lang, 'ACCOUNTS-F14-codes', async () => {
          await expect(page.getByTestId('codes-view')).toBeVisible();
          await expect(page.getByTestId('codes-list')).toBeVisible();
        });
        await page.getByTestId('codes-generate').click();
        await review(page, lang, 'ACCOUNTS-F16-regenerate', async () => {
          await expect(page.getByTestId('regenerate-view')).toBeVisible();
          await expect(page.getByText(t(lang, 'accounts.twoFactor.regenerate.title'))).toBeVisible();
        });
        await page.getByTestId('regenerate-cancel').click();
        await page.getByTestId('codes-back').click();
        await review(page, lang, 'ACCOUNTS-F15-F17', async () => {
          await expect(page.getByTestId('totp-pill')).toHaveText(t(lang, 'accounts.twoFactor.on'));
          await expect(page.getByTestId('trust-section')).toContainText(t(lang, 'accounts.twoFactor.trusted.title'));
        });
        await page.getByTestId('trust-revoke').click();
        await review(page, lang, 'ACCOUNTS-F17-revoked', async () => {
          await expect(page.getByTestId('trust-done')).toBeVisible();
        });
        await page.getByTestId('totp-turn-off').click();
        await review(page, lang, 'ACCOUNTS-F16-turn-off', async () => {
          await expect(page.getByTestId('deactivate-view')).toBeVisible();
          await expect(page.getByText(t(lang, 'accounts.twoFactor.deactivate.title'))).toBeVisible();
        });
        await page.getByTestId('deactivate-keep').click();
        await page.goto('/account/security');
        await review(page, lang, 'ACCOUNTS-F15-on', async () => {
          await expect(page.getByTestId('two-factor-state')).toHaveText(t(lang, 'accounts.twoFactor.on'));
        });

        // The next sign-in asks for the app's code after the password and the mailed one.
        await page.context().clearCookies();
        await page.goto('/launch');
        const since = Date.now();
        await submitSignInForm(page, account);
        await expect(page).toHaveURL(/\/verify-email(\?|$)/);
        await page.getByTestId('code').locator('input').fill(await waitForMailCode(account.email, since));
        await page.getByTestId('verify-email-submit').click();
        await expect(page).toHaveURL(/\/2fa\/authenticate(\?|$)/);
        await review(page, lang, 'ACCOUNTS-F05', async () => {
          await expect(page.getByTestId('mfa-form')).toBeVisible();
          await expect(page.getByTestId('mfa-trust')).toBeVisible();
        });
        await page.getByTestId('code').locator('input').fill(freshCode(secret, used));
        await page.getByTestId('mfa-submit').click();
        await expect(page).not.toHaveURL(/\/2fa\/authenticate(\?|$)/);
        expect(errors).toEqual([]);
      });

      test(`ACCOUNTS-F20 (${lang}): the staff without the app are taken from the admin to set it up`, async ({ page }) => {
        const errors = watchPageErrors(page);
        const staff = createAccount(address('staff', lang), lang, { staff: true });
        await page.goto('/launch');
        await signInThroughPage(page, staff);

        await page.goto('/admin/accounts/user/');
        await expect(page).toHaveURL(/\/2fa\?next=\/admin\/accounts\/user\/$/);
        await review(page, lang, 'ACCOUNTS-F20', async () => {
          await expect(page.getByTestId('mfa-required')).toHaveText(t(lang, 'accounts.twoFactor.requiredToContinue'));
          await expect(page.getByTestId('totp-section')).toBeVisible();
        });
        expect(errors).toEqual([]);
      });
    });
  });
}
