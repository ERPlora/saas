// The panel's smoke (plan 2026-10-13-panel-saas-unificado, L0-G): the pipeline from Ioan's visible
// Chrome to the SaaS's dev server on :8001 works end to end. The seeded owner signs in through the
// real /login page and lands on the launcher (/launch) in its auth frame, and /api/me answers with
// that session; then the signed-in fixture (allauth.headless's API, what later specs start from)
// opens the launcher at the three viewports. Only what the launcher has today is asserted: its frame,
// logo and title, and that it did not end in its error state (the owner has two hubs, so it lists
// them instead of jumping to one).
import { type Page } from '@playwright/test';

import { OWNER, VIEWPORTS, expect, sessionOf, shot, signInThroughPage, test, watchPageErrors } from './fixtures';

/** The launcher in its auth frame: the logo, «ERPlora Cloud», its title, and not its error. */
async function expectLauncher(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByRole('img', { name: 'ERPlora Cloud' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'ERPlora Cloud' })).toBeVisible();
  await expect(page).toHaveTitle('Choose a business - ERPlora Cloud');
  await expect(page.getByTestId('launch-loading')).toBeHidden();
  await expect(page.getByTestId('launch-error')).toHaveCount(0);
}

test('the seeded owner signs in at /login, lands on the launcher and /api/me is its session', async ({
  page,
  owner,
}) => {
  const pageErrors = watchPageErrors(page);

  const anonymous = await sessionOf(page.request);
  expect(anonymous.user).toBeNull();
  expect(anonymous.scope).toEqual({ kind: 'user', key: 'anonymous' });

  // No session: the shell's auth gate sends the visitor to the sign-in, keeping where it was going.
  await page.goto('/launch');
  await expect(page).toHaveURL(/\/login\?next=%2Flaunch$/);
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
