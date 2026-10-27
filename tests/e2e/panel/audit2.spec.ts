// The third fix pass of the panel, after the second audit of the real product
// (docs/plans/2026-10-14-auditoria-ux-panel-real-2.md), in Chrome without a window:
//   - R-01/R-10: the AA theme (`createShell({ contrast: 'aa' })`): the primary, «Retry» on its pink, the links and
//     the hints read ≥ 4.5:1, light and dark (text colour against the colours painted under it);
//   - S-05: «Skip to content» inside a landmark of its own, pointing at an element that exists;
//   - R-20: at 390 px a business's title is not cut; R-19: a manager's deep link says it has no permission;
//     R-18: an address that does not exist speaks of the panel and leads to Businesses;
//   - S-02: the one-Free-business limit before the form; S-03/R-17: a Free business is offered the plans sold at
//     sign-up, and the Store opens on a business that can buy; S-01: unpaid invoices have no PDF;
//   - S-07/S-08: the grouped notice of Businesses in Billing's order, with amounts; R-07: a deleted business is
//     recovered from the launcher; R-13: «View the invoices» is a 44 px target on a phone.
// Screenshots at 390, 834 and 1440 px, light and dark, go to `$SHOTS_DIR` (/tmp/panel-fix3 by default).
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { apiPost, businessIdOf, expect, panelAccount, seedPanel, settled, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/panel-fix3';
mkdirSync(SHOTS_DIR, { recursive: true });

/** WCAG 2.x AA for normal text. */
const AA = 4.5;

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

/** Signs the page's context in as `account`, signing out whoever was in (allauth refuses a second sign-in: 409). */
async function signInAs(page: Page, account: string): Promise<void> {
  await page.context().clearCookies();
  await signIn(page.request, panelAccount(account));
}

/** The page on screen (Ionic keeps the ones it left in the outlet, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/**
 * The contrast of an element's text against what is painted under it: its colour (an Ionic button's: its native
 * button's, in its shadow) over the background colours of it and of its ancestors (across shadow roots), composed
 * down to the first opaque one, else the theme's page background. Colours are read through a canvas, so
 * `color-mix()`/`oklab()` values count as painted.
 */
async function contrastOf(target: Locator): Promise<number> {
  return target.evaluate((host) => {
    const el = (host.shadowRoot?.querySelector<HTMLElement>('.button-native') ?? host) as HTMLElement;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    const rgba = (css: string): [number, number, number, number] => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = '#000';
      ctx.fillStyle = css;
      ctx.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
      return [r, g, b, a / 255];
    };
    const over = (top: number[], under: number[]): number[] => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
    const layers: number[][] = [];
    let node: Element | null = el;
    while (node) {
      const color = rgba(getComputedStyle(node).backgroundColor);
      if (color[3] > 0) layers.push(color);
      if (color[3] >= 1) break;
      node = node.parentElement ?? ((node.getRootNode() as ShadowRoot).host ?? null);
    }
    const page = rgba(getComputedStyle(document.documentElement).getPropertyValue('--ion-background-color').trim() || '#fff');
    const background = layers.reduceRight<number[]>((under, layer) => over(layer, under), page);
    const text = over(rgba(getComputedStyle(el).color), background);
    const luminance = (c: number[]) => {
      const [r, g, b] = c.slice(0, 3).map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const [hi, lo] = [luminance(text), luminance(background)].sort((a, b) => b - a);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  });
}

test.describe('R-01/R-10: the AA theme', () => {
  for (const scheme of ['light', 'dark'] as const) {
    test(`the primary, «Retry», the links and the hints read ≥ 4.5:1 (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const measured: Record<string, number> = {};
      await signIn(page.request, panelAccount('several'));
      await page.goto('/dashboard/businesses');
      await expect(shown(page).getByTestId('businesses-row').first()).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-ep-contrast', 'aa');
      await settled(page);
      measured['primary «Create business»'] = await contrastOf(shown(page).getByTestId('businesses-add'));
      await page.goto('/launch');
      await expect(page.getByTestId('launch-panel')).toBeVisible();
      await settled(page);
      measured['outlined «Go to the panel»'] = await contrastOf(page.getByTestId('launch-panel'));

      // «Retry» of the panel's error notice, on its pink (`/api/live` refused).
      const bakery = await businessIdOf(page.request, 'Panadería López');
      await page.route(/\/api\/live\?/, (route) =>
        route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'service_unavailable', message: 'Down.' } }) }),
      );
      await page.goto(`/dashboard/businesses/${bakery}/summary`);
      await expect(shown(page).getByTestId('business-retry')).toBeVisible();
      await settled(page);
      measured['«Retry» on the error notice'] = await contrastOf(shown(page).getByTestId('business-retry'));
      await page.unroute(/\/api\/live\?/);

      await signInAs(page, 'billing');
      await page.goto('/dashboard/billing/subscriptions');
      const link = shown(page).locator('.billing-alert__link');
      await expect(link).toBeVisible();
      await settled(page);
      measured['link «View the invoices»'] = await contrastOf(link);
      await page.goto('/dashboard/billing/invoices');
      await expect(shown(page).getByTestId('invoices-row').first()).toBeVisible();
      await settled(page);
      measured['outlined «Download Excel»'] = await contrastOf(shown(page).getByTestId('invoices-csv'));
      measured['outlined «Filters»'] = await contrastOf(shown(page).getByTestId('invoices-filters'));
      const plaza = await businessIdOf(page.request, 'Bar La Plaza');
      await page.goto(`/dashboard/store/plans?business=${plaza}`);
      const hint = shown(page).getByTestId('plan-hint').first();
      await expect(hint).toBeVisible();
      await settled(page);
      measured['plan hint «Pay the pending invoice first»'] = await contrastOf(hint);

      console.log(`contrast (${scheme}):`, JSON.stringify(measured));
      for (const [what, ratio] of Object.entries(measured)) expect(ratio, `${what} (${scheme})`).toBeGreaterThanOrEqual(AA);
    });
  }
});

test.describe('the chrome', () => {
  test('S-05: «Skip to content» lives in a landmark of its own and points at an element that exists', async ({ page }) => {
    await signIn(page.request, panelAccount('several'));
    await page.goto('/dashboard/businesses');
    await expect(shown(page).getByTestId('businesses-row').first()).toBeVisible();
    const skip = await page.evaluate(() => {
      const first = document.body.firstElementChild;
      const link = document.getElementById('skip-to-content') as HTMLAnchorElement | null;
      const target = link?.getAttribute('href')?.slice(1) ?? '';
      return { tag: first?.tagName, label: first?.getAttribute('aria-label'), inside: !!link && !!first?.contains(link), target: !!document.getElementById(target) };
    });
    expect(skip).toEqual({ tag: 'NAV', label: 'Shortcuts', inside: true, target: true });
    await page.keyboard.press('Tab');
    await expect(page.locator('#skip-to-content')).toBeFocused();
  });

  test('R-20: at 390 px a business’s title is whole; R-19: a manager’s deep link says it has no permission', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page.request, panelAccount('several'));
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.goto(`/dashboard/businesses/${bakery}/members`);
    await expect(shown(page).getByTestId('business-header')).toBeVisible();
    await settled(page);
    const title = await shown(page)
      .locator('.app-topbar ion-title')
      .evaluate((el) => {
        const box = el.shadowRoot?.querySelector<HTMLElement>('.toolbar-title') ?? (el as HTMLElement);
        return { text: el.textContent?.trim().replace(/\s+/g, ' '), cut: box.scrollWidth > box.clientWidth + 1 };
      });
    // The name and the section on screen («Panadería López Members»), whole.
    expect(title).toEqual({ text: 'Panadería López Members', cut: false });
    await page.screenshot({ path: join(SHOTS_DIR, 'business-members-390-light.png') });

    const ana = await businessIdOf(page.request, 'Peluquería Ana');
    await page.goto(`/dashboard/businesses/${ana}/members`);
    const error = shown(page).getByTestId('business-error');
    await expect(error).toContainText('You do not have permission to manage this business');
    await expect(error).toContainText('Your role does not allow it. If you need it, ask the owner.');
    await expect(error).not.toContainText('connection');
    await expect(shown(page).getByTestId('business-retry')).toHaveCount(0);
    await page.screenshot({ path: join(SHOTS_DIR, 'business-forbidden-390-light.png') });
  });

  test('R-18: an address that does not exist speaks of the panel and leads to Businesses', async ({ page }) => {
    await signIn(page.request, panelAccount('several'));
    await page.goto('/no-such-page');
    const notFound = shown(page).getByTestId('not-found');
    await expect(notFound).toContainText('The address you opened is not part of the panel.');
    await expect(notFound).not.toContainText('hub');
    await shown(page).getByTestId('not-found-home').click();
    await expect(page).toHaveURL(/\/dashboard\/businesses$/);
  });
});

test.describe('creating and buying', () => {
  test('S-02: with its Free business taken, «Create business» says so before any form and leads to its plan', async ({ page }) => {
    const errors = watchPageErrors(page);
    await signIn(page.request, panelAccount('several'));
    await page.goto('/dashboard/businesses');
    await shown(page).getByTestId('businesses-add').click();
    const limit = page.getByTestId('create-free-limit');
    await expect(limit).toContainText('You already have a free business');
    await expect(limit).toContainText('yours is Café Central');
    await expect(page.getByTestId('create-name')).toHaveCount(0);
    await settled(page);
    await page.screenshot({ path: join(SHOTS_DIR, 'businesses-create-limit-1280-light.png') });
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.getByTestId('create-free-limit-store').click();
    await expect(page).toHaveURL(new RegExp(`/dashboard/store/plans\\?business=${cafe}$`));
    expect(errors).toEqual([]);
  });

  test('S-03/R-17: a Free business is offered the plans sold at sign-up; the Store opens on one that can buy', async ({ page }) => {
    await signIn(page.request, panelAccount('billing'));
    await page.goto('/dashboard/store/plans');
    await expect(shown(page).getByTestId('store-plans')).toBeVisible();
    // Bar La Plaza and Bar Norte owe an invoice: not the business it opens on.
    await expect(shown(page).getByTestId('store-unpaid')).toHaveCount(0);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await expect(shown(page).getByTestId('plan-name')).toHaveText(['Free', 'Starter', 'Standard']);
    await expect(shown(page).getByTestId('store-plans-later')).toHaveText('Pro, Enterprise, and Max: available after moving to Starter.');
    // The server refuses an upgrade-only plan to a Free business too.
    const refused = await apiPost(page.request, '/api/billing/checkout/start', { hub_id: cafe, plan: 'pro', interval: 'month' });
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { error: { code: string } }).error.code).toBe('billing.plan_upgrade_only');
  });

  test('S-01: unpaid invoices have no PDF; S-07/S-08: the grouped notices, the most urgent first, with amounts', async ({ page }) => {
    await signIn(page.request, panelAccount('billing'));
    await page.goto('/dashboard/billing/invoices');
    await expect(shown(page).getByTestId('invoices-row').first()).toBeVisible();
    const unpaid = shown(page).locator('[data-testid="invoices-row"]').filter({ hasText: /Not collected/ });
    await expect(unpaid).toHaveCount(2);
    for (const row of await unpaid.all()) await row.locator('ion-checkbox').click();
    await expect(shown(page).getByTestId('invoices-pdf-selected')).toHaveText('Download PDF (0)');
    await expect(shown(page).getByTestId('invoices-selection-note')).toHaveText(
      '2 selected invoices are unpaid: an unpaid invoice has no PDF until it is paid.',
    );
    const billingOrder = await shown(page).getByTestId('unpaid-group-text').allInnerTexts();
    await page.goto('/dashboard/businesses');
    const group = shown(page).getByTestId('businesses-unpaid');
    await expect(group).toContainText('2 businesses have unpaid invoices: €');
    await expect(group.getByTestId('businesses-unpaid-amount')).toHaveCount(2);
    const businessOrder = await group.locator('.unpaid-line__text').allInnerTexts();
    expect(businessOrder.map((line) => line.split(' ')[0] + line.split(' ')[1])).toEqual(
      billingOrder.map((line) => line.split(' ')[0] + line.split(' ')[1]),
    );
  });

  test('R-07: a deleted business is recovered from the launcher', async ({ page }) => {
    const errors = watchPageErrors(page);
    await signIn(page.request, panelAccount('one'));
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const deleted = await apiPost(page.request, '/api/hubs/businesses/delete', { id: bakery, confirm_name: 'Panadería López' });
    expect(deleted.status(), await deleted.text()).toBe(200);
    await page.goto('/launch');
    const recover = page.getByTestId('recover-business');
    await expect(recover).toContainText('Recover business');
    await expect(page.getByTestId('launch-open')).toHaveCount(0);
    await settled(page);
    await page.screenshot({ path: join(SHOTS_DIR, 'launch-deleted-1280-light.png') });
    await recover.click();
    await expect(page.getByTestId('launch-open')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('R-13: «View the invoices» is a 44 px target on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page.request, panelAccount('billing'));
    await page.goto('/dashboard/billing/subscriptions');
    const link = shown(page).locator('.billing-alert__link');
    await expect(link).toBeVisible();
    const box = await link.boundingBox();
    expect(box && box.height >= 44).toBe(true);
  });
});

test.describe('screenshots for the supervisor', () => {
  const SCREENS: Array<[string, string, string, string]> = [
    ['launch', 'several', '/launch', 'launch-business'],
    ['businesses', 'billing', '/dashboard/businesses', 'businesses-row'],
    ['business-summary', 'several', 'bakery:summary', 'business-header'],
    ['store-plans-free', 'billing', 'cafe:store', 'store-plans'],
    ['billing-invoices', 'billing', '/dashboard/billing/invoices', 'invoices-row'],
  ];
  for (const scheme of ['light', 'dark'] as const) {
    test(`390, 834 and 1440 px (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      let account = '';
      for (const [name, who, where, ready] of SCREENS) {
        if (who !== account) {
          await signInAs(page, who);
          account = who;
        }
        let path = where;
        if (where === 'bakery:summary') path = `/dashboard/businesses/${await businessIdOf(page.request, 'Panadería López')}/summary`;
        if (where === 'cafe:store') path = `/dashboard/store/plans?business=${await businessIdOf(page.request, 'Café Central')}`;
        for (const width of [390, 834, 1440]) {
          await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
          await page.goto(path);
          await expect(shown(page).getByTestId(ready).first()).toBeVisible();
          await settled(page);
          await page.screenshot({ path: join(SHOTS_DIR, `${name}-${width}-${scheme}.png`) });
        }
      }
    });
  }
});
