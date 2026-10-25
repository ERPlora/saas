// flow: FIX-LAUNCH-TABS
// The panel's smoke (plan 2026-10-13-panel-saas-unificado, L0-G; launcher of L1-C): the pipeline from
// the browser to the panel's dev server (:8012 by default, project.ts) works end to end. A visitor opens the entry
// (/launch, open to visitors since round 17 §2.2), whose card is the sign-in itself (Ioan, 2026-10-15): the
// password, then the code mailed to the account typed on /verify-email, and the launcher loads again signed
// in, and /api/me answers with that session; then the signed-in fixture (allauth.headless's API with the
// same code, what later specs start from) opens the launcher at the three viewports. The seeded owner has
// no business of the panel (demo_seed only writes the jump's memberships), so the launcher is its sign-up
// card; only its frame and that it did not fail are asserted here (its variants: launch.spec.ts).
import { type Page } from '@playwright/test';

import {
  OWNER,
  VIEWPORTS,
  expect,
  sessionOf,
  shot,
  signInThroughPage,
  submitSignInForm,
  test,
  waitForMailCode,
  watchPageErrors,
} from './fixtures';

/** The launcher's card, signed in: the logo inside it, a heading, and neither loading nor failed. */
async function expectLauncher(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByRole('img', { name: 'ERPlora' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page).toHaveTitle('Enter - ERPlora');
  await expect(page.getByTestId('launch-loading')).toHaveCount(0);
  await expect(page.getByTestId('launch-error')).toHaveCount(0);
  await expect(page.getByTestId('shell-account')).toContainText('Signed in as');
}

test('the seeded owner signs in on the launcher with the mailed code, and /api/me is its session', async ({
  page,
  owner,
}) => {
  const pageErrors = watchPageErrors(page);

  const anonymous = await sessionOf(page.request);
  expect(anonymous.user).toBeNull();
  expect(anonymous.scope).toEqual({ kind: 'user', key: 'anonymous' });

  // No session: the launcher is the sign-in, the old login card with its form.
  await page.goto('/launch');
  await expect(page).toHaveTitle('Sign In - ERPlora Cloud');
  await expect(page.getByRole('heading', { name: 'ERPlora Cloud' })).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await signInThroughPage(page, owner);

  await expectLauncher(page);
  await page.screenshot({ path: shot('login--launcher') });
  const session = await sessionOf(page.request);
  expect(session.user).toMatchObject({ label: owner.email });
  expect(session.scope).toEqual({ kind: 'user', key: session.user?.id });
  expect(pageErrors).toEqual([]);
});

test('the old addresses of the sign-in (/login, /accounts/login/) land on the launcher in one hop, keeping next', async ({
  page,
}) => {
  const pageErrors = watchPageErrors(page);

  for (const old of ['/login', '/accounts/login/']) {
    const answer = await page.request.get(`${old}?next=/account`, { maxRedirects: 0 });
    expect([answer.status(), answer.headers().location], old).toEqual([301, '/launch?next=/account']);
  }

  await page.goto('/login?next=/account');
  await expect(page).toHaveURL(/\/launch\?next=\/account$/);
  await expect(page.getByTestId('login-form')).toBeVisible();
  // On «Sign in», the tab of the sign-in (FIX-LAUNCH-TABS, gh:saas#2246).
  await expect(page.getByTestId('login-submit')).toHaveText('Sign in');
  await expect(page.getByTestId('login-forgot')).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('the old address of the sign-up (/accounts/signup/) lands on «Create account» in one hop, keeping next', async ({ page }) => {
  const pageErrors = watchPageErrors(page);

  const answer = await page.request.get('/accounts/signup/?next=/account', { maxRedirects: 0 });
  expect([answer.status(), answer.headers().location]).toEqual([301, '/launch?tab=signup&next=/account']);

  await page.goto('/accounts/signup/?next=/account');
  await expect(page).toHaveURL(/\/launch\?tab=signup&next=\/account$/);
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await expect(page.getByTestId('login-forgot')).toHaveCount(0);
  // «Already have an account? Sign in» goes back to «Sign in», keeping next.
  await page.getByTestId('login-switch-action').click();
  await expect(page).toHaveURL(/\/launch\?next=(%2F|\/)account$/);
  await expect(page.getByTestId('login-submit')).toHaveText('Sign in');
  expect(pageErrors).toEqual([]);
});

test('a wrong sign-in code says so under the input and the right one still signs in', async ({ page, owner }) => {
  const pageErrors = watchPageErrors(page);
  await page.goto('/launch?next=/account');
  const since = Date.now();
  await submitSignInForm(page, owner);
  await expect(page).toHaveURL(/\/verify-email\?next=(%2F|\/)account$/);
  await expect(page.getByText(`We emailed a code to ${owner.email}`)).toBeVisible();
  await expect(page.getByTestId('verify-email-help')).toBeVisible();
  const code = await waitForMailCode(owner.email, since);

  await page.getByTestId('code').locator('input').fill(code === '000000' ? '111111' : '000000');
  await page.getByTestId('verify-email-submit').click();
  await expect(page.getByTestId('code')).toHaveClass(/ion-invalid/);

  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/dashboard\/account\/profile$/);
  expect((await sessionOf(page.request)).user).toMatchObject({ label: owner.email });
  expect(pageErrors).toEqual([]);
});

test('the signed-in fixture opens the launcher at 390, 834 and 1440 px without a horizontal scroll', async ({
  signedInPage: page,
}) => {
  const pageErrors = watchPageErrors(page);
  expect((await sessionOf(page.request)).user).toMatchObject({ label: OWNER.email });

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/launch');
    await expectLauncher(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `/launch overflows ${viewport.width} px`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`launcher--${viewport.width}`), fullPage: true });
  }
  expect(pageErrors).toEqual([]);
});
