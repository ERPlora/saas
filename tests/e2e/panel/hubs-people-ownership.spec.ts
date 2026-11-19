// HUBS-F28 of hubs/WORKBOOK.md (hand the business over) on its screens, at the three sizes (390×844, 834×1112,
// 1440×900); the other flows of «the people of a business» are in hubs-people.spec.ts.
//
// The spec plays the Hub (`startHubDouble`, as panel/members.spec.ts): it sees the snapshot of each change; no Hub
// runs. Stripe does not run either (no keys in the e2e stack): what calls it runs in the server's own code with Stripe
// at its boundary (`withStripe`, the double of the Python tests), and the page plays Stripe.js and the one call that
// opens a payment (`playStripe` of stripe.ts). Each test has its own accounts (`e2e-hubs3-…@example.com`, their
// address proven) and its own business, created through the API as the panel creates it; the people join it through
// the operations (invite, then accept), never written by hand.
import { djangoPrintWarm } from './django';
import { expect, freezeFrontend, test } from './fixtures';
import { type HubDouble, startHubDouble } from './hub';
import { waitForMail } from './mail';
import { watchPageErrors } from './page-events';
import {
  account,
  browserOf,
  businessOf,
  joins,
  membersOf,
  PANEL,
  PASSWORD,
  paintMail,
  removeOwnRows,
  roleInLastSnapshot,
  rowOf,
  shown,
} from './people';
import { PANEL_URL } from './project';
import { captureAtEverySize, toast } from './screen';
import { apiPost, signIn } from './session';
import { payInStripe, playStripe } from './stripe';

const atEverySize = captureAtEverySize('APP-HUBS-3');

/**
 * `code` run in the server's own code with Stripe at its boundary: `double` (billing/tests/stripe_double.py, as the Python
 * tests) answers what Stripe would; the operations of hubs and billing are the real ones, on this run's database. The
 * warm Django runs it, and it outlives the snippet: Stripe's keys and client are put back as they were when it ends.
 */
async function withStripe(code: string[]): Promise<string> {
  return djangoPrintWarm(
    [
      'from unittest import mock',
      'from django.test import override_settings',
      'from billing import stripe_service',
      'from billing.tests.stripe_double import StripeDouble, item, subscription',
      'double = StripeDouble()',
      'with override_settings(STRIPE_SECRET_KEY="rk_test_double", STRIPE_PUBLISHABLE_KEY="pk_test_double"), mock.patch.object(stripe_service, "client", lambda: double):',
      ...code.map((line) => `    ${line}`),
    ].join('\n'),
  );
}

let hub: HubDouble;

test.beforeAll(async () => {
  await removeOwnRows();
  hub = await startHubDouble();
});
test.afterAll(async () => {
  await hub?.close();
  await removeOwnRows();
});

