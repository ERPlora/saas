// flow: FIX-LAUNCH-TABS
// The sign-up and the password reset of the panel, end to end. The launcher's form has two strict tabs
// (FIX-LAUNCH-TABS): «Create account» creates the account of a new address, allauth mails a 6-digit code,
// /verify-email takes it and the launcher opens signed in: one code, never a second one (gh:hub#858);
// «Sign in» never creates one (gh:saas#1018). «Forgot your password?» mails a link, its key sets a new password on /password/reset/key/<key>, the
// sign-in says so and the account signs in with the new password and the code mailed at every sign-in.
// The mails are read from the panel's file backend (project.ts). Accounts of this spec: `e2e-signup-<time>`
// and `e2e-reset` at example.com, removed before and after (panel_seed.py's `clear` removes every
// `e2e-…@example.com` too).
import { type Page } from '@playwright/test';

import {
  djangoPrint,
  expect,
  sessionOf,
  settled,
  shot,
  sidewaysScroll,
  signInThroughPage,
  submitSignInForm,
  test,
  VIEWPORTS,
  waitForMailCode,
  waitForPasswordResetLink,
  watchPageErrors,
} from './fixtures';

/** A verified account whose password the reset changes (never the seeded owner's: other specs sign in with it). */
const RESET = { email: 'e2e-reset@example.com', password: 'e2e-panel' };
const NEW_PASSWORD = 'Reset-e2e-2026!';

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'users = get_user_model().objects',
      'users.filter(email__startswith="e2e-signup-", email__endswith="@example.com").delete()',
      `users.filter(email="${RESET.email}").delete()`,
    ].join('\n'),
  );
}

/** `RESET` with its address verified, as an account that already signed in once. */
function createResetAccount(): void {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${RESET.email}", password="${RESET.password}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
}

/**
 * The page on screen at 390, 834 and 1440 px (working rules §2.4), back at Playwright's size after: no
 * sideways scroll, and a screenshot of each (`<name>-<width>.png`). For the screens only a flow reaches
 * (a sign-up waiting for its code, a real reset key); the rest are in viewports.spec.ts.
 */
async function atEveryViewport(page: Page, name: string): Promise<void> {
  const size = page.viewportSize();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await settled(page);
    expect(await sidewaysScroll(page), `${name} scrolls sideways at ${viewport.width} px`).toEqual([]);
    await page.screenshot({ path: shot(`${name}-${viewport.width}`), fullPage: true });
  }
  if (size) await page.setViewportSize(size);
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test('«Sign in» with an unknown address creates nothing: the error of a wrong password, and the way to «Create account»', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const email = `e2e-signup-unknown-${Date.now()}@example.com`;

  await page.goto('/launch?next=/account');
  await submitSignInForm(page, { email, password: 'Signup-e2e-2026!' });
  await expect(page.getByTestId('login-password')).toContainText('The email address and/or password you specified are not correct.');
  await expect(page.getByTestId('login-error-signup')).toHaveText('First time here? Create your account');
  await expect(page).toHaveURL(/\/launch\?next=\/account$/);
  expect(hasAccount(email)).toBe(false);

  await page.getByTestId('login-error-signup').getByRole('button').click();
  await expect(page).toHaveURL(/\/launch\?next=(%2F|\/)account&tab=signup$/);
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await expect(page.getByTestId('login-error-signup')).toHaveCount(0);
  expect(errors).toEqual([]);
});

/** Whether an account holds `email` (the SaaS's side: no page shows it to a visitor). */
function hasAccount(email: string): boolean {
  return (
    djangoPrint(
      ['from django.contrib.auth import get_user_model', `print(get_user_model().objects.filter(email__iexact="${email}").exists())`].join(
        '\n',
      ),
    ) === 'True'
  );
}

/** The launcher's «Create account» tab, from its default «Sign in». */
async function openCreateAccount(page: Page): Promise<void> {
  await page.getByTestId('login-tab-signup').click();
  await expect(page).toHaveURL(/\/launch\?tab=signup$/);
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
}

