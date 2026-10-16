// flow: FIX-DATATABLE-SAAS
// The panel's lists after DataTable part 3 (ui#4, 070e74f): the `.panel-fill` height chain, the toolbar of
// R-14 and the phone's heading come from the shell's theme (`polish.css`, loaded by createShell); the SaaS
// keeps no sheet of its own (frontend/main.test.ts). Invoices, in Chrome at 390, 834 and 1440 px, against
// the rows of billing_seed.py: the list fills the page between the topbar and the tabbar, its search and
// its heading are as before, and its «Filters» popover (InvoiceFilters.vue: the SaaS keeps it,
// PLAN-MIGRATIONS §13; DataTable's own funnel stays off) still filters. One scroll at every width: the page
// never scrolls at 834 and 1440 (the rows scroll inside), and on a phone nothing inside the list scrolls (the
// page does). Screenshots: `FIX-DATATABLE-SAAS-<width>.png` in the artifacts, the viewport as a person sees it
// (not `fullPage`), so a second scrollbar or a cut list shows, and `-filters` with the popover open.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { expect, panelAccount, qaAccount, settled, shot, signIn, test, VIEWPORTS, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const BILLING = qaAccount('BILLING', panelAccount('billing'));

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], {
    cwd: SAAS_DIR,
    env: { ...process.env, DEBUG: 'True' },
    stdio: 'pipe',
  });
}

// Nothing here writes: the filters live in the address.
test.beforeAll(() => seedBilling('seed'));
test.afterAll(() => seedBilling('clear'));
test.beforeEach(async ({ page }) => {
  await signIn(page.request, BILLING);
});

/**
 * How the list fills its page (as viewports.spec.ts reads it): whether the page itself scrolls, and how far
 * the list's bottom is from the bottom of the content box, less what sits under it in its `.panel-fill`
 * stacks and their gaps.
 */
async function listFill(page: Page): Promise<{ pageScrolls: boolean; offBy: number }> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    const table = shown.querySelector<HTMLElement>('.data-table--fill');
    if (!scroll || !table) throw new Error('no ion-content or no filled DataTable on screen');
    const end = scroll.getBoundingClientRect().bottom - parseFloat(getComputedStyle(scroll).paddingBottom);
    let under = 0;
    for (let node: HTMLElement | null = table; node?.parentElement?.classList.contains('panel-fill'); node = node.parentElement) {
      const gap = parseFloat(getComputedStyle(node.parentElement).rowGap) || 0;
      for (let next = node.nextElementSibling as HTMLElement | null; next; next = next.nextElementSibling as HTMLElement | null) {
        if (getComputedStyle(next).display !== 'none') under += next.getBoundingClientRect().height + gap;
      }
    }
    return {
      pageScrolls: scroll.scrollHeight > scroll.clientHeight + 1,
      offBy: Math.round(end - under - table.getBoundingClientRect().bottom),
    };
  });
}

/** What scrolls up and down inside the list (a second scroll under the page's): its elements' classes. */
async function nestedScrollers(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('.ion-page:not(.ion-page-hidden) .data-table--fill, .ion-page:not(.ion-page-hidden) .data-table--fill *')]
      .filter((node) => ['auto', 'scroll'].includes(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight + 1)
      .map((node) => node.getAttribute('class') ?? node.tagName),
  );
}

async function openInvoices(page: Page, width: number): Promise<void> {
  await page.setViewportSize({ width, height: VIEWPORTS.find((v) => v.width === width)!.height });
  await page.goto('/billing/invoices');
  await expect(page.getByTestId('invoices-row')).toHaveCount(4);
  await settled(page);
}

const heading = (page: Page) => page.locator('.data-table--fill .data-table__title-wrap');
const search = (page: Page) => page.locator('.data-table--fill .data-table__search');

for (const { width } of VIEWPORTS) {
  test(`Invoices at ${width} px: the list fills the page, its search and heading as before, «Filters» filters`, async ({ page }) => {
    const errors = watchPageErrors(page);
    await openInvoices(page, width);
    await expect(search(page)).toBeVisible();
    if (width === 390) {
      // The topbar and the tabbar name the list: a list with a search drops its heading on a phone, where the
      // list grows with its rows under what waits for a payment (one scroll, DataTable's own `fill`).
      await expect(heading(page)).toBeHidden();
      expect(await nestedScrollers(page), 'a second scroll inside the list at 390').toEqual([]);
    } else {
      await expect(heading(page)).toBeVisible();
      const fill = await listFill(page);
      expect(fill.pageScrolls, `the page scrolls at ${width}`).toBe(false);
      expect(Math.abs(fill.offBy), `the list ends ${fill.offBy}px short of the page at ${width}`).toBeLessThanOrEqual(2);
      // Its toolbar and its footer on screen: the rows scroll inside.
      await expect(page.locator('.data-table--fill .data-table__bar')).toBeInViewport();
      await expect(page.locator('.data-table--fill .data-table__pager')).toBeInViewport();
    }
    await page.screenshot({ path: shot(`FIX-DATATABLE-SAAS-${width}`) });

    // «Filters»: the SaaS's own popover, kept in the address and counted on the button; DataTable's funnel
    // (`filterable`, opt-in) stays off here.
    await expect(page.locator('.data-table--fill .data-table__filter-button')).toHaveCount(0);
    await expect(page.getByTestId('invoices-filters')).toBeVisible();
    const paid = await page.request.get('/api/billing/invoices?status=paid&limit=50');
    expect(paid.status()).toBe(200);
    const paidRows = ((await paid.json()) as { rows: unknown[] }).rows.length;
    expect(paidRows).toBeGreaterThan(0);
    expect(paidRows).toBeLessThan(4);
    await page.getByTestId('invoices-filters').click();
    await expect(page.getByTestId('invoices-filters-panel')).toBeVisible();
    await page.getByTestId('invoices-status').locator('ion-segment-button').filter({ hasText: 'Paid' }).click();
    await expect(page).toHaveURL(/status=paid/);
    await expect(page.getByTestId('invoices-filters-count')).toHaveText('1');
    await settled(page);
    await page.screenshot({ path: shot(`FIX-DATATABLE-SAAS-${width}-filters`) });
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('invoices-filters-panel')).toBeHidden();
    await expect(page.getByTestId('invoices-row')).toHaveCount(paidRows);
    expect(errors).toEqual([]);
  });
}

test('the check of the check: without the `.panel-fill` chain the list stops filling and the phone shows its heading; a scroll inside the list is seen', async ({ page }) => {
  const dropChain = () =>
    page.evaluate(() => {
      for (const stack of document.querySelectorAll('.panel-fill')) stack.classList.remove('panel-fill');
    });
  await openInvoices(page, 1440);
  await dropChain();
  expect(Math.abs((await listFill(page)).offBy)).toBeGreaterThan(2);
  await openInvoices(page, 390);
  await expect(heading(page)).toBeHidden();
  // A list whose cards scroll on their own (the double scroll) is what nestedScrollers reports.
  expect(await nestedScrollers(page)).toEqual([]);
  await page.evaluate(() => {
    const cards = document.querySelector<HTMLElement>('.ion-page:not(.ion-page-hidden) .data-table--fill .data-table__cards');
    if (!cards) throw new Error('no cards on the phone');
    Object.assign(cards.style, { maxHeight: '60px', overflowY: 'auto' });
  });
  expect(await nestedScrollers(page)).not.toEqual([]);
  await dropChain();
  await expect(heading(page)).toBeVisible();
});
