// The fix pass of the panel after the audit of the real product (docs/plans/2026-10-14-auditoria-ux-panel-real.md),
// in Chrome without a window:
//   - R-04/R-08: with `/api/live` refused (503) or unreachable, every page says it could not load, with «Retry»,
//     never an empty state that lies («Create your first business») nor a spinner for ever; «Retry» loads it;
//   - R-06/R-07/R-09/R-15: the way to pay outside Billing — the launcher's real deadline and «Pay the invoice» /
//     «Change card», and one grouped notice on Businesses with each business's way out;
//   - R-11/R-13/R-14/R-20: «Skip to content», 44 px targets at 390, Back without ☰ in a business, the
//     table's toolbar in one row from 834 to 1180 px.
// Screenshots at 390, 834 and 1440 go to `$SHOTS_DIR` (/tmp/panel-fix2 by default) for the supervisor, each one
// refused when it repeats the top of the page at its bottom (taken before the page was painted at its size).
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import {
  businessIdOf,
  expect,
  panelAccount,
  repeatedTop,
  seedPanel,
  settled,
  shot,
  signIn,
  test,
  watchPageErrors,
} from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/panel-fix2';
mkdirSync(SHOTS_DIR, { recursive: true });

/** How long a page waits for its first result (`frontend/live-state.ts` LIVE_TIMEOUT_MS), plus a margin. */
const LIVE_TIMEOUT = 10_000 + 5_000;

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

test.beforeAll(() => {
  seedPanel();
  seedBilling('seed');
});
test.afterAll(() => {
  seedPanel('clear');
  seedBilling('clear');
});

/** `/api/live` refused, as when the stream's service is down (the API itself answers). */
async function liveRefused(page: Page): Promise<void> {
  await page.route(/\/api\/live\?/, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'service_unavailable', message: 'Live updates are not available right now.' } }),
    }),
  );
}

/** `/api/live` unreachable: the request fails before any answer (no network, a proxy that drops it). */
async function liveUnreachable(page: Page): Promise<void> {
  await page.route(/\/api\/live\?/, (route) => route.abort('failed'));
}

/** An `ion-button`'s link: Ionic Vue sets `href` as a property of the element, not as an attribute. */
const hrefOf = (button: ReturnType<Page['getByTestId']>) => button.evaluate((el) => (el as HTMLElement & { href?: string }).href ?? null);

/** The page on screen (Ionic keeps the ones it left in the outlet, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** Phone, tablet and desktop, one after another on the same page, as the launcher and Businesses are shot. */
const SHOT_SIZES = [
  { width: 390, height: 844 },
  { width: 834, height: 900 },
  { width: 1440, height: 900 },
] as const;

/** A screenshot for the supervisor, refused when it is not the page as painted (`repeatedTop`). */
async function snap(page: Page, name: string): Promise<void> {
  await settled(page);
  const png = await page.screenshot({ path: join(SHOTS_DIR, `${name}.png`) });
  expect(await repeatedTop(page, png), `${name}.png repeats the top of the page at its bottom`).toBe(0);
}

