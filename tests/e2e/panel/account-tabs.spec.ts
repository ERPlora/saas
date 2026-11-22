// The Account tabs one after another (`/dashboard/account/:tab`; the rest of Account is account.spec.ts): each at the
// three viewports, light and dark, without scrolling sideways, leaving a screenshot in `$SHOTS_DIR` (or
// `.artifacts/panel/account/`) to compare with the mockup.
//
// In a file of its own because a trace only turns off for a whole file. Closing a context first stops its trace, which
// reopens the files it wrote one by one, and with a loaded machine each open() waits: over these 12 pages that held the
// close for 65-90 s (under 1 s without a trace) and used up the test's time with nothing wrong on screen (saas#259). A
// screen failure still says which tab, width and theme, and leaves its screenshot; page errors are only listed.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { type Locator, type Page } from '@playwright/test';

import { panelAccount } from './accounts';
import { seedPanel } from './businesses';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { PANEL_URL } from './project';
import { shot, sidewaysScroll, VIEWPORTS } from './screen';
import { signIn } from './session';

const SHOTS_DIR = process.env.SHOTS_DIR ?? join(shot('account-dir'), '..', 'account');
mkdirSync(SHOTS_DIR, { recursive: true });

test.use({ trace: 'off' });

/** The difference, in px, between a notice's gap to the left and to the right of the room it sits in. */
const offCentre = (notice: Locator) =>
  notice.evaluate((el) => {
    const own = el.getBoundingClientRect();
    const room = (el.parentElement ?? el).getBoundingClientRect();
    return Math.abs(own.left - room.left - (room.right - own.right));
  });

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('each tab at the three viewports, light and dark, without scrolling sideways', async ({ browser }) => {
  const signing = await browser.newContext({ baseURL: PANEL_URL });
  await signIn(signing.request, panelAccount('several'));
  const state = await signing.storageState();
  await signing.close();
  // `centred`: what `ready` finds is a notice that sits in the middle of its room, not at its start.
  const TABS: Array<{ tab: string; ready: (page: Page) => Locator; centred?: boolean }> = [
    { tab: 'profile', ready: (p) => p.getByTestId('profile-card') },
    { tab: 'security', ready: (p) => p.getByTestId('sign-in-card') },
    { tab: 'preferences', ready: (p) => p.getByTestId('preferences-appearance') },
    { tab: 'api-keys', ready: (p) => p.getByTestId('api-keys-empty'), centred: true },
  ];
  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ baseURL: PANEL_URL, storageState: state, colorScheme: theme, locale: 'es-ES' });
    try {
      const page = await context.newPage();
      const errors = watchPageErrors(page);
      for (const { width, height } of VIEWPORTS) {
        await page.setViewportSize({ width, height });
        for (const { tab, ready, centred } of TABS) {
          await page.goto(`/dashboard/account/${tab}`);
          await expect(ready(page), `account-${tab}-${width}-${theme}`).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          expect(await sidewaysScroll(page), `account-${tab}-${width}-${theme}`).toEqual([]);
          const offBy = centred ? await offCentre(ready(page)) : 0;
          expect.soft(offBy, `account-${tab}-${width}-${theme} centred`).toBeLessThanOrEqual(1);
          await page.screenshot({ path: join(SHOTS_DIR, `account-${tab}-${width}-${theme}.png`), fullPage: true });
        }
      }
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  }
});
