// flow: ACCOUNTS-F10
// saas#166: inside the Android app the legal line under the sign-in sat under the system's gesture bar, as if struck
// through. The app lays the page out edge to edge and reserves only the top strip on its window (ERPlora/app,
// SystemBarInsets.kt): the strip at the bottom reaches the page as `env(safe-area-inset-bottom)`, and the page has to
// keep its content out of it, as Chrome does on the same tablet and as the Hub does under its tab bar.
//
// Chrome cannot paint Android's bar, so the run gives the page the inset (CDP `Emulation.setSafeAreaInsetsOverride`):
// the QA tablet's gesture bar (Lenovo TB361FU in landscape: a 1280 px wide window, 15 px of navigation bar,
// `adb shell dumpsys window`) and a phone's three-button bar (48 px). Whether the line lands on the bar depends on
// the window's height against the card's (on the tablet, production's card overflowed its 761 px by exactly the
// frame's bottom padding), so each frame is measured over a sweep of heights, at rest and scrolled to its end: the
// part of its last line on screen never lies under the bar, and at the end the line is whole. A probe first checks
// that the page sees the inset, so a browser that ignored the override could not pass for a fixed page.
import type { Locator, Page } from '@playwright/test';

import { expect, settled, shot, submitSignInForm, test } from './fixtures';

/** An Android window: its width and the height of the system's bar at the bottom, in CSS px. */
interface AppWindow {
  name: string;
  width: number;
  bar: number;
}

const WINDOWS: readonly AppWindow[] = [
  { name: 'tablet with gesture navigation', width: 1280, bar: 15 },
  { name: 'phone with three-button navigation', width: 390, bar: 48 },
];

/** The heights the sweep tries, every 10 px from a short landscape phone to a tall tablet. */
const HEIGHTS = Array.from({ length: 35 }, (_, step) => 560 + step * 10);

/** Gives the page `bottom` px of bottom safe area, as the Android app's WebView does. */
async function systemBar(page: Page, bottom: number): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: 0, left: 0, right: 0, bottom } });
}

/** What the page resolves `env(safe-area-inset-bottom)` to, in px (a probe element, removed after reading). */
async function insetSeen(page: Page): Promise<number> {
  return page.evaluate(() => {
    const probe = document.createElement('div');
    probe.style.setProperty('padding-bottom', 'env(safe-area-inset-bottom, 0px)');
    document.body.append(probe);
    const px = parseFloat(getComputedStyle(probe).paddingBottom);
    probe.remove();
    return px;
  });
}

/**
 * At each height of the sweep, with the page at rest and scrolled to its end, what goes wrong with `last` (the
 * frame's last line): the px of it on screen that lie under the window's system bar, and, at the end, a line not
 * whole on screen above the bar. Empty when nothing does.
 */
async function underTheBar(page: Page, last: Locator, window: AppWindow): Promise<string[]> {
  const faults: string[] = [];
  for (const height of HEIGHTS) {
    await page.setViewportSize({ width: window.width, height });
    await settled(page);
    const found = await last.evaluate(async (line, bar) => {
      type Content = HTMLElement & {
        getScrollElement(): Promise<HTMLElement>;
        scrollToTop(ms: number): Promise<void>;
        scrollToBottom(ms: number): Promise<void>;
      };
      const content = line.closest('ion-content') as Content;
      const scroller = await content.getScrollElement();
      const barTop = innerHeight - bar;
      const at = (position: string): string[] => {
        const box = line.getBoundingClientRect();
        const view = scroller.getBoundingClientRect();
        const shownTop = Math.max(box.top, view.top);
        const shownBottom = Math.min(box.bottom, view.bottom, innerHeight);
        const wrong: string[] = [];
        const under = shownBottom - Math.max(shownTop, barTop);
        if (shownBottom > shownTop && under > 0.5) wrong.push(`${position}: ${Math.round(under)} px under the bar`);
        if (position === 'end' && (box.top < view.top - 0.5 || box.bottom > Math.min(view.bottom, barTop) + 0.5))
          wrong.push(`end: not whole above the bar (${Math.round(box.top)}–${Math.round(box.bottom)} px)`);
        return wrong;
      };
      await content.scrollToTop(0);
      const rest = at('rest');
      await content.scrollToBottom(0);
      const end = at('end');
      await content.scrollToTop(0);
      return [...rest, ...end];
    }, window.bar);
    faults.push(...found.map((fault) => `${window.width}×${height}, ${fault}`));
  }
  return faults;
}

for (const window of WINDOWS) {
  test.describe(`saas#166 · ${window.name} (${window.bar} px bar)`, () => {
    test.use({ viewport: { width: window.width, height: 761 } });

    test('on the sign-in, the legal line never lies under the system bar', async ({ page }) => {
      await systemBar(page, window.bar);
      await page.goto('/launch');
      await expect(page.getByTestId('login-form')).toBeVisible();
      expect(await insetSeen(page)).toBe(window.bar);

      const foot = page.locator('.auth-card > .foot');
      await expect(foot).toContainText('By continuing you agree to our');
      expect(await underTheBar(page, foot, window)).toEqual([]);
      await page.setViewportSize({ width: window.width, height: 761 });
      await settled(page);
      await page.screenshot({ path: shot(`saas-166--sign-in--${window.width}`) });
    });

    test('on «Check your email», the legal line never lies under the system bar', async ({ page, owner }) => {
      await systemBar(page, window.bar);
      await page.goto('/launch');
      await submitSignInForm(page, owner);
      await expect(page).toHaveURL(/\/verify-email(\?|$)/);
      expect(await insetSeen(page)).toBe(window.bar);

      // The sign-in's page stays in the DOM under it (Ionic's stack): the foot of the frame holding the code.
      const foot = page.locator('.auth-card', { has: page.getByTestId('verify-email-submit') }).locator(':scope > .foot');
      await expect(foot).toContainText('By continuing you agree to our');
      expect(await underTheBar(page, foot, window)).toEqual([]);
    });

    test('signed in, the launcher’s «Sign out» row never lies under the system bar', async ({ signedInPage: page }) => {
      await systemBar(page, window.bar);
      await page.goto('/launch');
      const account = page.getByTestId('shell-account');
      await expect(account).toContainText('Signed in as');
      expect(await insetSeen(page)).toBe(window.bar);

      expect(await underTheBar(page, account, window)).toEqual([]);
    });
  });
}
