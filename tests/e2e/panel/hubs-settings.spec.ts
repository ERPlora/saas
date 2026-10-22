// The flows of «the settings of a business, its web address, deleting and recovering it, its status and usage, and
// the staff on it in the admin» (hubs/WORKBOOK.md, MIGRATION-TASK APP-HUBS-2) on their screens, at the three sizes of
// the migration (390×844, 834×1112, 1440×900). Each test names its flow by its registry key; in hubs/WORKBOOK.md:
// G73=F15, G74=F16, G88=F18, G22=F19, G90=F21, G97=F23. F20 (the clock of a suspended business) and F22 (the nightly
// usage) have no screen: their tests are the server's (hubs/tests/test_suspended_lifecycle.py, test_collect_hub_usage.py).
//
// Against the panel's own Django (project.ts): its calls to the Hub go nowhere, so every write here waits for the Hub
// (owed, retried by reconcile_hub_states) and the page says what the SaaS keeps. Each test has its own account
// (`e2e-hubs2-…@example.com`) and its own business, created through the API as the panel creates it.
import { type Page } from '@playwright/test';

import { apiPost, djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const PREFIX = 'e2e-hubs2-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

/** The page Ionic shows (it keeps the pages it left in the DOM, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** A fresh account of this spec, its address proven, signed in on `page`, with a ready business called `name`. */
async function ownerOf(page: Page, who: string, name: string): Promise<{ email: string; id: string; slug: string }> {
  const email = `${PREFIX}${who}-${Date.now()}@example.com`;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="en")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  await signIn(page.request, { email, password: PASSWORD });
  const created = await apiPost(page.request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), 'POST /api/hubs/businesses').toBe(201);
  const business = (await created.json()) as { id: string; slug: string };
  // Ready, as the Hub's callback leaves it (here no Hub answers).
  djangoPrint(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub',
      `Hub.objects.filter(pk="${business.id}").update(status="active", ready_at=timezone.now())`,
    ].join('\n'),
  );
  return { email, id: business.id, slug: business.slug };
}

/** `ready` at each size: no sideways scroll and a capture `APP-HUBS-2-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-HUBS-2-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** Type `value` into the `ion-input` with that test id (its native input). */
async function typeInto(page: Page, testid: string, value: string): Promise<void> {
  const input = page.getByTestId(testid).locator('input');
  await input.fill(value);
}

function removeOwnRows(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import Hub',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}").delete()`,
    ].join('\n'),
  );
}

test.beforeAll(() => removeOwnRows());
test.afterAll(() => removeOwnRows());

test('HUBS-G73: the owner renames the business in «General»; an empty name is not saved', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'rename', 'Bar Manolo');
  await page.goto(`/businesses/${id}/settings`);
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
  expect(djangoPrint(`from hubs.models import Hub;h=Hub.objects.get(pk="${id}");print(h.name, h.pending_hub_call)`)).toBe(
    'Casa Manolo put',
  );
  expect(errors).toEqual([]);
});

test('HUBS-G74: the owner moves the business to another web address; the old one stays its own', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id, slug } = await ownerOf(page, 'address', 'Bar Manolo');
  const wanted = `${slug}-nuevo`;
  await page.goto(`/businesses/${id}/settings`);
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
  await typeInto(page, 'address-dialog-slug', wanted);
  await dialog.getByTestId('address-dialog-submit').click();
  await expect(page.getByText(`The business now opens at ${wanted}.`)).toBeVisible();
  await expect(general.getByTestId('copy-value')).toContainText(`${wanted}.`);
  expect(djangoPrint(`from hubs.models import Hub;h=Hub.objects.get(pk="${id}");print(h.slug, h.previous_slug)`)).toBe(
    `${wanted} ${slug}`,
  );
  expect(errors).toEqual([]);
});

test('HUBS-G88 + HUBS-G22: the owner deletes the business typing its name, then recovers it', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'delete', 'Bar Manolo');
  await page.goto(`/businesses/${id}/settings`);
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
  expect(djangoPrint(`from hubs.models import Hub;print(Hub.objects.get(pk="${id}").status)`)).toBe('active');
  expect(errors).toEqual([]);
});

test('HUBS-G90: the Summary says the business’s status, its plan and the usage the Hub measured last night', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'usage', 'Bar Manolo');
  djangoPrint(
    [
      'from datetime import UTC, datetime, timedelta',
      'from hubs.models import HubUsageDaily',
      `HubUsageDaily.objects.create(hub_id="${id}", day=datetime.now(UTC).date() - timedelta(days=1),`,
      '    s3_bytes=900 * 1024 * 1024, db_bytes=0, active_users_1d=2, active_users_30d=3)',
    ].join('\n'),
  );
  await page.goto(`/businesses/${id}/summary`);
  const usage = shown(page).getByTestId('summary-usage');
  await atEverySize(page, 'HUBS-G90', async () => {
    await expect(usage).toBeVisible();
  });
  await expect(usage).toContainText('88%');
  await expect(usage.getByTestId('summary-usage-day')).toContainText("Yesterday's data: updated every night.");
  await expect(shown(page).getByTestId('summary-plan')).toContainText('Free');
  expect(errors).toEqual([]);
});

test('HUBS-G97: an action of the staff on a business is in its history in the admin', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { id } = await ownerOf(page, 'admin', 'Bar Manolo');
  const staff = `${PREFIX}staff-${Date.now()}@example.com`;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_superuser(email="${staff}", password="${PASSWORD}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  // The owner's session is open on this page: the staff signs in on a clean one.
  await page.context().clearCookies();
  await signIn(page.request, { email: staff, password: PASSWORD });
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
