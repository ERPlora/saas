// Promo codes of a discount, at the three sizes (390×844, 834×1112, 1440×900), against the panel's own Django and
// the rows of store_seed.py plus a code of a discount of all of it for six months, used by Panadería López with the
// invoice of its first month (`DISCOUNT`). Stripe does not run here: `billing.checkout.start` is answered at the API's edge and Stripe.js
// is the double of stripe.ts (`gotoWithCheckout`); everything else is the real server. Each test names its flow of
// billing/WORKBOOK.md in its title.
// flow: BILLING-F12 BILLING-F23 BILLING-F36 — the invoices of 0 € themselves: billing/tests/test_zero_invoices_everywhere.py.
import { panelAccount, qaAccount } from './accounts';
import { businessIdOf } from './businesses';
import { djangoPrintWarm } from './django';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { captureAtEverySize } from './screen';
import { gotoWithCheckout } from './stripe';

seededAndSignedInWarm('store_seed.py', qaAccount('STORE', panelAccount('store')));
const atEverySize = captureAtEverySize('APP-BILLING-DISCOUNTS');

/** The rows of the discount, written again: free for six months with the code `e2e_testers`, its use on Panadería
 *  López's subscription until 150 days from now, and that business's invoice of its first month (0 €, all of
 *  Starter's price discounted). */
const DISCOUNT = `
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from billing.models import Discount, Invoice, InvoiceLine, PromoCode, PromoRedemption
from hubs.models import Hub
Invoice.objects.filter(series="E2EFM").delete()
PromoCode.objects.filter(code="e2e_testers").delete()
Discount.objects.filter(name="E2E testers").delete()
bakery = Hub.objects.select_related("billing_profile").get(slug="e2e-store-panaderia")
discount = Discount.objects.create(name="E2E testers", percent_off=100, duration="repeating", duration_in_months=6)
promo = PromoCode.objects.create(code="e2e_testers", discount=discount)
PromoRedemption.objects.create(promo=promo, hub=bakery, stripe_customer_id="cus_panaderia",
    stripe_subscription_id="sub_panaderia", discount_ends_at=timezone.now() + timedelta(days=150))
today = timezone.localdate()
invoice = Invoice.objects.create(hub=bakery, business_name=bakery.name, billing_profile=bakery.billing_profile,
    payer_account=bakery.billing_profile.owner, stripe_invoice_id="in_e2e_discounted_month", payment_status="paid",
    series="E2EFM", sequence=1, number=f"E2EFM-{today.year}-00001", issued_on=today, paid_at=timezone.now(),
    billed_at=timezone.now(), tax_treatment="domestic", tax_country="ES", tax_rate=Decimal("21.00"),
    fiscal_status="accepted", payer_name=f"{bakery.name} SL", payer_country="ES")
InvoiceLine.objects.create(invoice=invoice, position=1, description="1 × Starter", item_kind="plan",
    item_slug="starter", tax_category_id="service.saas_subscription", tax_treatment="domestic",
    tax_rate=Decimal("21.00"), discount_cents=2999)
print(invoice.id)
`;
let invoiceId = '';
test.beforeEach(async () => {
  invoiceId = await djangoPrintWarm(DISCOUNT);
});
test.afterAll(() =>
  djangoPrintWarm(
    'from billing.models import Discount, Invoice, PromoCode\nInvoice.objects.filter(series="E2EFM").delete()\n' +
      'PromoCode.objects.filter(code="e2e_testers").delete()\nDiscount.objects.filter(name="E2E testers").delete()',
  ),
);

test.describe('promo codes of a discount', () => {
  test('BILLING-F12: a code of a discount is applied in the Store, and the checkout says it and when the plan’s price starts', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started = await gotoWithCheckout(page, `/dashboard/store/plans?business=${cafe}`);
    await page.getByTestId('store-promo-toggle').click();
    await page.getByTestId('store-promo-code').locator('input').fill('E2E_TESTERS');
    await page.getByTestId('store-promo-apply').click();
    await expect(page.getByTestId('store-promo-result')).toHaveText('Code e2e_testers: Free for 6 months.');
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    const dialog = page.getByTestId('checkout-modal');
    const notice = dialog.getByTestId('checkout-discount');
    await atEverySize(page, 'checkout', async () => {
      await expect(notice).toHaveText('Free for 6 months. Then €29.99/month + VAT. Your card is not charged today.');
      await expect(dialog.getByTestId('stripe-double')).toBeVisible();
    });
    expect(started).toEqual([{ hub_id: cafe, plan: 'starter', interval: 'month', promo_code: 'e2e_testers' }]);
    expect(errors).toEqual([]);
  });

  test('BILLING-F12: a discount for months is only for a monthly plan: the yearly checkout is refused and says why', async ({ page }) => {
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({
        status: 409,
        json: { error: { code: 'billing.discount_monthly_only', message: 'This code’s discount lasts a number of months: choose monthly billing to use it.' } },
      }),
    );
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await page.getByTestId('store-promo-toggle').click();
    await page.getByTestId('store-promo-code').locator('input').fill('e2e_testers');
    await page.getByTestId('store-promo-apply').click();
    await page.getByTestId('store-period-year').click();
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    await expect(page.getByTestId('checkout-modal').getByTestId('checkout-error')).toContainText('choose monthly billing to use it');
    await expect(page.getByTestId('checkout-modal').getByTestId('checkout-discount')).toHaveCount(0);
  });

  test('BILLING-F23: the subscription with a discount says until when, and its next invoice is 0 €', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard/billing/subscriptions');
    const row = page.getByTestId('subscriptions-row').filter({ hasText: 'Panadería López' });
    await atEverySize(page, 'subscriptions', async () => {
      await expect(row.getByTestId('subscription-discount')).toContainText('Free until');
      await expect(row).toContainText('€0.00');
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-F36: the invoice of a month all discounted is 0 € and its line says the discount', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto(`/dashboard/billing/invoices/${invoiceId}`);
    await atEverySize(page, 'invoice', async () => {
      await expect(page.getByTestId('invoice-line-discount')).toHaveText('Discount -€29.99');
      await expect(page.getByTestId('invoice-totals')).toContainText('€0.00');
    });
    expect(errors).toEqual([]);
  });
});