test.describe('R-04/R-08: a failure is never an empty page nor a spinner for ever', () => {
  test('with /api/live answering 503, every page says it could not load, offers «Retry», and «Retry» loads it', async ({ page }) => {
    const errors = watchPageErrors(page);
    await signIn(page.request, panelAccount('several'));
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await liveRefused(page);

    await page.goto('/dashboard/businesses');
    await expect(page.getByTestId('businesses-retry')).toBeVisible();
    await expect(shown(page)).toContainText('We could not load your businesses');
    await expect(page.getByTestId('businesses-empty')).toHaveCount(0);
    await expect(page.getByTestId('businesses-row')).toHaveCount(0);
    await snap(page, 'businesses-live-503-1440');

    await page.goto('/launch');
    await expect(page.getByTestId('launch-error')).toContainText('We could not load your businesses.');
    await expect(page.getByTestId('launch-loading')).toHaveCount(0);

    await page.goto(`/dashboard/businesses/${bakery}/members`);
    await expect(page.getByTestId('business-error')).toBeVisible();
    // No tabbar on an error: its sections would only repeat it (W-18).
    await expect(shown(page).locator('[data-testid^="tab-"]')).toHaveCount(0);

    await page.goto('/invitation');
    await expect(page.getByTestId('invitation-error')).toBeVisible();
    await expect(page.getByTestId('invitation-expired')).toHaveCount(0);

    await page.goto('/dashboard/account/profile');
    await expect(page.getByTestId('profile-error')).toBeVisible();
    await expect(page.getByTestId('profile-loading')).toHaveCount(0);

    await page.goto('/dashboard/account/preferences');
    await expect(page.getByTestId('preferences-error')).toBeVisible();

    // The service is back: «Retry» loads the page.
    await page.goto('/dashboard/businesses');
    await expect(page.getByTestId('businesses-retry')).toBeVisible();
    await page.unroute(/\/api\/live\?/);
    await page.getByTestId('businesses-retry').click();
    await expect(page.getByTestId('businesses-row')).toHaveCount(4);
    expect(errors).toEqual([]);
  });

  test('with /api/live unreachable, the spinner gives way to the error after the time limit', async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page.request, panelAccount('several'));
    await liveUnreachable(page);
    await page.goto('/launch');
    await expect(page.getByTestId('launch-loading')).toBeVisible();
    await expect(page.getByTestId('launch-error')).toBeVisible({ timeout: LIVE_TIMEOUT });
    await expect(page.getByTestId('launch-loading')).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    await snap(page, 'launch-live-unreachable-390');
    await page.unroute(/\/api\/live\?/);
    await page.getByTestId('launch-retry').click();
    await expect(page.getByTestId('launch-business')).toHaveCount(4);
  });
});

