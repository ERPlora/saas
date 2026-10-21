// The flows of «create the account, confirm the email, sign in, the password, sign out, the terms and the throttle»
// (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-1) on their screens, at the three sizes of the migration
// (390×844, 834×1112, 1440×900), against the panel's own Django: the codes and the reset links are read from its
// mail folder (project.ts), nothing is played. Each test names its flow in its title by its registry key; in
// accounts/WORKBOOK.md: G83=F01, G84=F02, G107=F03, G85=F04, G91=F07, G109=F08, G93=F09, G119=F10, G96=F11, G18=F13.
// Google (F06) and the authenticator app (F05) have no e2e: the panel's server has no Google credentials and the
// second factor is off in phase 1 (the WORKBOOK says why). Accounts of this spec: `e2e-acc1-…@example.com`,
// removed before and after (panel_seed.py's `clear` removes every `e2e-…@example.com` too).
import { type Page } from '@playwright/test';

import {
  djangoPrint,
  expect,
  sessionOf,
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
import { PANEL_URL } from './project';

const PREFIX = 'e2e-acc1-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

/** A fresh address of this spec, never used before (a throttle or a code of an earlier run never leaks in). */
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
function createAccount(email: string, options: { verified?: boolean; staff?: boolean } = {}): void {
  const { verified = true, staff = false } = options;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.${staff ? 'create_superuser' : 'create_user'}(email="${email}", password="${PASSWORD}")`,
      `EmailAddress.objects.create(user=user, email=user.email, verified=${verified ? 'True' : 'False'}, primary=True)`,
    ].join('\n'),
  );
}

/** What the account accepted (ACCOUNTS-G119): `terms_version privacy_version`, or `None None`. */
function acceptedVersions(email: string): string {
  return djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `u = get_user_model().objects.get(email="${email}")`,
      'print(u.terms_version, u.privacy_version, u.terms_accepted_at is not None)',
    ].join('\n'),
  );
}

/** `ready` at each size: no sideways scroll and a capture `APP-ACCOUNTS-1-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-1-${key}-${size.name}`), fullPage: true });
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
  await trigger.click();
  await expect(page.getByTestId('user-menu-logout')).toBeVisible();
}

/** The page is on `path`, not merely naming it in its `next`. */
const onPath = (path: string) => (url: URL) => url.pathname === path;

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test('ACCOUNTS-G83: a new address creates its account on «Create account», refused passwords say why, and the code opens the launcher', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const email = address('signup');

  await page.goto('/launch?tab=signup');
  await atEverySize(page, 'ACCOUNTS-G83', async () => {
    await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  });
  // The rules of the old sign-up (ERPlora/saas#2542): one like the address is refused under the password.
  await submitSignInForm(page, { email, password: email.split('@')[0] });
  await expect(page.getByTestId('login-password')).toContainText('The password is too similar to the email.');
  await expect(page).toHaveURL(/\/launch\?tab=signup$/);
  expect(djangoPrint(`from django.contrib.auth import get_user_model\nprint(get_user_model().objects.filter(email="${email}").exists())`)).toBe('False');

  const since = Date.now();
  await submitSignInForm(page, { email, password: PASSWORD });
  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.getByText(`We emailed a code to ${email}`)).toBeVisible();
  await page.getByTestId('code').locator('input').fill(await waitForMailCode(email, since));
  await page.getByTestId('verify-email-submit').click();

  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByRole('heading', { name: 'Create your business' })).toBeVisible();
  expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G84: the code that proves a new address, with «Send another code» when the mail is lost', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = address('code');

  await page.goto('/launch?tab=signup');
  await submitSignInForm(page, { email, password: PASSWORD });
  await expect(page).toHaveURL(/\/verify-email$/);
  await atEverySize(page, 'ACCOUNTS-G84', async () => {
    await expect(page.getByTestId('verify-email-form')).toBeVisible();
    await expect(page.getByTestId('verify-email-resend')).toBeVisible();
  });
  // allauth lets a new code go 10 s after the first one (`confirm_email`, 1/10s per address).
  await page.waitForTimeout(10_500);
  const since = Date.now();
  await page.getByTestId('verify-email-resend').click();
  const code = await waitForMailCode(email, since);
  // A wrong code says so under the input, and the right one still signs in.
  await page.getByTestId('code').locator('input').fill(code === '000000' ? '111111' : '000000');
  await page.getByTestId('verify-email-submit').click();
  await expect(page.getByTestId('code')).toHaveClass(/ion-invalid/);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();

  await expect(page).toHaveURL(/\/launch$/);
  expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G107: an address never proven asks for its code before the panel opens, and then goes where it was going', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const email = address('unproven');
  createAccount(email, { verified: false });

  // A page of the panel without a session: the sign-in, keeping where it was going.
  await page.goto('/account/profile');
  await expect(page).toHaveURL(/\/launch\?next=(%2F|\/)account(%2F|\/)profile$/);
  const since = Date.now();
  await submitSignInForm(page, { email, password: PASSWORD });
  await expect(page).toHaveURL(/\/verify-email\?next=/);
  await atEverySize(page, 'ACCOUNTS-G107', async () => {
    await expect(page.getByText(`We emailed a code to ${email}`)).toBeVisible();
  });
  expect((await sessionOf(page.request)).user).toBeNull();
  await page.getByTestId('code').locator('input').fill(await waitForMailCode(email, since));
  await page.getByTestId('verify-email-submit').click();

  await expect(page).toHaveURL(onPath('/account/profile'));
  expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G85: the email and the password, then the code mailed at every sign-in, lead to `next`', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = address('signin');
  createAccount(email);

  await page.goto('/launch?next=/account/security');
  await atEverySize(page, 'ACCOUNTS-G85', async () => {
    await expect(page.getByTestId('login-form')).toBeVisible();
    await expect(page.getByTestId('login-forgot')).toBeVisible();
  });
  await submitSignInForm(page, { email, password: 'not-the-password-26' });
  await expect(page.getByTestId('login-password')).toContainText('The email address and/or password you specified are not correct.');
  await signInThroughPage(page, { email, password: PASSWORD });

  await expect(page).toHaveURL(onPath('/account/security'));
  // Who signed in (ACCOUNTS-G20): the shell's account and /api/me name it.
  const session = await sessionOf(page.request);
  expect(session.user).toMatchObject({ label: email });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G91: «Forgot your password?» mails a link whose page shows the rules, refuses the same password and the old link', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const email = address('reset');
  createAccount(email);

  await page.goto('/launch');
  await page.getByTestId('login-forgot').click();
  await expect(page).toHaveURL(/\/password\/reset$/);
  await atEverySize(page, 'ACCOUNTS-G123', async () => {
    await expect(page.getByTestId('password-reset-form')).toBeVisible();
  });
  const since = Date.now();
  await page.getByTestId('password-reset-email').locator('input').fill(email);
  await page.getByTestId('password-reset-submit').click();
  await atEverySize(page, 'ACCOUNTS-G120', async () => {
    await expect(page.getByTestId('password-reset-sent')).toBeVisible();
  });

  const link = await waitForPasswordResetLink(email, since);
  await page.goto(link);
  const field = page.getByTestId('password-reset-key-password');
  await atEverySize(page, 'ACCOUNTS-G121', async () => {
    await expect(field).toContainText('At least 8 characters; better long, and without your email.');
  });
  // Today's password is not a new one (ERPlora/saas#2612).
  await field.locator('input').fill(PASSWORD);
  await page.getByTestId('password-reset-key-submit').click();
  await expect(field).toContainText('Your new password must be different from the current one.');
  const changed = 'Pan-de-centeno-y-sal-2026';
  await field.locator('input').fill(changed);
  await page.getByTestId('password-reset-key-submit').click();

  await expect(page).toHaveURL(/\/launch\?notice=password_reset$/);
  await atEverySize(page, 'ACCOUNTS-G122', async () => {
    await expect(page.getByTestId('login-notice')).toContainText('Your password has been changed successfully.');
  });
  // A used link is dead: its page says so and offers a new one.
  await page.goto(link);
  await expect(page.getByTestId('password-reset-key-invalid')).toContainText('This password reset link has expired or is not valid.');
  await expect(page.getByTestId('password-reset-key-request')).toBeVisible();

  await page.goto('/launch');
  await signInThroughPage(page, { email, password: changed });
  expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G109: «Change password» asks for the current one, refuses it as the new one, and ends the other sessions', async ({
  page,
  browser,
}) => {
  const errors = watchPageErrors(page);
  const email = address('change');
  createAccount(email);
  await signIn(page.request, { email, password: PASSWORD });
  const phone = await browser.newContext({ baseURL: PANEL_URL });
  try {
    await signIn(phone.request, { email, password: PASSWORD });
    await page.goto('/account/security');
    await page.getByTestId('password-row-change').click();
    await atEverySize(page, 'ACCOUNTS-G109', async () => {
      await expect(page.getByTestId('password-current')).toBeVisible();
      await expect(page.getByTestId('password-new')).toBeVisible();
    });
    await page.getByTestId('password-current').locator('input').fill(PASSWORD);
    await page.getByTestId('password-new').locator('input').fill(PASSWORD);
    await page.getByTestId('password-change-submit').click();
    await expect(page.getByTestId('password-new')).toContainText('Your new password must be different from the current one.');
    await page.getByTestId('password-new').locator('input').fill('Pan-de-centeno-y-sal-2026');
    await page.getByTestId('password-change-submit').click();
    await expect(page.locator('ion-toast').filter({ hasText: 'Password changed' })).toBeVisible();

    // This browser stays signed in; the other one is signed out.
    expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
    expect((await sessionOf(phone.request)).user).toBeNull();
  } finally {
    await phone.close();
  }
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G93: «Sign out» in the user menu ends the session and leaves the sign-in on screen', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = address('signout');
  createAccount(email);
  await signIn(page.request, { email, password: PASSWORD });

  await atEverySize(page, 'ACCOUNTS-G93', async () => {
    await page.goto('/account/profile');
    await openUserMenu(page);
  });
  await page.goto('/account/profile');
  await openUserMenu(page);
  await page.getByTestId('user-menu-logout').click();

  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByTestId('login-form')).toBeVisible();
  expect((await sessionOf(page.request)).user).toBeNull();
  // Back to a page of the panel: the sign-in again, not the account.
  await page.goto('/account/profile');
  await expect(page).toHaveURL(/\/launch\?next=/);
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G119: the sign-in says what continuing accepts, and the account keeps when and which versions', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = address('terms');
  createAccount(email);
  expect(acceptedVersions(email)).toBe('None None False');

  await page.goto('/launch');
  const foot = page.locator('.foot').filter({ hasText: 'By continuing you agree to our' });
  await atEverySize(page, 'ACCOUNTS-G119', async () => {
    await expect(foot).toBeVisible();
  });
  await expect(foot.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', /\/legal\/terms\/$/);
  await expect(foot.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', /\/legal\/privacy\/$/);
  await signInThroughPage(page, { email, password: PASSWORD });

  expect(acceptedVersions(email)).toBe('2026-10-13 2026-10-13 True');
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G96: five wrong passwords stop the account, also to the right one, with the same words for any address', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const email = address('throttle');
  createAccount(email);

  await page.goto('/launch');
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await submitSignInForm(page, { email, password: `a-guess-${attempt}-2026` });
    await expect(page.getByTestId('login-password')).toContainText('The email address and/or password you specified are not correct.');
  }
  await submitSignInForm(page, { email, password: PASSWORD });
  await atEverySize(page, 'ACCOUNTS-G96', async () => {
    await expect(page.getByRole('alert')).toContainText('Too many failed login attempts. Try again later.');
  });
  await expect(page).toHaveURL(/\/launch$/);
  expect((await sessionOf(page.request)).user).toBeNull();
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G18: the staff sees on an account’s page what it accepted, read only', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const staff = address('staff');
  const customer = address('customer');
  createAccount(staff, { staff: true });
  createAccount(customer);
  // The customer signs in once, somewhere else: that accepts today's texts.
  const elsewhere = await browser.newContext({ baseURL: PANEL_URL });
  try {
    await signIn(elsewhere.request, { email: customer, password: PASSWORD });
  } finally {
    await elsewhere.close();
  }
  await signIn(page.request, { email: staff, password: PASSWORD });
  const id = djangoPrint(`from django.contrib.auth import get_user_model\nprint(get_user_model().objects.get(email="${customer}").pk)`);

  await page.goto(`/admin/accounts/user/${id}/change/`);
  await atEverySize(page, 'ACCOUNTS-G18', async () => {
    await expect(page.getByRole('heading', { name: 'Terms and privacy' })).toBeVisible();
  });
  await expect(page.locator('.field-terms_version .readonly')).toHaveText('Oct. 13, 2026');
  await expect(page.locator('input[name="terms_version"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
