// The panel's smoke (plan 2026-10-13-panel-saas-unificado, L0-G; launcher of L1-C): the pipeline from
// Ioan's visible Chrome to the panel's dev server (:8012, project.ts) works end to end. A visitor opens the entry
// (/launch, open to visitors since round 17 §2.2), is asked to sign in, signs in through the real
// /login page and comes back to the launcher, and /api/me answers with that session; then the
// signed-in fixture (allauth.headless's API, what later specs start from) opens the launcher at the
// three viewports. The seeded owner has no business of the panel (demo_seed only writes the jump's
// memberships), so the launcher is its sign-up card; only its frame and that it did not fail are
// asserted here (its variants: launch.spec.ts).
import { type Page } from '@playwright/test';

import { OWNER, VIEWPORTS, expect, sessionOf, shot, signInThroughPage, test, watchPageErrors } from './fixtures';

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

test('the seeded owner signs in at /login, lands on the launcher and /api/me is its session', async ({
  page,
  owner,
}) => {
  const pageErrors = watchPageErrors(page);

  const anonymous = await sessionOf(page.request);
  expect(anonymous.user).toBeNull();
  expect(anonymous.scope).toEqual({ kind: 'user', key: 'anonymous' });

  // No session: the launcher asks to sign in and come back to it.
  await page.goto('/launch');
  await expect(page.getByRole('heading', { name: 'Sign in to ERPlora' })).toBeVisible();
  await page.getByTestId('launch-sign-in').click();
  await expect(page).toHaveURL(/\/login\?next=(%2F|\/)launch$/);
  await signInThroughPage(page, owner);

  await expectLauncher(page);
  await page.screenshot({ path: shot('login--launcher') });
  const session = await sessionOf(page.request);
  expect(session.user).toMatchObject({ label: owner.email });
  expect(session.scope).toEqual({ kind: 'user', key: session.user?.id });
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