test.describe('R-06/R-07/R-09/R-15: the way to pay outside Billing', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/^https:\/\/(invoice|billing)\.stripe\.com\//, (route) =>
      route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
    );
    await signIn(page.request, panelAccount('billing'));
  });

  test('the launcher says each real deadline and offers «Change card» or «Pay the invoice»', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/launch');
    const plaza = page.getByTestId('launch-business').filter({ hasText: 'Bar La Plaza' });
    const norte = page.getByTestId('launch-business').filter({ hasText: 'Bar Norte' });
    // Unpaid 4 and 2 days ago: suspended 3 and 5 days from now, never «7 more days».
    const day = (offset: number) => new Intl.DateTimeFormat('en', { dateStyle: 'medium' }).format(new Date(Date.now() + offset * 86_400_000));
    await expect(plaza).toContainText(`Pay it before ${day(3)} or the business is suspended.`);
    await expect(norte).toContainText(`Pay it before ${day(5)} or the business is suspended.`);
    await expect(page.locator('ion-app')).not.toContainText('7 more days');
    await expect(plaza.getByTestId('unpaid-change-card')).toBeVisible();
    expect(await hrefOf(norte.getByTestId('unpaid-pay'))).toBe('https://invoice.stripe.com/i/e2e-billing-norte');
    for (const size of SHOT_SIZES) {
      await page.setViewportSize(size);
      await snap(page, `launch-past-due-${size.width}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await norte.getByTestId('unpaid-pay').click();
    await expect(page).toHaveURL('https://invoice.stripe.com/i/e2e-billing-norte');
    expect(errors).toEqual([]);
  });

  // flow: ninguno — FIX tests/e2e. A capture right after `setViewportSize` used to be taken before the page was
  // painted at the new size: an 87 px stripe at its bottom repeated the top of the page (8 in 12 at 834 px).
  test('a screenshot right after a resize is the page as painted, never its top repeated at the bottom', async ({ page }) => {
    await page.goto('/launch');
    await expect(page.getByTestId('launch-business').filter({ hasText: 'Bar Norte' })).toBeVisible();
    const striped: string[] = [];
    for (let round = 0; round < 4; round++) {
      for (const size of SHOT_SIZES) {
        await page.setViewportSize(size);
        await settled(page);
        const png = await page.screenshot({ path: shot(`FIX-SAAS-E2E-CHROME-SHOT-STRIPE-${size.width}`) });
        const rows = await repeatedTop(page, png);
        if (rows) striped.push(`round ${round} at ${size.width}: ${rows} rows`);
      }
    }
    expect(striped).toEqual([]);
  });

  test('Businesses groups the unpaid invoices in one notice, each business with its way out, days without the time', async ({ page }) => {
    await page.goto('/dashboard/businesses');
    const group = page.getByTestId('businesses-unpaid');
    await expect(group).toContainText('2 businesses have unpaid invoices');
    const lines = group.getByTestId('businesses-unpaid-line');
    await expect(lines).toHaveCount(2);
    await expect(lines.filter({ hasText: 'Bar La Plaza' }).getByTestId('unpaid-change-card')).toBeVisible();
    expect(await hrefOf(lines.filter({ hasText: 'Bar Norte' }).getByTestId('unpaid-pay'))).toBe('https://invoice.stripe.com/i/e2e-billing-norte');
    expect(await group.innerText()).not.toMatch(/\d{1,2}:\d{2}/);
    await expect(page.locator('[data-testid^="businesses-unpaid-e2e"]')).toHaveCount(0);
    for (const size of SHOT_SIZES) {
      await page.setViewportSize(size);
      await snap(page, `businesses-unpaid-grouped-${size.width}`);
    }
  });
});

/** Targets under 44 px on the page on screen and its topbar: Ionic's buttons, segments, chips, menu and Back. */
async function smallTargets(page: Page, inDialog = false): Promise<string[]> {
  return page.evaluate((dialog) => {
    const page = dialog
      ? (document.querySelector('ion-modal.show-modal') ?? document)
      : ([...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document);
    const found: string[] = [];
    for (const el of page.querySelectorAll<HTMLElement>('ion-button, ion-segment-button, ion-menu-button, ion-back-button, ion-chip')) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (rect.width === 0 || rect.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
      const iconOnly = el.tagName === 'ION-MENU-BUTTON' || !!el.querySelector(':scope > [slot="icon-only"]');
      const name = el.getAttribute('aria-label') ?? el.getAttribute('data-testid') ?? (el.textContent ?? '').trim().slice(0, 30);
      if (rect.height < 43.5 || (iconOnly && rect.width < 43.5)) found.push(`${el.tagName.toLowerCase()} «${name}» ${Math.round(rect.width)}×${Math.round(rect.height)}`);
    }
    return found;
  }, inDialog);
}

test.describe('R-11/R-13/R-20: the chrome of every page', () => {
  test('«Skip to content» is the first stop of the keyboard and takes it to the page', async ({ page }) => {
    await signIn(page.request, panelAccount('several'));
    await page.goto('/dashboard/businesses');
    await expect(page.getByTestId('businesses-row').first()).toBeVisible();
    await page.keyboard.press('Tab');
    const link = page.locator('#skip-to-content');
    await expect(link).toBeFocused();
    await expect(link).toHaveText('Skip to content');
    const box = await link.boundingBox();
    expect(box && box.y >= 0 && box.height >= 44).toBe(true);
    await page.keyboard.press('Enter');
    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      return { tag: el?.tagName ?? '', inShown: !!el?.closest('ion-router-outlet > .ion-page:not(.ion-page-hidden)') };
    });
    expect(focused).toEqual({ tag: 'ION-CONTENT', inShown: true });
  });

  test('at 390 px every target is 44 px, and a business has Back without ☰', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page.request, panelAccount('several'));
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const screens: Array<[string, string, string]> = [
      ['launch', '/launch', 'launch-business'],
      ['businesses', '/dashboard/businesses', 'businesses-row'],
      ['business-summary', `/dashboard/businesses/${bakery}/summary`, 'business-header'],
      ['business-members', `/dashboard/businesses/${bakery}/members`, 'members-row'],
      ['account-preferences', '/dashboard/account/preferences', 'preferences-theme'],
    ];
    const offenders: string[] = [];
    for (const [name, path, ready] of screens) {
      await page.goto(path);
      await expect(page.locator(`[data-testid="${ready}"], [data-testid^="${ready}"]`).first()).toBeVisible();
      await settled(page);
      offenders.push(...(await smallTargets(page)).map((target) => `${name}: ${target}`));
      await snap(page, `${name}-390`);
    }
    // A dialog: its ✕ and its buttons (with Café Central on Free, the one-Free-business limit and its way out,
    // audit 2 S-02).
    await page.goto('/dashboard/businesses?create=1');
    await expect(page.getByTestId('create-free-limit-store')).toBeVisible();
    await settled(page);
    offenders.push(...(await smallTargets(page, true)).map((target) => `create dialog: ${target}`));
    await snap(page, 'businesses-create-390');
    expect(offenders).toEqual([]);

    await page.goto(`/dashboard/businesses/${bakery}/summary`);
    await expect(shown(page).getByTestId('topbar-back')).toBeVisible();
    await expect(shown(page).locator('ion-menu-button')).toBeHidden();
    await page.goto('/dashboard/businesses');
    await expect(shown(page).locator('ion-menu-button')).toBeVisible();
  });
});

test.describe('R-13: Billing and the Store at 390 px', () => {
  test('every target is 44 px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page.request, panelAccount('billing'));
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const screens: Array<[string, string, string]> = [
      ['billing-invoices', '/dashboard/billing/invoices', 'invoices-row'],
      ['billing-subscriptions', '/dashboard/billing/subscriptions', 'subscriptions-row'],
      ['store-plans', `/dashboard/store/plans?business=${bakery}`, 'store-plans'],
    ];
    const offenders: string[] = [];
    for (const [name, path, ready] of screens) {
      await page.goto(path);
      await expect(page.getByTestId(ready).first()).toBeVisible();
      await settled(page);
      offenders.push(...(await smallTargets(page)).map((target) => `${name}: ${target}`));
      await snap(page, `${name}-390`);
    }
    expect(offenders).toEqual([]);
  });
});

/** The rows the toolbar of the table on screen takes: a piece below every piece of the row so far starts a new one. */
async function toolbarRows(page: Page): Promise<number> {
  return page.evaluate(() => {
    const page = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const bar = page.querySelector('.data-table__bar-main');
    if (!bar) return 0;
    const boxes = [...bar.children]
      .map((child) => child.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0)
      .sort((a, b) => a.top - b.top);
    let rows = 0;
    let bottom = -Infinity;
    for (const box of boxes) {
      if (box.top >= bottom - 2) rows += 1;
      bottom = Math.max(bottom, box.bottom);
    }
    return rows;
  });
}

test.describe('R-14: the table’s toolbar in one row on a tablet and a laptop', () => {
  for (const width of [834, 1024, 1180]) {
    test(`Businesses at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page.request, panelAccount('several'));
      await page.goto('/dashboard/businesses');
      await expect(page.getByTestId('businesses-row').first()).toBeVisible();
      await settled(page);
      expect(await toolbarRows(page)).toBe(1);
      if (width === 834) await snap(page, 'businesses-834');
    });

    test(`Invoices at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page.request, panelAccount('billing'));
      await page.goto('/dashboard/billing/invoices');
      await expect(page.getByTestId('invoices-row').first()).toBeVisible();
      await settled(page);
      expect(await toolbarRows(page)).toBe(1);
      await snap(page, `invoices-${width}`);
    });
  }
});
