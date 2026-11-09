// A business created during a real platform freeze: the Hub's signed poll says maintenance, the
// card and the row explain it, and «Check now» clears it after the lift, without a reload.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, panelAccount, seedPanel, sidewaysScroll, signIn, startHubDouble, test, watchPageErrors } from './fixtures';
import { uiClipSweep } from '../ui-evidence';

const EVIDENCE = join(process.env.HOME ?? '', '.erplora', 'fleet-next', 'logs', '387', 'ui');
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
    hub.setMaintenance({ frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' });
    await signIn(page.request, panelAccount('creator'));
    await page.goto('/dashboard/businesses');
    await page.getByTestId('create-name').locator('input').fill('Pastelería Dulce E2E');
    await page.getByTestId('create-submit').click();

    await expect(page.getByTestId('preparing-maintenance')).toContainText('Provisioning is paused for maintenance');
    const row = page.getByTestId('businesses-row').filter({ hasText: 'Pastelería Dulce E2E' });
    await expect(row).toContainText('Paused for maintenance');
    mkdirSync(EVIDENCE, { recursive: true });
    for (const size of VIEWPORTS) {
      await page.setViewportSize(size);
      await expect(page.getByTestId('preparing-maintenance')).toBeVisible();
      expect(await sidewaysScroll(page), `maintenance at ${size.width}`).toEqual([]);
      await page.screenshot({ path: join(EVIDENCE, `business-maintenance-en-${size.width}x${size.height}.png`), fullPage: true });
    }
    await uiClipSweep(page, 'http://localhost:13872/dashboard/businesses');

    hub.setMaintenance(null);
    await page.getByTestId('preparing-check').click();
    await expect(page.getByTestId('preparing-maintenance')).toHaveCount(0);
    await expect(page.getByTestId('preparing-check-error')).toHaveCount(0);
    await expect(row).toContainText('Preparing');
    expect(errors).toEqual([]);
  } finally {
    await hub.close();
  }
});