test('a new address signs up on «Create account»: the one code mailed to it opens the launcher, signed in', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = `e2e-signup-${Date.now()}@example.com`;

  await page.goto('/launch');
  await openCreateAccount(page);
  const since = Date.now();
  await submitSignInForm(page, { email, password: 'Signup-e2e-2026!' });

  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.getByText(`We emailed a code to ${email}`)).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeHidden();
  // A new address can be sent another code: the sign-in code is renewed by signing in again instead.
  await expect(page.getByTestId('verify-email-resend')).toBeVisible();
  await atEveryViewport(page, 'verify-email');
  const code = await waitForMailCode(email, since);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();

  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByTestId('shell-account')).toContainText(email);
  await expect(page.getByRole('heading', { name: 'Create your business' })).toBeVisible();
  expect((await sessionOf(page.request)).user).toMatchObject({ label: email });
  await page.screenshot({ path: shot('signup--launcher') });
  expect(errors).toEqual([]);
});

test('a mistyped address is left with «Use a different email»: the right account signs in with its own code', async ({
  page,
  owner,
}) => {
  const errors = watchPageErrors(page);
  const typo = `e2e-signup-typo-${Date.now()}@example.com`;

  // The typo is an unknown address: it signs up and waits for the code that proves it.
  await page.goto('/launch');
  await openCreateAccount(page);
  await submitSignInForm(page, { email: typo, password: 'Signup-e2e-2026!' });
  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.getByText(`We emailed a code to ${typo}`)).toBeVisible();
  await expect(page.getByTestId('verify-email-resend')).toBeVisible();
  await page.getByTestId('code').locator('input').fill('123456');
  await page.getByTestId('verify-email-other').click();
  await expect(page).toHaveURL(/\/launch$/);

  // The real account: /verify-email again, now for its sign-in code, with nothing of the typo left.
  const since = Date.now();
  await submitSignInForm(page, owner);
  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.getByText(`We emailed a code to ${owner.email}`)).toBeVisible();
  await expect(page.getByText(`We emailed a code to ${typo}`)).toHaveCount(0);
  await expect(page.getByTestId('code').locator('input')).toHaveValue('');
  await expect(page.getByTestId('verify-email-help')).toBeVisible();
  await expect(page.getByTestId('verify-email-resend')).toHaveCount(0);
  const code = await waitForMailCode(owner.email, since);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();

  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByTestId('shell-account')).toContainText(owner.email);
  expect((await sessionOf(page.request)).user).toMatchObject({ label: owner.email });
  expect(errors).toEqual([]);
});

test('«Forgot your password?»: the mailed link sets a new password, and the account signs in with it', async ({ page }) => {
  const errors = watchPageErrors(page);
  createResetAccount();

  await page.goto('/launch');
  await page.getByTestId('login-forgot').click();
  await expect(page).toHaveURL(/\/password\/reset$/);
  const since = Date.now();
  await page.getByTestId('password-reset-email').locator('input').fill(RESET.email);
  await page.getByTestId('password-reset-submit').click();
  await expect(page.getByTestId('password-reset-sent')).toBeVisible();
  await atEveryViewport(page, 'password-reset-sent');

  // The link as mailed: the SPA's page on this panel.
  const link = await waitForPasswordResetLink(RESET.email, since);
  expect(new URL(link).pathname).toMatch(/^\/password\/reset\/key\/[^/]+$/);
  await page.goto(link);
  await expect(page.getByTestId('password-reset-key-form')).toBeVisible();
  await atEveryViewport(page, 'password-reset-key');
  await page.getByTestId('password-reset-key-password').locator('input').fill(NEW_PASSWORD);
  await page.getByTestId('password-reset-key-submit').click();

  await expect(page).toHaveURL(/\/launch\?notice=password_reset$/);
  await expect(page.getByTestId('login-notice')).toContainText('Your password has been changed successfully.');
  await signInThroughPage(page, { email: RESET.email, password: NEW_PASSWORD });
  await expect(page).toHaveURL(/\/launch$/);
  expect((await sessionOf(page.request)).user).toMatchObject({ label: RESET.email });
  expect(errors).toEqual([]);
});
