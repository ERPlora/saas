// Billing › Subscriptions after a business is deleted, in Chrome against the panel's own Django and the rows of
// billing_seed.py: the business is deleted through the real route, and its row then says what its own page says —
// «Being deleted», with no next invoice and nothing to change — while the other businesses of the account still renew.
import { panelAccount, qaAccount } from './accounts';
import { businessIdOf } from './businesses';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { settled, shot, sidewaysScroll } from './screen';
import { apiPost } from './session';

const BILLING = qaAccount('BILLING', panelAccount('billing'));

seededAndSignedInWarm('billing_seed.py', BILLING);

test('HUBS-F18 + BILLING-F23: a deleted business is «Being deleted» in Subscriptions, as on its own page, with no next invoice', async ({ page }) => {
  const errors = watchPageErrors(page);
  const bakery = await businessIdOf(page.request, 'Panadería López');
  const plaza = await businessIdOf(page.request, 'Bar La Plaza');
  const deleted = await apiPost(page.request, '/api/hubs/businesses/delete', { id: bakery, confirm_name: 'Panadería López' });
  expect(deleted.status(), await deleted.text()).toBe(200);

  await page.goto(`/dashboard/businesses/${bakery}/summary`);
  await expect(page.locator('.biz-header__pills .status-pill')).toHaveText('Being deleted');

  await page.goto('/dashboard/billing/subscriptions');
  const row = page.locator(`[data-testid="subscriptions-row"][data-id="${bakery}"]`);
  await expect(row.locator('.status-pill')).toHaveText('Being deleted');
  await expect(row).not.toContainText('Active');
  await expect(row).not.toContainText('with VAT');
  // Nothing to change on a deleted business: only its invoices.
  await expect(row.locator(`[data-testid^="subscriptions-row-${bakery}-"]`)).toHaveCount(1);
  await expect(row.getByTestId(`subscriptions-row-${bakery}-view_invoices`)).toBeVisible();
  // Another business of the account still renews as before.
  await expect(page.locator(`[data-testid="subscriptions-row"][data-id="${plaza}"]`)).toContainText('with VAT');

  for (const [width, height] of [[1440, 900], [820, 1180], [375, 667]] as const) {
    await page.setViewportSize({ width, height });
    await settled(page);
    expect(await sidewaysScroll(page), `${width}x${height}`).toEqual([]);
    // A card of its own below 1000 px, still «Being deleted»; brought into view for the capture.
    await expect(row.locator('.status-pill')).toHaveText('Being deleted');
    await row.scrollIntoViewIfNeeded();
    await settled(page);
    await page.screenshot({ path: shot(`billing-deleted-subscriptions-${width}x${height}`), fullPage: true });
  }
  expect(errors).toEqual([]);
});
