// Businesses (`/businesses`, mockups `businesses.html`) in Ioan's Chrome: the account's businesses in
// the DataTable with their statuses, the banners of what waits (an invitation, an unpaid invoice), the
// cards on a phone, «Manage» into a business's page and its four sections, and «Delete» → «Recover».
import { type Page } from '@playwright/test';

import { expect, panelAccount, seedPanel, signIn, test, watchPageErrors } from './fixtures';

/** A section of the business: each has its address, so Ionic slides the next page in over the last
 *  one, which it then drops; the tabbar is clicked once only one page is left. */
async function openSection(page: Page, id: string): Promise<void> {
  await expect(page.getByTestId(`tab-${id}`)).toHaveCount(1);
  await page.getByTestId(`tab-${id}`).click();
  await expect(page).toHaveURL(new RegExp(`/${id}$`));
  await expect(page.getByTestId(`tab-${id}`)).toHaveCount(1);
}

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('lists the businesses with their status, plan and role, and what waits above them', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  await page.goto('/businesses');
  const rows = page.getByTestId('businesses-row');
  await expect(rows).toHaveCount(4);
  await expect(rows.first()).toContainText('Panadería López');
  await expect(rows.filter({ hasText: 'Café Central' })).toContainText('Preparing');
  await expect(rows.filter({ hasText: 'Bar La Plaza' })).toContainText('Payment due');
  await expect(rows.filter({ hasText: 'Peluquería Ana' })).toContainText('Managed by the owner');
  await expect(page.getByTestId('businesses-pager').or(page.locator('.data-table__pager'))).toContainText('4');
  await expect(page.locator('[data-testid^="businesses-unpaid-"]')).toContainText('Bar La Plaza has an unpaid invoice');
  await expect(page.locator('[data-testid^="businesses-invitation-"]')).toContainText('You have been invited to Bar Norte');
  // A manager may open the business but not manage it.
  await expect(page.locator('[data-testid$="-manage"]')).toHaveCount(3);
  expect(errors).toEqual([]);
});

test('on a phone the businesses are cards, with their actions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page.request, panelAccount('several'));
  await page.goto('/businesses');
  await expect(page.locator('.data-table__card').first()).toContainText('Panadería López');
  await expect(page.locator('.data-table__card')).toHaveCount(4);
});

test('«Manage» opens the business’s page, whose tabbar walks its four sections', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  await page.goto('/businesses');
  await page.getByTestId('businesses-row').first().locator('[data-testid$="-manage"]').click();
  await expect(page).toHaveURL(/\/businesses\/[0-9a-f-]+\/summary$/);
  await expect(page.getByTestId('business-header')).toContainText('Panadería López');
  await expect(page.getByTestId('summary-plan')).toContainText('Starter');
  await openSection(page, 'members');
  await expect(page.getByTestId('members-row')).toHaveCount(5);
  await expect(page.getByTestId('members-row').filter({ hasText: 'e2e-jorge@example.com' })).toContainText('Pending');
  await openSection(page, 'modules');
  await expect(page.getByTestId('business-modules')).toContainText('Apps are turned on and off inside the business');
  await openSection(page, 'settings');
  await expect(page.getByTestId('settings-general')).toBeVisible();
  await expect(page.getByTestId('danger-zone')).toContainText('Delete business');
  expect(errors).toEqual([]);
});

// Café Central is Free: it comes back on Free (the account's one free business), so it can be recovered.
test('«Delete» lives in the business’s Settings and asks for the name; deleted, «Recover» brings it back', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  await page.goto('/businesses');
  const cafe = page.getByTestId('businesses-row').filter({ hasText: 'Café Central' });
  await expect(cafe.locator('[data-testid$="-delete"]')).toHaveCount(0);
  await cafe.locator('[data-testid$="-manage"]').click();
  await expect(page).toHaveURL(/\/summary$/);
  await openSection(page, 'settings');
  await page.getByTestId('danger-delete').click();
  await expect(page.getByTestId('delete-dialog')).toContainText('You can recover it for 90 days');
  // An ion-button says it is disabled to assistive tech, not with the native attribute.
  await expect(page.getByTestId('delete-dialog-submit')).toHaveAttribute('aria-disabled', 'true');
  await page.getByTestId('delete-dialog-input').locator('input').fill('Café Central');
  await page.getByTestId('delete-dialog-submit').click();
  await expect(page.getByTestId('business-deleted')).toContainText('It will be erased for good on');
  await page.getByTestId('business-restore').click();
  await expect(page.getByTestId('business-deleted')).toHaveCount(0);
  await page.goto('/businesses');
  await expect(cafe).toContainText('Preparing');
  expect(errors).toEqual([]);
});
