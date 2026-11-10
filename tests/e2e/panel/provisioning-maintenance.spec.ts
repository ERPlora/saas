// A business created during a real platform freeze: the Hub's signed poll says maintenance, the
// card and the row explain it, and «Check now» clears it after the lift, without a reload. While the
// pause lasts neither the Entry nor «Create business» promises «a few seconds» (saas#398): the
// sentence comes back with the lift.
import {
  expect,
  panelAccount,
  seedPanel,
  shot,
  sidewaysScroll,
  signIn,
  startHubDouble,
  test,
  watchPageErrors,
} from './fixtures';

/** The sentence over a preparation (`hubs.launch.preparing.lead`): never shown during the pause. */
const FEW_SECONDS = 'It usually takes a few seconds.';
const MAINTENANCE = { frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' };

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('create during maintenance → the pause is visible → Check now recovers', async ({ page }) => {
  const hub = await startHubDouble();
  const errors = watchPageErrors(page);
  try {
    hub.setMaintenance(MAINTENANCE);
    await signIn(page.request, panelAccount('creator'));
    await page.goto('/dashboard/businesses');
    await page.getByTestId('create-name').locator('input').fill('Pastelería Dulce E2E');
    await page.getByTestId('create-submit').click();

    await expect(page.getByTestId('preparing-maintenance')).toContainText('Provisioning is paused for maintenance');
    const dialog = page.getByTestId('create-modal');
    await expect(dialog).not.toContainText(FEW_SECONDS);
    const row = page.getByTestId('businesses-row').filter({ hasText: 'Pastelería Dulce E2E' });
    await expect(row).toContainText('Paused for maintenance');
    for (const size of VIEWPORTS) {
      await page.setViewportSize(size);
      await expect(page.getByTestId('preparing-maintenance')).toBeVisible();
      expect(await sidewaysScroll(page), `maintenance at ${size.width}`).toEqual([]);
      await page.screenshot({ path: shot(`business-maintenance-en-${size.width}x${size.height}`), fullPage: true });
    }

    hub.setMaintenance(null);
    await page.getByTestId('preparing-check').click();
    await expect(page.getByTestId('preparing-maintenance')).toHaveCount(0);
    await expect(page.getByTestId('preparing-check-error')).toHaveCount(0);
    await expect(row).toContainText('Preparing');
    await expect(dialog).toContainText(FEW_SECONDS);
    expect(errors).toEqual([]);
  } finally {
    await hub.close();
  }
});

test('the Entry during maintenance → only the pause, no «a few seconds» → the sentence is back after the lift', async ({ page }) => {
  const hub = await startHubDouble();
  const errors = watchPageErrors(page);
  try {
    hub.setMaintenance(MAINTENANCE);
    await signIn(page.request, panelAccount('first'));
    await page.goto('/launch');
    await page.getByTestId('create-name').locator('input').fill('Panadería Pausa E2E');
    await page.getByTestId('create-submit').click();

    await expect(page.getByRole('heading', { name: 'Preparing Panadería Pausa E2E' })).toBeVisible();
    await expect(page.getByTestId('preparing-maintenance')).toContainText('Provisioning is paused for maintenance');
    await expect(page.locator('.shell-lead')).toHaveCount(0);
    for (const size of VIEWPORTS) {
      await page.setViewportSize(size);
      await expect(page.getByTestId('preparing-maintenance')).toBeVisible();
      expect(await sidewaysScroll(page), `launch maintenance at ${size.width}`).toEqual([]);
      await page.screenshot({ path: shot(`launch-maintenance-en-${size.width}x${size.height}`), fullPage: true });
    }

    hub.setMaintenance(null);
    await page.getByTestId('preparing-check').click();
    await expect(page.getByTestId('preparing-maintenance')).toHaveCount(0);
    await expect(page.locator('.shell-lead')).toHaveText(FEW_SECONDS);
    expect(errors).toEqual([]);
  } finally {
    await hub.close();
  }
});
