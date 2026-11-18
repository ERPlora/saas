// «Transparency effects» of Account › Preferences (ACCOUNTS-F22) in Chrome, at the three sizes, against the rows of
// billing_seed.py, whose unpaid businesses give the bell's panel something to show. On from the start, the panel and a
// brief notice blur what is behind them; turned off, `<html>` carries `ep-opaque` and both are opaque, already when the
// shell mounts after a reload; turned on again, the glass is back. A last test leaves the shots of the Preferences
// screen and of the bell's panel, glass and opaque, light and dark, at 390 and 1440 px, in SHOTS_DIR when it is
// given (else with the panel's other shots).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Locator, Page } from '@playwright/test';

import { panelAccount, qaAccount } from './accounts';
import { djangoPrintWarm } from './django';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { openNotices } from './notices';
import { watchPageErrors } from './page-events';
import { settled, shot, toast, VIEWPORTS } from './screen';

const BILLING = qaAccount('BILLING', panelAccount('billing'));
const PREFERENCES = '/dashboard/account/preferences';
const BUSINESSES = '/dashboard/businesses';

seededAndSignedInWarm('billing_seed.py', BILLING);

const html = (page: Page) => page.locator('html');
const transparency = (page: Page) => page.getByTestId('preferences-transparency');
const backdropOf = (locator: Locator) => locator.evaluate((element) => getComputedStyle(element).backdropFilter);

/** The blur behind the bell's panel, open and still: its surface is the `content` part of its modal, in the shadow
 *  root. */
async function panelBackdrop(page: Page): Promise<string> {
  const panel = await openNotices(page);
  await settled(page);
  return panel.evaluate((modal) => {
    const surface = modal.shadowRoot?.querySelector('[part~="content"]');
    if (!surface) throw new Error('the bell’s panel has no content part');
    return getComputedStyle(surface).backdropFilter;
  });
}

async function closeNotices(page: Page): Promise<void> {
  await page.getByTestId('action-panel-close').click();
  await expect(page.getByTestId('action-panel')).toBeHidden();
}

/** Records, on every load of `page`, whether `<html>` was already opaque when the shell's `ion-app` entered it. */
async function watchOpaqueAtMount(page: Page): Promise<void> {
  await page.addInitScript(() => {
    new MutationObserver((_, observer) => {
      if (!document.querySelector('ion-app')) return;
      document.documentElement.dataset.opaqueAtMount = String(document.documentElement.classList.contains('ep-opaque'));
      observer.disconnect();
    }).observe(document, { childList: true, subtree: true });
  });
}

/** Clicks the switch and waits for its save: the switch is pressable again and «Preferences saved» is on screen, done
 *  entering (a toast has no blur while it comes in or goes). */
async function toggleTransparency(page: Page): Promise<Locator> {
  await transparency(page).click();
  await expect(transparency(page)).toHaveJSProperty('disabled', false);
  const saved = toast(page, 'Preferences saved');
  await expect(saved).toBeVisible();
  await settled(page);
  return saved;
}

for (const size of VIEWPORTS) {
  test(`ACCOUNTS-F22: «Transparency effects» turns the glass off and on, kept after a reload, at ${size.width} px`, async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    await watchOpaqueAtMount(page);
    await page.setViewportSize(size);
    await page.goto(PREFERENCES);
    await expect(transparency(page)).toHaveJSProperty('checked', true);
    await expect(html(page)).not.toHaveClass(/ep-opaque/);
    expect(await panelBackdrop(page)).toContain('blur(');
    await closeNotices(page);

    const off = await toggleTransparency(page);
    await expect(html(page)).toHaveClass(/ep-opaque/);
    expect(await backdropOf(off)).toBe('none');
    expect(await panelBackdrop(page)).toBe('none');
    await closeNotices(page);

    await page.reload();
    await expect(transparency(page)).toHaveJSProperty('checked', false);
    await expect(html(page)).toHaveAttribute('data-opaque-at-mount', 'true');
    expect(await panelBackdrop(page)).toBe('none');
    await closeNotices(page);

    const on = await toggleTransparency(page);
    await expect(html(page)).not.toHaveClass(/ep-opaque/);
    expect(await backdropOf(on)).toContain('blur(');
    await page.reload();
    await expect(transparency(page)).toHaveJSProperty('checked', true);
    await expect(html(page)).toHaveAttribute('data-opaque-at-mount', 'false');
    expect(errors).toEqual([]);
  });
}

/** The billing account's transparency effects, written as Account › Preferences keeps them. */
async function keepTransparency(on: boolean): Promise<void> {
  await djangoPrintWarm(
    [
      'from django.contrib.auth import get_user_model',
      'from accounts.models import UserPreferences',
      `user = get_user_model().objects.get(email="${BILLING.email}")`,
      `UserPreferences.objects.update_or_create(user=user, defaults={"transparency": ${on ? 'True' : 'False'}})`,
    ].join('\n'),
  );
}

/** The page as it is once still, as `name`. */
async function capture(page: Page, name: string): Promise<void> {
  const dir = process.env.SHOTS_DIR;
  if (dir) mkdirSync(dir, { recursive: true });
  await settled(page);
  await page.screenshot({ path: dir ? join(dir, `${name}.png`) : shot(name) });
}

test('the Preferences screen and the bell’s panel, glass and opaque, light and dark, at 390 and 1440 px', async ({ page }) => {
  for (const state of ['glass', 'opaque'] as const) {
    await keepTransparency(state === 'glass');
    for (const theme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: theme });
      for (const size of [VIEWPORTS[0], VIEWPORTS[2]]) {
        await page.setViewportSize(size);
        await page.goto(PREFERENCES);
        await expect(transparency(page)).toHaveJSProperty('checked', state === 'glass');
        await capture(page, `preferences-${state}-${theme}-${size.width}`);
        await page.goto(BUSINESSES);
        await expect(page.getByTestId('businesses-row').first()).toBeVisible();
        expect(await panelBackdrop(page)).toBe(state === 'glass' ? 'blur(20px) saturate(1.8)' : 'none');
        await capture(page, `notices-${state}-${theme}-${size.width}`);
      }
    }
  }
});
