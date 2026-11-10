// flow: ninguno — layout check of the panel by touch after ui#131 (saas#389): no flow changes, only the size of a button
// With a coarse pointer `@erplora/ui` gives every `ion-button size="small"` at least 44×44 px (ui#131). The panel's
// screens whose components use them (the businesses, a business's summary, members and settings, the account's profile
// and security, billing's invoices and payment, the store's plans) at a phone and a tablet with touch: nothing scrolls
// sideways and every small button on screen measures 44 px at least. The rows are panel_seed.py's (`e2e-several`, as
// businesses.spec.ts reads them); nothing is created, changed or removed.
import type { Locator, Page } from '@playwright/test';

import { businessIdOf, expect, expectNoSidewaysScroll, panelAccount, seedPanel, settled, signIn, test } from './fixtures';

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
];
/** ui#131: a small button's minimum with a coarse pointer. */
const TOUCH_TARGET = 44;

/** The panel page on screen (hidden pages stay in the DOM). */
const shown = (page: Page): Locator => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** Each screen and what says it has loaded: its rows, or what it shows without them. */
function screens(id: string): Array<{ path: string; ready: (page: Page) => Locator }> {
  return [
    { path: '/dashboard/businesses', ready: (page) => shown(page).getByTestId('businesses-row').first() },
    { path: `/dashboard/businesses/${id}/summary`, ready: (page) => shown(page).getByTestId('summary-plan') },
    { path: `/dashboard/businesses/${id}/members`, ready: (page) => shown(page).getByTestId('members-row').first() },
    { path: `/dashboard/businesses/${id}/settings`, ready: (page) => shown(page).getByTestId('settings-general') },
    { path: '/dashboard/account/profile', ready: (page) => shown(page).getByTestId('profile-first-name') },
    { path: '/dashboard/account/security', ready: (page) => shown(page).getByTestId('sessions-row').first() },
    {
      path: '/dashboard/billing/invoices',
      ready: (page) => shown(page).getByTestId('invoices-row').first().or(shown(page).getByTestId('invoices-empty')),
    },
    {
      path: '/dashboard/billing/payment',
      ready: (page) =>
        shown(page)
          .getByTestId('payment-change')
          .or(shown(page).getByTestId('payment-method-empty'))
          .or(shown(page).getByTestId('payment-profile-empty'))
          .first(),
    },
    { path: '/dashboard/store/plans', ready: (page) => shown(page).getByTestId('store-plans') },
  ];
}

test.use({ hasTouch: true });
test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

for (const viewport of VIEWPORTS) {
  test(`saas#389: by touch at ${viewport.width}x${viewport.height}, no panel screen scrolls sideways and its small buttons are ${TOUCH_TARGET} px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await signIn(page.request, panelAccount('several'));
    const id = await businessIdOf(page.request, 'Panadería López');
    for (const screen of screens(id)) {
      const where = `${screen.path} by touch at ${viewport.width}px`;
      await page.goto(screen.path);
      await expect(screen.ready(page), `${where}: loaded`).toBeVisible();
      await settled(page);
      await expectNoSidewaysScroll(page, `${where}: nothing scrolls sideways`);
      const boxes = await shown(page)
        .locator('ion-button[size="small"]:visible')
        .evaluateAll((elements) =>
          elements.map((element) => {
            const rect = element.getBoundingClientRect();
            const name = element.getAttribute('data-testid') ?? element.getAttribute('aria-label') ?? element.textContent?.trim();
            return { name: name ?? element.tagName, width: rect.width, height: rect.height };
          }),
        );
      for (const box of boxes) {
        expect.soft(box.width, `${where}: ${box.name} width`).toBeGreaterThanOrEqual(TOUCH_TARGET);
        expect.soft(box.height, `${where}: ${box.name} height`).toBeGreaterThanOrEqual(TOUCH_TARGET);
      }
    }
  });
}
