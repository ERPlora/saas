// The unpaid invoices in the bell of the panel's topbar (BILLING-F16, BILLING-F17), in Chrome against the rows of
// billing_seed.py: Bar La Plaza, whose card the bank declined 4 days ago, and Bar Norte, a soft failure 2 days ago.
// With them the bell is a red pill with their number at every width; its panel features the most urgent with what it
// owes and its way out; paying one leaves the other; with nothing unpaid the bell is bare; and no page paints a
// notice of its own. Stripe's pages are played at their boundary.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { panelAccount, qaAccount } from './accounts';
import { djangoPrintWarm } from './django';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { expectBell, featureNotice, openNotices, primary, secondary } from './notices';
import { watchPageErrors } from './page-events';
import { settled, toast } from './screen';

const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/billing-notices-shots';
mkdirSync(SHOTS_DIR, { recursive: true });

const BILLING = qaAccount('BILLING', panelAccount('billing'));
const SIZES = [
  { width: 390, height: 844 },
  { width: 834, height: 1194 },
  { width: 1440, height: 900 },
] as const;

seededAndSignedInWarm('billing_seed.py', BILLING);

/** Each seeded business and the number its invoice takes once paid. */
const PAID_NUMBERS = { norte: 90120, plaza: 90121 } as const;

/** What Stripe's `invoice.paid` leaves behind, played with the ORM: the invoice numbered, the business up to date. */
async function playPaid(...keys: Array<keyof typeof PAID_NUMBERS>): Promise<void> {
  const numbers = Object.fromEntries(keys.map((key) => [key, PAID_NUMBERS[key]]));
  await djangoPrintWarm(
    [
      'from django.utils import timezone',
      'from billing.models import Invoice',
      'from hubs.models import Hub, Subscription',
      `for key, sequence in ${JSON.stringify(numbers)}.items():`,
      '    invoice = Invoice.objects.get(stripe_invoice_id=f"in_e2e_billing_{key}")',
      '    Invoice.objects.filter(pk=invoice.pk).update(payment_status="paid", number=f"ERP-2026-{sequence}", series="ERP", sequence=sequence, issued_on=timezone.localdate(), paid_at=timezone.now(), fiscal_status="issuing")',
      '    Subscription.objects.filter(hub_id=invoice.hub_id).update(status="active", unpaid_reason="", unpaid_since=None, unpaid_invoice_url="")',
      '    Hub.objects.filter(pk=invoice.hub_id).update(status="active")',
    ].join('\n'),
  );
}

async function capture(page: Page, name: string): Promise<void> {
  await settled(page);
  await page.screenshot({ path: join(SHOTS_DIR, `${name}.png`) });
}

/** Businesses at each width, in each theme, once its rows are there; `check` gets the `<width>-<theme>` of its shots. */
async function onBusinesses(page: Page, themes: readonly ('light' | 'dark')[], check: (size: string) => Promise<void>): Promise<void> {
  for (const theme of themes) {
    await page.emulateMedia({ colorScheme: theme });
    for (const size of SIZES) {
      await page.setViewportSize(size);
      await page.goto('/dashboard/businesses');
      await expect(page.getByTestId('businesses-row').first()).toBeVisible();
      await check(`${size.width}-${theme}`);
    }
  }
}

test.describe('the unpaid invoices in the bell', () => {
  test('a red pill with their number at every width; Businesses and Billing paint no notice of their own', async ({ page }) => {
    const errors = watchPageErrors(page);
    await onBusinesses(page, ['light', 'dark'], async (size) => {
      await expectBell(page, 2);
      await expect(page.locator('[data-testid^="businesses-unpaid"]')).toHaveCount(0);
      await capture(page, `bell-businesses-${size}`);
    });
    await page.goto('/dashboard/billing/subscriptions');
    await expect(page.getByTestId('subscriptions-row').first()).toBeVisible();
    await expectBell(page, 2);
    await expect(page.locator('[data-testid^="billing-unpaid"], [data-testid^="unpaid-group"]')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('its panel features the most urgent with what it owes and its way out; each other one is a row', async ({ page }) => {
    const errors = watchPageErrors(page);
    await onBusinesses(page, ['light', 'dark'], async (size) => {
      // Bar La Plaza ends its grace first; the bank declined its card: «Change card» is its one way out.
      const plaza = await featureNotice(page, 'Bar La Plaza');
      await expect(plaza.locator('h3')).toHaveText('Bar La Plaza has an unpaid invoice');
      await expect(plaza).toContainText('Urgent · 3 days left');
      await expect(plaza.locator('.action-featured__figure')).toHaveText('€36.29');
      await expect(plaza).toContainText(/The bank declined the card\. If it is not paid by \w{3} \d{1,2}, \d{4}, the business is suspended\./);
      expect(await plaza.innerText()).not.toMatch(/\d{1,2}:\d{2}/);
      await expect(primary(plaza)).toHaveText('Change card');
      await expect(secondary(plaza)).toHaveCount(0);
      await expect(page.getByTestId('action-row')).toHaveText([/Bar Norte has an unpaid invoice\s*5 days left/]);
      await capture(page, `panel-plaza-${size}`);
      const norte = await featureNotice(page, 'Bar Norte');
      await expect(primary(norte)).toHaveText('Pay the invoice · €36.29');
      await expect(secondary(norte)).toHaveText('Change card');
      await capture(page, `panel-norte-${size}`);
      await page.getByTestId('action-panel-close').click();
      await expect(page.getByTestId('action-panel')).toBeHidden();
    });
    expect(errors).toEqual([]);
  });

  test('«Pay the invoice» goes to Stripe’s page for it and, paid, its notice leaves: one is left', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.route(/^https:\/\/invoice\.stripe\.com\//, (route) =>
      route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
    );
    await page.goto('/dashboard/businesses');
    const norte = await featureNotice(page, 'Bar Norte');
    await primary(norte).click();
    await page.waitForURL('https://invoice.stripe.com/i/e2e-billing-norte');
    await playPaid('norte');
    await page.goto('/dashboard/businesses');
    await expect(toast(page, 'Invoice paid: Bar Norte is up to date again')).toBeVisible();
    await expectBell(page, 1);
    const panel = await openNotices(page);
    await expect(panel.getByTestId('action-featured').locator('h3')).toHaveText('Bar La Plaza has an unpaid invoice');
    await expect(panel.getByTestId('action-row')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('with nothing unpaid the bell is bare and its panel says all is clear', async ({ page }) => {
    await playPaid('plaza', 'norte');
    await onBusinesses(page, ['light'], async (size) => {
      await expectBell(page, 0);
      await capture(page, `bell-clear-${size}`);
    });
    const panel = await openNotices(page);
    await expect(panel.getByTestId('action-panel-empty')).toContainText('All caught up');
  });
});