test('HUBS-F28: the owner offers the business to a member, who accepts it on Businesses from the mail’s link', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('hand-owner', 'Olga', 'Ruiz');
  const carlos = await account('hand-carlos', 'Carlos', 'Mora');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, carlos, 'hub_admin');
  const member = await rowOf(page, id, carlos.email);

  await page.goto(`/dashboard/businesses/${id}/members`);
  await shown(page).getByTestId(`members-row-${member.id}-menu`).click();
  await page.locator('ion-popover.data-table__row-menu').getByTestId(`members-row-${member.id}-transfer`).click();
  const dialog = page.getByTestId('transfer-dialog');
  await atEverySize(page, 'HUBS-G82', async () => {
    await expect(dialog).toContainText('Transfer Bar Manolo');
    await expect(dialog).toContainText('A paid plan stays until the end of the period already paid; then the new owner pays it with their card, and the current one is not charged again.');
  });
  await expect(dialog.getByTestId('transfer-dialog-submit')).toHaveAttribute('aria-disabled', 'true');
  await page.getByTestId('transfer-dialog-input').locator('input').fill('Bar Manolo');
  const offeredAt = Date.now();
  await dialog.getByTestId('transfer-dialog-submit').click();
  await expect(page.getByText(`Offer sent to ${carlos.email}: they have 7 days to accept it`)).toBeVisible();
  await expect(shown(page).getByTestId('members-transfer')).toContainText(`Ownership offered to ${carlos.email}`);
  // A second offer while this one waits is refused.
  const again = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(again.status()).toBe(409);

  // Carlos follows the mail's link: Businesses, with the offer on top.
  const link = await waitForMail(carlos.email, offeredAt, new RegExp(`${PANEL}/dashboard/businesses(?=\\s|$)`, 'm'));
  const { context, page: theirs, errors: theirErrors } = await browserOf(browser, carlos);
  await theirs.goto(link);
  const offer = shown(theirs).locator('[data-testid^="businesses-offer-"]');
  await atEverySize(theirs, 'HUBS-G82-accept', async () => {
    await expect(offer).toContainText(`${owner.email} offers you Bar Manolo`);
  });
  const acceptedAt = Date.now();
  await offer.getByTestId('offer-accept').click();
  await expect(theirs.getByText('You are now the owner of Bar Manolo')).toBeVisible();

  // The two roles swap: Carlos owns it, Olga stays as admin; the Hub hears it, and the outgoing owner is told
  // where to see what they still pay.
  const roles = Object.fromEntries((await membersOf(theirs, id)).map((one) => [one.email, one.role]));
  expect(roles).toEqual({ [owner.email]: 'hub_admin', [carlos.email]: 'hub_owner' });
  await expect.poll(() => roleInLastSnapshot(hub, id, carlos.email)).toBe('hub_owner');
  await waitForMail(owner.email, acceptedAt, new RegExp(`${PANEL}/dashboard/businesses/${id}(?=\\s|$)`, 'm'));
  await context.close();
  expect(theirErrors).toEqual([]);
  expect(errors).toEqual([]);
});

