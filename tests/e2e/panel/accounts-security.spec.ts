// The flows of «the second factor, the trusted browsers and the open sessions» (accounts/WORKBOOK.md, MIGRATION-TASK
// APP-ACCOUNTS-2) on their screens, at the three sizes of the migration (390×844, 834×1112, 1440×900). The second
// factor is off by default in phase 1 (ACCOUNTS_MFA_ENABLED): its flows play on the panel's twin with it on
// (`PANEL_MFA_URL`, panel/project.ts), the sessions and the admin's «Close sessions» on the panel as production has it.
// The codes of the authenticator app are computed here from the key the setup page shows (RFC 6238, as the phone
// does); the mailed codes are read from the panel's mail folder: nothing is played. Each test names its flow by its
// registry key; in accounts/WORKBOOK.md: G87=F14, G116=F15, G89=F16, G88=F05, G23=F17, G94=F18, G09=F19, G90=F20.
// Accounts of this spec: `e2e-acc2-…@example.com`, removed before and after.
import { createHmac } from 'node:crypto';

import { type APIRequestContext, type Browser, type Page } from '@playwright/test';

import {
  djangoPrint,
  expect,
  sessionOf,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  signInThroughPage,
  test,
  watchPageErrors,
} from './fixtures';
import { PANEL_MFA_URL, PANEL_URL } from './project';

const PREFIX = 'e2e-acc2-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const SIGN_OUT_API = '/_allauth/browser/v1/auth/session';

