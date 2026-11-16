// Promo codes of free months, at the three sizes (390×844, 834×1112, 1440×900), against the panel's own Django and
// the rows of billing_free_months_seed.py. Stripe does not run here: `billing.checkout.start` is answered at the API's
// edge and Stripe.js is the double of stripe.ts (`gotoWithCheckout`); everything else is the real server. Each test
// names its flow of billing/WORKBOOK.md in its title.
// flow: BILLING-F12 BILLING-F23 BILLING-F36 — the invoices of 0 € themselves: billing/tests/test_zero_invoices_everywhere.py.
import { panelAccount } from './accounts';
import { businessIdOf } from './businesses';
import { djangoPrint } from './django';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { captureAtEverySize } from './screen';
import { gotoWithCheckout } from './stripe';

seededAndSignedInWarm('billing_free_months_seed.py', panelAccount('free-months'));
const atEverySize = captureAtEverySize('APP-BILLING-FREE-MONTHS');

test.describe('promo codes of free months', () => {
  test('BILLING-F12: a code of six free months is applied in the Store, and the checkout says when the plan’s price starts', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Libre');
    const started = await gotoWithCheckout(page, `/dashboard/store/plans?business=${cafe}`);
    await page.getByTestId('store-promo-toggle').click();
    await page.getByTestId('store-promo-code').locator('input').fill('E2E_TESTERS');
    await page.getByTestId('store-promo-apply').click();
    await expect(page.getByTestId('store-promo-result')).toHaveText('Code e2e_testers: 6 months free, then the plan’s regular price.');
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    const dialog = page.getByTestId('checkout-modal');
    const notice = dialog.getByTestId('checkout-free-months');
    await atEverySize(page, 'checkout', async () => {
      await expect(notice).toHaveText('6 months free, then €29.99/month. Your card is not charged until then.');
      await expect(dialog.getByTestId('stripe-double')).toBeVisible();
    });
    expect(started).toEqual([{ hub_id: cafe, plan: 'starter', interval: 'month', promo_code: 'e2e_testers' }]);
    expect(errors).toEqual([]);
  });

  test('BILLING-F12: a code of free months is only for a monthly plan: the yearly checkout is refused and says why', async ({ page }) => {
    const cafe = await businessIdOf(page.request, 'Café Libre');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({
        status: 409,
        json: { error: { code: 'billing.promo_monthly_only', message: 'This code gives free months of a monthly plan: choose monthly billing to use it.' } },
      }),
    );
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await page.getByTestId('store-promo-toggle').click();
    await page.getByTestId('store-promo-code').locator('input').fill('e2e_testers');
    await page.getByTestId('store-promo-apply').click();
    await page.getByTestId('store-period-year').click();
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    await expect(page.getByTestId('checkout-modal').getByTestId('checkout-error')).toContainText('choose monthly billing to use it');
  });

  test('BILLING-F23: the subscription on free months says until when, and its next invoice is 0 €', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard/billing/subscriptions');
    const row = page.getByTestId('subscriptions-row').filter({ hasText: 'Panadería Gratis' });
    await atEverySize(page, 'subscriptions', async () => {
      await expect(row.getByTestId('subscription-free-until')).toContainText('Free until');
      await expect(row).toContainText('€0.00');
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-F36: the invoice of a free month is 0 € and its line says the discount', async ({ page }) => {
    const errors = watchPageErrors(page);
    const id = djangoPrint('from billing.models import Invoice\nprint(Invoice.objects.get(series="E2EFM").id)').trim();
    await page.goto(`/dashboard/billing/invoices/${id}`);
    await atEverySize(page, 'invoice', async () => {
      await expect(page.getByTestId('invoice-line-discount')).toHaveText('Discount -€29.99');
      await expect(page.getByTestId('invoice-totals')).toContainText('€0.00');
    });
    expect(errors).toEqual([]);
  });
});
