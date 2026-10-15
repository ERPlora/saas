// The entry (`/launch`, round 17 §2.2, README §5) in Ioan's Chrome: the four variants of the mockups
// (first time, invited, one business, several), the app surface and, signed out, the sign-in itself (the
// form of the launcher, at the three viewports). Accounts of panel_seed.py.
// «Open» goes to the Hub's start of the jump (`http://<slug>.localhost:8000/auth/login?next=/`): the
// spec answers that address itself and checks where the browser went, so no Hub has to run.
import { type Page } from '@playwright/test';

import {
  expect,
  panelAccount,
  seedPanel,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  signInThroughPage,
  test,
  VIEWPORTS,
  watchPageErrors,
} from './fixtures';

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

/** Stands in for the Hub's start of the jump; returns the addresses the browser went to (with their method). */
async function hubStart(page: Page): Promise<string[]> {
  const visits: string[] = [];
  await page.route(/^http:\/\/[\w-]+\.localhost:8000\//, async (route) => {
    visits.push(`${route.request().method()} ${route.request().url()}`);
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
  });
  return visits;
}

test('first time: the sign-up card, with «Go to the panel» and where an invitation would show', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('first'));
  await page.goto('/launch');
  await expect(page.getByRole('heading', { name: 'Create your business' })).toBeVisible();
  await expect(page.getByTestId('create-name')).toBeVisible();
  await expect(page.getByTestId('launch-foot')).toHaveText(
    'Invited? The invitation shows up here if you sign in with the email it was sent to.',
  );
  await page.getByTestId('launch-panel').click();
  await expect(page).toHaveURL(/\/businesses$/);
  expect(errors).toEqual([]);
});

test('invited without a business: the card is the invitation; «Accept and enter» goes into it', async ({ page }) => {
  const errors = watchPageErrors(page);
  const visits = await hubStart(page);
  await signIn(page.request, panelAccount('invited'));
  await page.goto('/launch');
  await expect(page.getByRole('heading', { name: 'You have been invited to Peluquería Ana' })).toBeVisible();
  await expect(page.locator('.shell-lead')).toHaveText('Carlos Ruiz gives you access as Manager.');
  await page.getByTestId('launch-accept').click();
  await expect.poll(() => visits).toEqual(['GET http://e2e-peluqueria-ana.localhost:8000/auth/login?next=/']);
  expect(errors).toEqual([]);
});

test('one business: «Open» goes to its Hub’s start of the jump; «Go to the panel» manages it', async ({ page }) => {
  const errors = watchPageErrors(page);
  const visits = await hubStart(page);
  await signIn(page.request, panelAccount('one'));
  await page.goto('/launch');
  await expect(page.getByRole('heading', { name: 'Hello, Laura' })).toBeVisible();
  await expect(page.getByTestId('launch-business')).toContainText('Panadería López');
  await expect(page.getByTestId('launch-business')).toContainText('Plan Free · Owner');
  await page.getByTestId('launch-open').click();
  await expect.poll(() => visits).toEqual(['GET http://e2e-one-panaderia.localhost:8000/auth/login?next=/']);
  expect(errors).toEqual([]);
});

test('several businesses: the last opened first, why one does not open, and the pending invitation', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  await page.goto('/launch');
  await expect(page.getByRole('heading', { name: 'Where are you working today?' })).toBeVisible();
  const tiles = page.getByTestId('launch-business');
  await expect(tiles).toHaveCount(4);
  await expect(tiles.first()).toContainText('Panadería López');
  await expect(tiles.first()).toContainText('Last opened');
  const cafe = tiles.filter({ hasText: 'Café Central' });
  // With several businesses nothing opens by itself: it says when it will be ready.
  await expect(cafe).toContainText('Ready in a few seconds');
  // Being prepared, its «Open» is there but disabled.
  await expect(cafe.getByTestId('launch-open')).toHaveAttribute('aria-disabled', 'true');
  await expect(page.getByTestId('launch-invitation')).toContainText('You have been invited to Bar Norte');
  await page.getByTestId('launch-create-another').click();
  await expect(page).toHaveURL(/\/businesses$/);
  // Café Central fills its one Free business: the dialog says so before any form (audit 2 S-02).
  await expect(page.getByTestId('create-free-limit')).toContainText('yours is Café Central');
  expect(errors).toEqual([]);
});

// flow: FIX-LAUNCH-TABS
test('signed out, at 390, 834 and 1440 px: the form on «Sign in» with the tab «Create account», without scrolling sideways', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/launch');
    await expect(page.getByTestId('login-form')).toBeVisible();
    for (const testid of ['login-tabs', 'login-email', 'login-password', 'login-submit', 'login-forgot', 'login-switch']) {
      await expect(page.getByTestId(testid)).toBeVisible();
    }
    await expect(page.getByTestId('login-submit')).toHaveText('Sign in');
    await settled(page);
    expect(await sidewaysScroll(page), `/launch scrolls sideways at ${viewport.width} px`).toEqual([]);
    // Touch targets: «Sign in» is a large button (Ionic's 48 px), and each tab is 44 px high.
    expect((await page.getByTestId('login-submit').boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    for (const tab of ['login-tab-signin', 'login-tab-signup']) {
      expect((await page.getByTestId(tab).boundingBox())?.height ?? 0, tab).toBeGreaterThanOrEqual(44);
    }
    await page.screenshot({ path: shot(`FIX-LAUNCH-TABS-${viewport.width}`), fullPage: true });
  }
  // «Create account» at 390: its button, no «Forgot your password?», the way back to «Sign in».
  await page.setViewportSize(VIEWPORTS[0]);
  await page.getByTestId('login-tab-signup').click();
  await expect(page).toHaveURL(/\/launch\?tab=signup$/);
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await expect(page.getByTestId('login-forgot')).toHaveCount(0);
  await expect(page.getByTestId('login-switch')).toHaveText('Already have an account? Sign in');
  await expect(page.getByTestId('login-password').locator('input')).toHaveAttribute('autocomplete', 'new-password');
  await settled(page);
  expect(await sidewaysScroll(page), '/launch?tab=signup scrolls sideways at 390 px').toEqual([]);
  await page.screenshot({ path: shot('FIX-LAUNCH-TABS-signup-390'), fullPage: true });
  expect(errors).toEqual([]);
});

test('signed out, inside the app: the same sign-in, and it comes back here signed in', async ({ page, owner }) => {
  const errors = watchPageErrors(page);
  await page.goto('/launch?surface=mobile');
  await expect(page.locator('html')).toHaveClass(/in-app-shell/);
  await expect(page.getByTestId('login-form')).toBeVisible();
  await signInThroughPage(page, owner);
  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByTestId('shell-account')).toContainText(owner.email);
  expect(errors).toEqual([]);
});
