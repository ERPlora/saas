// The flows of «the settings of a business, its web address, deleting and recovering it, its status and usage, and
// the staff on it in the admin» (hubs/WORKBOOK.md) on their screens, at the three sizes
// (390×844, 834×1112, 1440×900). Each test names its flow of hubs/WORKBOOK.md in its title. F20 (the clock of a
// suspended business) and F22 (the nightly usage) have no screen: their tests are the server's
// (hubs/tests/test_suspended_lifecycle.py, test_collect_hub_usage.py).
//
// Two parts, as panel/hubs-flows.spec.ts:
// - against the panel's own Django (project.ts): its calls to the Hub go nowhere, so every write here waits for the
//   Hub (owed, retried by reconcile_hub_states) and the page says what the SaaS keeps;
// - «the real Hub» (`E2E_REAL_HUB=1`, README «El Hub real de la e2e»): the new name and address reach the Hub, «Open»
//   goes in by the new one and the old one no longer opens. With the variable, the two tests that read what waits for
//   the Hub (HUBS-F15, HUBS-F23) are skipped, and say so. So the spec runs twice: once without, once with.
// Each test has its own account (`e2e-hubs2-…@example.com`) and its own business, created through the API as the
// panel creates it.
import { type Page } from '@playwright/test';

import {
  apiPost,
  captureAtEverySize,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  internalSecret,
  QUIET_MS,
  realHubPrint,
  removeAccountsWarm,
  reportBusinessReady,
  settled,
  shot,
  signIn,
  signInAs,
  test,
  watchLiveStreams,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const atEverySize = captureAtEverySize('APP-HUBS-2');

const PREFIX = 'e2e-hubs2-';
const PASSWORD = 'Masa-madre-y-centeno-26';

/** The page Ionic shows (it keeps the pages it left in the DOM, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** What waits for the Hub: with the real Hub it takes the write at once, so there is nothing to read. */
const NO_HUB = 'reads what waits for the Hub; the real Hub takes it at once';

/** A fresh account of this spec, its address proven, signed in on `page`, with a business called `name`. */
async function signedUpWith(page: Page, who: string, name: string): Promise<{ email: string; id: string; slug: string }> {
  const email = `${PREFIX}${who}-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { language: 'en' });
  await signIn(page.request, { email, password: PASSWORD });
  const created = await apiPost(page.request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), 'POST /api/hubs/businesses').toBe(201);
  return { email, ...((await created.json()) as { id: string; slug: string }) };
}

/** `signedUpWith`, its business ready as the Hub's callback leaves it (here no Hub answers). */
async function ownerOf(page: Page, who: string, name: string): Promise<{ email: string; id: string; slug: string }> {
  const business = await signedUpWith(page, who, name);
  // Ready: the Hub's callback, sent here as the Hub sends it (no Hub answers here).
  await reportBusinessReady(page.request, business.id);
  return business;
}

/** Type `value` into the `ion-input` with that test id (its native input). */
async function typeInto(page: Page, testid: string, value: string): Promise<void> {
  const input = page.getByTestId(testid).locator('input');
  await input.fill(value);
}

/** What the SaaS keeps of business `id` and the panel shows, through its API (`hubs.business.get`). */
async function kept(page: Page, id: string): Promise<{ name: string; slug: string; status: string }> {
  const detail = await page.request.get(`/api/hubs/businesses/detail?id=${id}`);
  expect(detail.status(), await detail.text()).toBe(200);
  return detail.json();
}

// Django's boots on no test's clock (saas#354): the warm Django and the secret of the Hub's callback, once here.
test.beforeAll(async () => {
  await Promise.all([removeAccountsWarm(PREFIX), internalSecret()]);
});
test.afterAll(() => removeAccountsWarm(PREFIX));

test('HUBS-F15: the owner renames the business in «General»; an empty name is not saved', async ({ page }) => {
  test.skip(!!process.env.E2E_REAL_HUB, NO_HUB);
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'rename', 'Bar Manolo');
  await page.goto(`/dashboard/businesses/${id}/settings`);
  const general = shown(page).getByTestId('settings-general');
  await atEverySize(page, 'HUBS-G73', async () => {
    await expect(general.getByTestId('settings-name')).toBeVisible();
  });
  await typeInto(page, 'settings-name', '   ');
  await general.getByTestId('settings-save').click();
  await expect(general.getByTestId('settings-name')).toHaveClass(/ion-invalid/);
  await typeInto(page, 'settings-name', 'Casa Manolo');
  await general.getByTestId('settings-save').click();
  await expect(page.getByText('Changes saved')).toBeVisible();
  // What waits for the Hub only Django knows: the warm one reads it.
  expect(await djangoPrintWarm(`from hubs.models import Hub;h=Hub.objects.get(pk="${id}");print(h.name, h.pending_hub_call)`)).toBe(
    'Casa Manolo put',
  );
  expect(errors).toEqual([]);
});

test('HUBS-F16: an address the server refuses says why on its field, and on top to look at it until it is corrected, in the language of the account', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'address-refused', 'Bar Refused');
  for (const { language, notice, reason } of [
    { language: 'en', notice: 'Check the highlighted details.', reason: 'Use only lowercase letters, digits and hyphens' },
    { language: 'es', notice: 'Revisa los datos marcados.', reason: 'Usa solo minúsculas' },
  ]) {
    expect((await apiPost(page.request, '/api/accounts/preferences', { language })).status()).toBe(200);
    await page.goto(`/dashboard/businesses/${id}/settings`);
    await shown(page).getByTestId('settings-general').getByTestId('settings-change-address').click();
    const dialog = page.getByTestId('address-dialog');
    await typeInto(page, 'address-dialog-slug', '-casa');
    await dialog.getByTestId('address-dialog-submit').click();
    await expect(dialog.getByTestId('address-dialog-error')).toHaveText(notice);
    await expect(page.getByTestId('address-dialog-slug')).toContainText(reason);
    for (const { width, height } of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }, { width: 375, height: 667 }]) {
      await page.setViewportSize({ width, height });
      await settled(page);
      await expect(dialog.getByTestId('address-dialog-error')).toBeInViewport({ ratio: 1 });
      await page.screenshot({ path: shot(`refused-address-${language}-${width}x${height}`) });
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    // Corrected, the notice has done its job; refused again, it comes back.
    await typeInto(page, 'address-dialog-slug', 'casa');
    await expect(dialog.getByTestId('address-dialog-error')).toBeHidden();
    await typeInto(page, 'address-dialog-slug', '-casa');
    await dialog.getByTestId('address-dialog-submit').click();
    await expect(dialog.getByTestId('address-dialog-error')).toHaveText(notice);
  }
  expect(errors).toEqual([]);
});

test('HUBS-F16: the owner moves the business to another web address; the old one stays its own', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id, slug } = await ownerOf(page, 'address', 'Bar Manolo');
  const wanted = `${slug}-nuevo`;
  await page.goto(`/dashboard/businesses/${id}/settings`);
  const general = shown(page).getByTestId('settings-general');
  await general.getByTestId('settings-change-address').click();
  const dialog = page.getByTestId('address-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('address-dialog-submit')).toHaveAttribute('aria-disabled', 'true');
  await typeInto(page, 'address-dialog-slug', wanted);
  await expect(dialog.getByTestId('address-dialog-host')).toContainText(`${wanted}.`);
  await atEverySize(page, 'HUBS-G74', async () => {
    // The whole sheet fits: its action is on screen at every size, not cut by the bottom edge.
    await expect(dialog.getByTestId('address-dialog-submit')).toBeInViewport({ ratio: 1 });
    await expect(dialog.getByTestId('address-dialog-submit')).not.toHaveAttribute('aria-disabled', 'true');
  });
  // A reserved address is refused in the dialog, which stays.
  await typeInto(page, 'address-dialog-slug', 'hubs');
  await dialog.getByTestId('address-dialog-submit').click();
  await expect(dialog.getByTestId('address-dialog-error')).toContainText('This address is reserved. Choose another one.');
  // No field says it, so it stays until the next try.
  await typeInto(page, 'address-dialog-slug', wanted);
  await expect(dialog.getByTestId('address-dialog-error')).toContainText('This address is reserved. Choose another one.');
  await dialog.getByTestId('address-dialog-submit').click();
  await expect(page.getByText(`The business now opens at ${wanted}.`)).toBeVisible();
  await expect(general.getByTestId('copy-value')).toContainText(`${wanted}.`);
  // The old address kept as the business's own only Django knows: the warm one reads it.
  expect(await djangoPrintWarm(`from hubs.models import Hub;h=Hub.objects.get(pk="${id}");print(h.slug, h.previous_slug)`)).toBe(
    `${wanted} ${slug}`,
  );
  expect(errors).toEqual([]);
});

test('HUBS-F18 + HUBS-F19: the owner deletes the business typing its name, then recovers it', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'delete', 'Bar Manolo');
  await page.goto(`/dashboard/businesses/${id}/settings`);
  const danger = shown(page).getByTestId('danger-zone');
  await danger.getByTestId('danger-delete').click();
  const dialog = page.getByTestId('delete-dialog');
  await expect(dialog.getByTestId('delete-dialog-submit')).toHaveAttribute('aria-disabled', 'true');
  await page.getByTestId('delete-dialog-input').locator('input').fill('Bar Manolo');
  await atEverySize(page, 'HUBS-G88', async () => {
    await expect(dialog.getByTestId('delete-dialog-submit')).not.toHaveAttribute('aria-disabled', 'true');
  });
  await dialog.getByTestId('delete-dialog-submit').click();
  await expect(page.getByText(/^Business deleted: Bar Manolo\. You can recover it until/)).toBeVisible();
  // Deleted, the page says until when it can be recovered, with «Recover business».
  const deleted = shown(page).getByTestId('business-deleted');
  await atEverySize(page, 'HUBS-G22', async () => {
    await expect(deleted.getByTestId('business-restore')).toBeVisible();
  });
  await expect(deleted).toContainText('It will be erased for good on');
  await deleted.getByTestId('business-restore').click();
  await expect(shown(page).getByTestId('business-deleted')).toHaveCount(0);
  expect((await kept(page, id)).status).toBe('active');
  expect(errors).toEqual([]);
});

test('HUBS-F21: the Summary says the business’s status, its plan and the usage the Hub measured last night', async ({ page }) => {
  const errors = watchPageErrors(page);
  const streams = watchLiveStreams(page);
  const { id } = await ownerOf(page, 'usage', 'Bar Manolo');
  // What the Hub measured last night, as the nightly pass keeps it (no screen writes it).
  await djangoPrintWarm(
    [
      'from datetime import UTC, datetime, timedelta',
      'from hubs.models import HubUsageDaily',
      `HubUsageDaily.objects.create(hub_id="${id}", day=datetime.now(UTC).date() - timedelta(days=1),`,
      '    s3_bytes=900 * 1024 * 1024, db_bytes=0, active_users_1d=2, active_users_30d=3)',
    ].join('\n'),
  );
  await page.goto(`/dashboard/businesses/${id}/summary`);
  const usage = shown(page).getByTestId('summary-usage');
  await expect(shown(page).getByTestId('representation')).toBeVisible();
  // One stream with all the page shows: the business and its authorisation to file invoices (a Spanish business).
  await page.waitForTimeout(QUIET_MS);
  expect({ opened: streams.opened, failed: [...streams.failed] }).toEqual({
    opened: [
      expect.arrayContaining([expect.stringMatching(/^hubs\.business\.get /), expect.stringMatching(/^fiscal\.representation\.status /)]),
    ],
    failed: [],
  });
  await atEverySize(page, 'HUBS-G90', async () => {
    await expect(usage).toBeVisible();
  });
  await expect(usage).toContainText('88%');
  await expect(usage.getByTestId('summary-usage-day')).toContainText("Yesterday's data: updated every night.");
  await expect(shown(page).getByTestId('summary-plan')).toContainText('Free');
  expect(errors).toEqual([]);
});

test('HUBS-F23: an action of the staff on a business is in its history in the admin', async ({ page }) => {
  test.skip(!!process.env.E2E_REAL_HUB, NO_HUB);
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'admin', 'Bar Manolo');
  const staff = `${PREFIX}staff-${Date.now()}@example.com`;
  await createAccountWarm(staff, PASSWORD, { role: 'superuser' });
  // The owner's session is open on this page: the staff signs in on a clean one.
  await signInAs(page, { email: staff, password: PASSWORD });
  await page.goto('/admin/hubs/hub/');
  await page.locator(`input[name="_selected_action"][value="${id}"]`).check();
  await page.locator('select[name="action"]').selectOption('retry_owed');
  await page.locator('button[name="index"]').click();
  await expect(page.locator('.messagelist')).toContainText('still owed');
  await page.goto(`/admin/hubs/hub/${id}/history/`);
  await atEverySize(page, 'HUBS-G97', async () => {
    await expect(page.locator('#change-history')).toContainText('Ran «Retry what the Hub still owes»');
  });
  expect(errors).toEqual([]);
});

// ── The real Hub ──────────────────────────────────────────────────────────────────────────────────────────────
// A Hub runserver on HUB_DOUBLE_PORT, its `SAAS_URL` this stack's panel, the same INTERNAL_SHARED_SECRET, and this
// run's `HUB_CALLBACK_TEMPLATE` pointing at it (README «El Hub real de la e2e»). `HUB_DIR` is its checkout and
// `HUB_DB_NAME` its database, read here with its `manage.py`.
test.describe('against the real Hub', () => {
  test.skip(!process.env.E2E_REAL_HUB, 'needs a real Hub on the stack’s Hub port (README «El Hub real de la e2e»)');

  /** What the Hub's registry has for the business `id`: `<address> <name>`, or `missing`. */
  const inTheHub = (id: string) =>
    realHubPrint(`from base.models import Hub;h=Hub.objects.filter(pk="${id}").first();print(f"{h.slug} {h.name}" if h else "missing")`);

  test('HUBS-F15 + HUBS-F16: renamed and moved, the business opens at its new address and no longer at the old one', async ({ page }) => {
    const errors = watchPageErrors(page);
    const { id, slug } = await signedUpWith(page, 'real', 'Taberna Hub Real E2E');
    await expect.poll(async () => (await kept(page, id)).status, { timeout: 30_000 }).toBe('active');
    expect(await inTheHub(id)).toBe(`${slug} Taberna Hub Real E2E`);
    await page.goto(`/dashboard/businesses/${id}/settings`);
    const general = shown(page).getByTestId('settings-general');
    await typeInto(page, 'settings-name', 'Bodegon Hub Real E2E');
    await general.getByTestId('settings-save').click();
    await expect(page.getByText('Changes saved')).toBeVisible();
    const wanted = `${slug}-nueva`;
    await general.getByTestId('settings-change-address').click();
    const dialog = page.getByTestId('address-dialog');
    await typeInto(page, 'address-dialog-slug', wanted);
    await dialog.getByTestId('address-dialog-submit').click();
    await expect(page.getByText(`The business now opens at ${wanted}.`)).toBeVisible();
    await expect.poll(() => inTheHub(id), { timeout: 30_000 }).toBe(`${wanted} Bodegon Hub Real E2E`);
    await page.goto('/dashboard/businesses');
    await shown(page)
      .getByTestId('businesses-row')
      .filter({ hasText: 'Bodegon Hub Real E2E' })
      .getByRole('button', { name: 'Open Bodegon Hub Real E2E' })
      .click();
    await page.waitForURL(new RegExp(`^http://${wanted}\\.localhost:${HUB_DOUBLE_PORT}/(?!auth)`), { timeout: 30_000 });
    const old = await page.request.get(`http://${slug}.localhost:${HUB_DOUBLE_PORT}/`, { maxRedirects: 0 });
    expect(old.status(), 'the old address no longer opens the business').toBe(404);
    expect(errors).toEqual([]);
  });
});
