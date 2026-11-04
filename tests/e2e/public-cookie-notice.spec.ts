// The cookie notice beside the navbar's side menu on a small phone (PUBLIC-F19, saas#244): the menu the person opens
// lies over the notice, so its actions show and can be pressed, and the notice is there again when it closes.
// The notice only shows with a tracker configured, which production does not have today (PUBLIC-F19, step 1), so these
// specs run on the public server's twin that has one (`publicNoticePort`, playwright.config.ts).
// flow: PUBLIC-G24
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { djangoEnv } from './django-env';
import { expect, test } from './public-test';
import { STACK } from './stack';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..', '..');
const SHOTS = join(HERE, '.artifacts', 'public-cookie-notice');
// Direct children: Playwright also looks inside the shadow root of an ion-button, whose inner link has the same href.
const START_FREE = '.ep-navbar__actions > [href="/launch"]';
const TRY_THE_DEMO = '.ep-navbar__actions > [href="/demo/"]';

test.beforeAll(() => {
  // The cookie groups every deploy seeds (saas-migrate runs init_cookie_groups): without them there is no notice.
  execFileSync('uv', ['run', 'python', 'manage.py', 'init_cookie_groups'], { cwd: SAAS_DIR, env: djangoEnv(true) });
  mkdirSync(SHOTS, { recursive: true });
});

test.use({
  baseURL: `http://127.0.0.1:${STACK.publicNoticePort}`,
  locale: 'en-GB',
  viewport: { width: 375, height: 667 },
});

/** Opens the side menu with the notice up and waits for its slide to end: mid-slide a measure says nothing. */
async function openMenu(page: Page) {
  await page.goto('/');
  await expect(page.locator('#cookie-consent-banner')).toBeVisible();
  await page.locator('[data-navbar-toggle]').click();
  const panel = page.locator('[data-navbar-panel]');
  await expect(panel).toBeVisible();
  await panel.evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
}

/**
 * What lies over `control` at its centre and just inside its top and bottom edges: a `#id` or tag for each spot where
 * something else is on top, nothing when the whole of it can be seen and reached; and whether it fits the screen.
 */
function coverOf(control: Locator) {
  return control.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const covering = [box.top + 2, box.top + box.height / 2, box.bottom - 2]
      .map((y) => document.elementFromPoint(x, y))
      .filter((hit) => hit === null || !element.contains(hit))
      .map((hit) => hit?.id || hit?.tagName || 'nothing');
    return { covering, onScreen: box.top >= 0 && box.bottom <= window.innerHeight };
  });
}

test('PUBLIC-G24 on a small phone, with the cookie notice up, the menu shows «Start free» and «Try the demo» whole', async ({ page }) => {
  await openMenu(page);
  await page.screenshot({ path: join(SHOTS, 'menu-open-375x667.png') });

  for (const action of [START_FREE, TRY_THE_DEMO]) {
    expect(await coverOf(page.locator(action)), action).toEqual({ covering: [], onScreen: true });
  }
});

test('PUBLIC-G24 on a small phone, with the cookie notice up, pressing «Start free» and «Try the demo» leads on', async ({ page }) => {
  await openMenu(page);
  await page.locator(START_FREE).click();
  await expect(page).toHaveURL(/\/launch$/);
  await expect(page.getByTestId('login-form')).toBeVisible();

  await openMenu(page);
  await page.locator(TRY_THE_DEMO).click();
  await expect(page).toHaveURL(/\/demo\/$/);
});

test('PUBLIC-G24 closing the menu leaves the cookie notice on top, and its choice still goes through', async ({ page }) => {
  await openMenu(page);
  // The strip of backdrop beside the panel, right over the notice: a tap closes the menu and presses nothing behind it.
  const notice = await page.locator('#cookie-consent-banner').boundingBox();
  if (notice === null) throw new Error('the cookie notice has no box');
  await page.mouse.click(10, notice.y + notice.height / 2);
  await expect(page.locator('[data-navbar]')).not.toHaveAttribute('data-open');
  await expect(page).toHaveURL(/\/$/);

  const decline = page.locator('#cookie-decline');
  expect(await coverOf(decline)).toEqual({ covering: [], onScreen: true });
  await decline.click();
  await expect(page.locator('#cookie-consent-banner')).toBeHidden();
  await page.reload();
  await expect(page.locator('#cookie-consent-banner')).toHaveCount(0);
});