/** A fresh address of this spec, never used before. */
const address = (name: string) => `${PREFIX}${name}-${Date.now()}@example.com`;

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** An account with its address proven, as one that signed in before; `staff` makes it a platform administrator. */
function createAccount(email: string, options: { staff?: boolean } = {}): { email: string; password: string } {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.${options.staff ? 'create_superuser' : 'create_user'}(email="${email}", password="${PASSWORD}")`,
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

// ── Pages ─────────────────────────────────────────────────────────────────────────────────────

/** `ready` at each size: no sideways scroll and a capture `APP-ACCOUNTS-2-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-2-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** Signs `request`'s session out (allauth.headless), with Django's CSRF token from its cookies. */
async function signOut(request: APIRequestContext): Promise<void> {
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
  const response = await request.delete(SIGN_OUT_API, { headers: { 'X-CSRFToken': csrf } });
  expect(response.status(), `DELETE ${SIGN_OUT_API}`).toBe(401);
}

/** The password, the code mailed to the account and, with the app on, its code on /2fa/authenticate. */
async function signInWithTheApp(
  page: Page,
  account: { email: string; password: string },
  secret: string,
  used: Set<string>,
  options: { trust?: boolean } = {},
): Promise<void> {
  await page.goto('/launch');
  await signInThroughPage(page, account);
  await expect(page).toHaveURL(/\/2fa\/authenticate(\?|$)/);
  if (options.trust) await page.getByTestId('mfa-trust').click();
  await page.getByTestId('code').locator('input').fill(freshCode(secret, used));
  await page.getByTestId('mfa-submit').click();
  await expect(page).not.toHaveURL(/\/2fa\/authenticate(\?|$)/);
}

/** Sets the app up on /2fa (the account signed in a moment ago: no «Confirm it's you»); returns its key. */
async function setUpTheApp(page: Page, used: Set<string>): Promise<string> {
  await page.getByTestId('totp-set-up').click();
  await expect(page.getByTestId('totp-qr')).toBeVisible();
  const secret = (await page.locator('.auth-secret').textContent())?.trim() ?? '';
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await page.getByTestId('activate-form').getByTestId('code').locator('input').fill(freshCode(secret, used));
  await page.getByTestId('activate-submit').click();
  await expect(page.getByTestId('codes-view')).toBeVisible();
  return secret;
}

async function newContextOn(browser: Browser, baseURL: string) {
  return browser.newContext({ baseURL, locale: 'en-US' });
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test.describe('the second factor (the panel with ACCOUNTS_MFA_ENABLED on)', () => {
  test.use({ baseURL: PANEL_MFA_URL });

  test('ACCOUNTS-G87 (F14): the authenticator app is set up from Security with its key, and the ten recovery codes are shown once and downloaded', async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('setup'));
    const used = new Set<string>();
    await signIn(page.request, account);
    await page.goto('/account/security');
    await expect(page.getByTestId('two-factor-state')).toHaveText('Off');
    await page.getByTestId('two-factor-manage').click();
    await expect(page).toHaveURL(/\/2fa$/);
    await page.getByTestId('totp-set-up').click();
    await expect(page.getByTestId('activate-cant-scan')).toHaveText("Can't scan? Enter this key by hand:");
    await atEverySize(page, 'G87-setup', async () => {
      await expect(page.getByTestId('totp-qr')).toBeVisible();
    });
    await page.getByTestId('activate-cancel').click();
    const secret = await setUpTheApp(page, used);
    await expect(page.getByTestId('codes-count')).toHaveText('10 of 10 unused');
    expect((await page.getByTestId('codes-list').textContent())?.trim().split('\n')).toHaveLength(10);
    const download = page.waitForEvent('download');
    await page.getByTestId('codes-download').click();
    expect((await download).suggestedFilename()).toBe('erplora-recovery-codes.txt');
    await atEverySize(page, 'G87', async () => {
      await expect(page.getByTestId('codes-list')).toBeVisible();
    });
    expect(secret).not.toBe('');
    expect(errors).toEqual([]);
  });

  test('ACCOUNTS-G116 (F15): Security says whether the second factor is on, and «Manage» leads to it', async ({ page }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('state'));
    const used = new Set<string>();
    await signIn(page.request, account);
    await page.goto('/2fa');
    await setUpTheApp(page, used);
    await page.goto('/account/security');
    await expect(page.getByTestId('two-factor-state')).toHaveText('On');
    await expect(page.getByTestId('two-factor-manage')).toContainText('Manage');
    await atEverySize(page, 'G116', async () => {
      await expect(page.getByTestId('two-factor')).toBeVisible();
    });
    await page.getByTestId('two-factor-manage').click();
    await expect(page.getByTestId('totp-pill')).toHaveText('On');
    await expect(page.getByTestId('recovery-section')).toContainText('10 unused');
    expect(errors).toEqual([]);
  });

  test('ACCOUNTS-G88 (F05): after the password and the mailed code, the app’s code; «Trust this browser» skips it next time, here only', async ({
    page,
    browser,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('trust'));
    const used = new Set<string>();
    await signIn(page.request, account);
    await page.goto('/2fa');
    const secret = await setUpTheApp(page, used);
    await signOut(page.request);

    await page.goto('/launch');
    await signInThroughPage(page, account);
    await expect(page).toHaveURL(/\/2fa\/authenticate(\?|$)/);
    await expect(page.getByTestId('mfa-trust')).toContainText('Trust this browser for 14 days');
    await atEverySize(page, 'G88', async () => {
      await expect(page.getByTestId('mfa-form')).toBeVisible();
    });
    // A wrong code says so under the field and keeps the login waiting.
    const right = freshCode(secret, used);
    const wrong = right === '000000' ? '111111' : '000000';
    await page.getByTestId('code').locator('input').fill(wrong);
    await page.getByTestId('mfa-submit').click();
    await expect(page.getByTestId('code')).toHaveClass(/ion-invalid/);
    await page.getByTestId('mfa-trust').click();
    await page.getByTestId('code').locator('input').fill(right);
    await page.getByTestId('mfa-submit').click();
    await expect(page).toHaveURL(/\/launch$/);
    expect((await sessionOf(page.request)).user).toMatchObject({ label: account.email });

    // Trusted: the next sign-in here asks the password and the mailed code only.
    await signOut(page.request);
    await page.goto('/launch');
    await signInThroughPage(page, account);
    await expect(page).toHaveURL(/\/launch$/);
    expect((await sessionOf(page.request)).user).toMatchObject({ label: account.email });

    // Another browser is still asked for the app's code.
    const other = await newContextOn(browser, PANEL_MFA_URL);
    try {
      const otherPage = await other.newPage();
      await otherPage.goto('/launch');
      await signInThroughPage(otherPage, account);
      await expect(otherPage).toHaveURL(/\/2fa\/authenticate(\?|$)/);
    } finally {
      await other.close();
    }
    expect(errors).toEqual([]);
  });

  test('ACCOUNTS-G23 (F17): the settings say until when this browser is trusted, and «Stop trusting all browsers» asks for the app’s code again', async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('forget'));
    const used = new Set<string>();
    await signIn(page.request, account);
    await page.goto('/2fa');
    const secret = await setUpTheApp(page, used);
    await signOut(page.request);
    await signInWithTheApp(page, account, secret, used, { trust: true });

    await page.goto('/2fa');
    await expect(page.getByTestId('trust-this')).toContainText('This browser is trusted until');
    await atEverySize(page, 'G23', async () => {
      await expect(page.getByTestId('trust-section')).toBeVisible();
    });
    await page.getByTestId('trust-revoke').click();
    await expect(page.getByTestId('trust-this')).toHaveText('This browser is not trusted.');
    await expect(page.getByTestId('trust-done')).toHaveText(
      'No browser is trusted now: each one will ask for the code from your app at its next sign-in.',
    );
    await atEverySize(page, 'G23-revoked', async () => {
      await expect(page.getByTestId('trust-done')).toBeVisible();
    });

    await signOut(page.request);
    await page.goto('/launch');
    await signInThroughPage(page, account);
    await expect(page).toHaveURL(/\/2fa\/authenticate(\?|$)/);
    expect(errors).toEqual([]);
  });

  test('ACCOUNTS-G89 (F16): new recovery codes replace the old ones, and turning the app off leaves the mailed code', async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('off'));
    const used = new Set<string>();
    await signIn(page.request, account);
    await page.goto('/2fa');
    await setUpTheApp(page, used);
    const first = (await page.getByTestId('codes-list').textContent())?.trim();
    await page.getByTestId('codes-generate').click();
    await expect(page.getByTestId('regenerate-lead')).toHaveText('This replaces your 10 unused codes.');
    await page.getByTestId('regenerate-submit').click();
    await expect(page.getByTestId('codes-list')).toBeVisible();
    expect((await page.getByTestId('codes-list').textContent())?.trim()).not.toBe(first);
    await page.getByTestId('codes-back').click();

    await page.getByTestId('totp-turn-off').click();
    await expect(page.getByTestId('deactivate-lead')).toHaveText('You will sign in with your password and the code we email you.');
    await atEverySize(page, 'G89', async () => {
      await expect(page.getByTestId('deactivate-view')).toBeVisible();
    });
    await page.getByTestId('deactivate-submit').click();
    await expect(page.getByTestId('totp-pill')).toHaveText('Off');

    // Without the app, the sign-in is the password and the mailed code again.
    await signOut(page.request);
    await page.goto('/launch');
    await signInThroughPage(page, account);
    await expect(page).toHaveURL(/\/launch$/);
    expect(errors).toEqual([]);
  });

  test('ACCOUNTS-G90 (F20): the staff without the app are taken from the admin to set it up, and «Continue» brings them back', async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    const staff = createAccount(address('staff'), { staff: true });
    const used = new Set<string>();
    await signIn(page.request, staff);

    await page.goto('/admin/accounts/user/');
    await expect(page).toHaveURL(/\/2fa\?next=\/admin\/accounts\/user\/$/);
    await expect(page.getByTestId('mfa-required')).toHaveText('Turn on the authenticator app to continue.');
    await atEverySize(page, 'G90', async () => {
      await expect(page.getByTestId('totp-section')).toBeVisible();
    });
    await setUpTheApp(page, used);
    await page.getByTestId('codes-back').click();
    await page.getByTestId('mfa-continue').click();
    await expect(page).toHaveURL(/\/admin\/accounts\/user\/$/);
    await expect(page.locator('#changelist')).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe('the open sessions (the panel as production has it)', () => {
  test.use({ baseURL: PANEL_URL });

  test('ACCOUNTS-G94 (F18): Security lists the open sessions, this one first; one is closed, then all the others', async ({
    page,
    browser,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(address('sessions'));
    await signIn(page.request, account);
    const phone = await newContextOn(browser, PANEL_URL);
    const tablet = await newContextOn(browser, PANEL_URL);
    try {
      await signIn(phone.request, account);
      await signIn(tablet.request, account);
      await page.goto('/account/security');
      const rows = page.getByTestId('sessions-row');
      await expect(rows).toHaveCount(3);
      await expect(rows.first()).toContainText('This session');
      await atEverySize(page, 'G94', async () => {
        await expect(rows.first()).toBeVisible();
      });

      // One: the phone, with its own button (a browser: no question asked).
      const phoneKey = (await phone.storageState()).cookies.find((cookie) => cookie.name === 'sessionid')?.value;
      const phoneRow = djangoPrint(
        `from allauth.usersessions.models import UserSession;print(UserSession.objects.get(session_key="${phoneKey}").pk)`,
      );
      await page.getByTestId(`sessions-row-${phoneRow}-close`).click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Session closed on' })).toBeVisible();
      await expect(rows).toHaveCount(2);
      expect((await sessionOf(phone.request)).user).toBeNull();
      expect((await sessionOf(tablet.request)).user).not.toBeNull();

      // All the others: the tablet, after the question.
      await page.getByTestId('sessions-close-others').click();
      await expect(page.getByTestId('sessions-close-others-dialog')).toContainText('1 session will be closed');
      await page.getByTestId('sessions-close-others-dialog-submit').click();
      await expect(rows).toHaveCount(1);
      expect((await sessionOf(tablet.request)).user).toBeNull();
      expect((await sessionOf(page.request)).user).toMatchObject({ label: account.email });
    } finally {
      await phone.close();
      await tablet.close();
    }
    expect(errors).toEqual([]);
  });

  test('the sideways-scroll reader also catches a page that is no Ionic page: the admin, wider than the screen (the check of the check, ACCOUNTS-G09)', async ({
    page,
  }) => {
    const staff = createAccount(address('reader'), { staff: true });
    await signIn(page.request, staff);
    await page.setViewportSize({ width: 834, height: 1112 });
    await page.goto('/admin/accounts/user/');
    await expect(page.locator('#changelist')).toBeVisible();
    expect(await sidewaysScroll(page)).toEqual([]);
    // The «Action» select is as wide as its longest option: the label F19 had first pushed the page past 834 px.
    await page.evaluate(() => {
      const option = document.createElement('option');
      option.textContent = 'Close all their sessions and the trust of their browsers (here and in their businesses)';
      document.querySelector('select[name="action"]')?.append(option);
    });
    expect((await sidewaysScroll(page)).join()).toMatch(/^document \d+ > \d+$/);
  });

  test('ACCOUNTS-G09 (F19): a superuser closes every session of an account from the admin', async ({ page, browser }) => {
    const errors = watchPageErrors(page);
    const staff = createAccount(address('root'), { staff: true });
    const account = createAccount(address('incident'));
    const laptop = await newContextOn(browser, PANEL_URL);
    try {
      await signIn(laptop.request, account);
      await signIn(page.request, staff);
      await page.goto(`/admin/accounts/user/?q=${encodeURIComponent(account.email)}`);
      await page.locator('input.action-select').first().check();
      await page.locator('select[name="action"]').selectOption('close_sessions');
      await page.locator('button[name="index"]').click();
      await expect(page.locator('.messagelist .success')).toHaveText('Sessions closed: 1.');
      await atEverySize(page, 'G09', async () => {
        await expect(page.locator('.messagelist')).toBeVisible();
      });
      expect((await sessionOf(laptop.request)).user).toBeNull();
    } finally {
      await laptop.close();
    }
    expect(errors).toEqual([]);
  });
});