test('HUBS-F28: a business handed over on a paid plan: the new owner keeps it with their card, nothing charged today', async ({
  page,
  browser,
}) => {
  const errors = watchPageErrors(page);
  const owner = await account('paid-owner', 'Olga', 'Ruiz');
  const carlos = await account('paid-carlos', 'Carlos', 'Mora');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, carlos, 'hub_admin');
  const member = await rowOf(page, id, carlos.email);
  const stamp = Date.now();
  const [oldSub, oldCustomer, newSub, newCustomer] = [`sub_e2e_old_${stamp}`, `cus_e2e_olga_${stamp}`, `sub_e2e_new_${stamp}`, `cus_e2e_carlos_${stamp}`];
  // Olga pays Starter with her card, as the webhook of her checkout leaves it.
  await djangoPrintWarm(
    [
      'from datetime import timedelta',
      'from django.utils import timezone',
      'from hubs.schemas.subscriptions import SubscriptionApplyIn',
      'from hubs.services import hub_callbacks, subscription_sync',
      'now = timezone.now()',
      `subscription_sync.subscription_apply(hub_callbacks.system_ctx_for("${id}"), SubscriptionApplyIn(hub_id="${id}", plan="starter", billing_interval="month", status="active", stripe_customer_id="${oldCustomer}", stripe_subscription_id="${oldSub}", current_period_start=now - timedelta(days=10), current_period_end=now + timedelta(days=20), cancel_at_period_end=False))`,
    ].join('\n'),
  );
  // She offers it to Carlos; he accepts (`hubs.ownership.accept`, which stops her renewal in Stripe).
  const offered = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(offered.status(), await offered.text()).toBe(200);
  const transfer = ((await offered.json()) as { id: string }).id;
  await withStripe([
    'from django.contrib.auth import get_user_model',
    'from hubs.schemas.common import ByIdIn',
    'from hubs.services import ownership',
    'from hubs.tests.conftest import ctx_for',
    `double.answer("subscriptions.update", subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True))`,
    `ownership.ownership_accept(ctx_for(get_user_model().objects.get(email="${carlos.email}")), ByIdIn(id="${transfer}"))`,
    'assert [call.params for call in double.calls_to("subscriptions.update")] == [{"cancel_at_period_end": True}], double.paths()',
  ]);

  // Carlos, now its owner, sees in Billing that the plan is on another account's card until its period ends.
  const { context, page: theirs, errors: theirErrors } = await browserOf(browser, carlos);
  await playStripe(theirs);
  const opened: unknown[] = [];
  await theirs.route('**/api/billing/plan/take-over', async (route) => {
    opened.push(route.request().postDataJSON());
    await route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e_keep', client_secret: 'cs_test_e2e_keep_secret', publishable_key: 'pk_test_e2e', preview: null } });
  });
  await theirs.goto('/dashboard/billing/subscriptions');
  const lead = shown(theirs).getByTestId(`subscriptions-row-${id}-lead`);
  await atEverySize(theirs, 'HUBS-G82-keep-plan', async () => {
    await expect(lead).toHaveText('Keep it with my card');
    await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveText('Paid with another account’s card');
  });

  // «Keep it with my card»: his details first (the payer is still Olga's), then the secure payment, nothing charged today.
  await lead.click();
  const modal = theirs.getByTestId('checkout-modal');
  await expect(modal).toContainText('Keep Starter with your card');
  await expect(modal.getByTestId('checkout-another-account')).toBeVisible();
  // «Use the business's data»: its name and country; the postal code is his.
  await theirs.getByTestId('details-same').click();
  await theirs.getByTestId('details-postal-code').locator('input').fill('28002');
  await modal.getByTestId('checkout-modal-submit').click();
  await expect(modal.getByTestId('stripe-double')).toBeVisible();
  await atEverySize(theirs, 'HUBS-G82-keep-plan-pay', async () => {
    await expect(modal.getByTestId('checkout-for')).toContainText('Bar Manolo · nothing is charged today: your card pays it from');
    await expect(modal.getByTestId('stripe-double')).toBeVisible();
  });
  expect(opened).toEqual([{ hub_id: id }]);
  await payInStripe(theirs);
  await expect(toast(theirs, /^Bar Manolo keeps Starter: your card pays it from /)).toBeVisible();
  await expect(theirs).toHaveURL(new RegExp(`/dashboard/businesses/${id}/summary`));

  // Stripe tells the checkout completed (the webhook): the business moves to his card, Olga's subscription ends now.
  await withStripe([
    'from billing.services import checkout_webhooks',
    `held = {"${newSub}": subscription("${newSub}", customer="${newCustomer}", items=[item("si_e2e_new", "price_e2e_starter_month")]), "${oldSub}": subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True)}`,
    'double.answer("subscriptions.retrieve", lambda call: held[call.args[0]])',
    'double.answer("subscriptions.cancel", lambda call: {**held[call.args[0]], "status": "canceled"})',
    `assert checkout_webhooks.checkout_completed({"id": "cs_test_e2e_keep", "mode": "subscription", "payment_status": "no_payment_required", "status": "complete", "subscription": "${newSub}", "customer": "${newCustomer}", "metadata": {"kind": "plan_takeover", "hub_id": "${id}", "replaces": "${oldSub}"}}) == "completed"`,
    `assert [call.args for call in double.calls_to("subscriptions.cancel")] == [("${oldSub}",)], double.paths()`,
  ]);
  await theirs.goto('/dashboard/billing/subscriptions');
  await expect(lead).toHaveText('Change plan');
  await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveCount(0);
  await atEverySize(theirs, 'HUBS-G82-kept', async () => {
    await expect(lead).toHaveText('Change plan');
  });

  expect(theirErrors).toEqual([]);
  await context.close();
  expect(errors).toEqual([]);
});

test('HUBS-F28, in Spanish: «Mantenerlo con mi tarjeta» and the secure payment that charges nothing today', async ({ browser, page }) => {
  const errors = watchPageErrors(page);
  const owner = await account('paid-es-owner', 'Olga', 'Ruiz');
  const lucia = await account('paid-es-lucia', 'Lucía', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, lucia, 'hub_admin');
  const member = await rowOf(page, id, lucia.email);
  const stamp = Date.now();
  const [oldSub, oldCustomer] = [`sub_e2e_es_${stamp}`, `cus_e2e_es_${stamp}`];
  await djangoPrintWarm(
    [
      'from datetime import timedelta',
      'from django.contrib.auth import get_user_model',
      'from django.utils import timezone',
      'from hubs.schemas.subscriptions import SubscriptionApplyIn',
      'from hubs.services import hub_callbacks, subscription_sync',
      'now = timezone.now()',
      `subscription_sync.subscription_apply(hub_callbacks.system_ctx_for("${id}"), SubscriptionApplyIn(hub_id="${id}", plan="starter", billing_interval="month", status="active", stripe_customer_id="${oldCustomer}", stripe_subscription_id="${oldSub}", current_period_start=now - timedelta(days=10), current_period_end=now + timedelta(days=20), cancel_at_period_end=False))`,
      `get_user_model().objects.filter(email="${lucia.email}").update(language="es")`,
    ].join('\n'),
  );
  const offeredAt = Date.now();
  const offered = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(offered.status(), await offered.text()).toBe(200);
  // The offer of a paid business says until when it is paid and where she keeps it: her mail, in Spanish.
  await waitForMail(lucia.email, offeredAt, new RegExp(`${PANEL}/dashboard/billing/subscriptions(?=\\s|$)`, 'm'));
  await paintMail(browser, 'HUBS-G82-offer-mail-es', lucia.email, offeredAt, 'quiere traspasarte Bar Manolo', 'es');
  await withStripe([
    'from django.contrib.auth import get_user_model',
    'from hubs.schemas.common import ByIdIn',
    'from hubs.services import ownership',
    'from hubs.tests.conftest import ctx_for',
    `double.answer("subscriptions.update", subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True))`,
    `ownership.ownership_accept(ctx_for(get_user_model().objects.get(email="${lucia.email}")), ByIdIn(id="${((await offered.json()) as { id: string }).id}"))`,
  ]);

  const context = await browser.newContext({ baseURL: PANEL_URL, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  await freezeFrontend(context);
  const theirs = await context.newPage();
  const theirErrors = watchPageErrors(theirs);
  await signIn(theirs.request, { email: lucia.email, password: PASSWORD });
  await playStripe(theirs);
  await theirs.route('**/api/billing/plan/take-over', (route) =>
    route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e_es', client_secret: 'cs_test_e2e_es_secret', publishable_key: 'pk_test_e2e', preview: null } }),
  );
  await theirs.goto('/dashboard/billing/subscriptions');
  const lead = shown(theirs).getByTestId(`subscriptions-row-${id}-lead`);
  await atEverySize(theirs, 'HUBS-G82-keep-plan-es', async () => {
    await expect(lead).toHaveText('Mantenerlo con mi tarjeta');
    await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveText('Se paga con la tarjeta de otra cuenta');
  });
  await lead.click();
  const modal = theirs.getByTestId('checkout-modal');
  await expect(modal).toContainText('Mantén Starter con tu tarjeta');
  // «Use the business's data»: its name and country; the postal code is his.
  await theirs.getByTestId('details-same').click();
  await theirs.getByTestId('details-postal-code').locator('input').fill('28002');
  await modal.getByTestId('checkout-modal-submit').click();
  await atEverySize(theirs, 'HUBS-G82-keep-plan-pay-es', async () => {
    await expect(modal.getByTestId('checkout-for')).toContainText('Bar Manolo · hoy no se cobra nada: tu tarjeta lo paga desde el');
    await expect(modal.getByTestId('stripe-double')).toBeVisible();
  });
  await context.close();
  expect(theirErrors).toEqual([]);
  expect(errors).toEqual([]);
});
