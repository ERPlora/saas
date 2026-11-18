// The panel's notices come from the shell's one stack of toasts: at most three on screen, the newest in front and in
// at once, the oldest that leaves by itself making room for it (never an error); an error keeps its «Close»; the stack
// sits above the section tabbar of the screen, at the three sizes. Four saves of «Notices from my businesses», held back and let go one after another, make the four
// notices: the first refused (an error, which lasts longest), the other three saved.
import type { Page, Route } from '@playwright/test';

import { expect, test } from './fixtures';
import { settled, shot, toasts, VIEWPORTS } from './screen';

const SAVED = 'Preferences saved';
const OFFLINE = 'We could not reach ERPlora. Check your connection and try again.';

/** Holds every save of the preferences until the spec lets it go; loading them still goes through. */
async function holdSaves(page: Page): Promise<Route[]> {
  const held: Route[] = [];
  await page.route(/\/api\/accounts\/preferences$/, async (route) => {
    if (route.request().method() === 'GET') await route.continue();
    else held.push(route);
  });
  return held;
}

/** Every toast's box ends inside the window and above the tabbar's top. */
async function expectAboveTabbar(page: Page, width: number): Promise<void> {
  const tabbar = await page.locator('ion-footer.section-tabbar').filter({ has: page.getByTestId('tab-preferences') }).boundingBox();
  expect(tabbar, `the section tabbar at ${width} px`).not.toBeNull();
  for (const notice of await toasts(page).all()) {
    await expect.soft(notice, `a toast whole on screen at ${width} px`).toBeInViewport({ ratio: 1 });
    const box = await notice.boundingBox();
    expect.soft(box && tabbar && box.y + box.height <= tabbar.y, `a toast above the tabbar at ${width} px: ${JSON.stringify({ box, tabbar })}`).toBe(true);
  }
}

test('four notices: three on screen, the newest in front, the error with «Close», above the tabbar, in the three sizes', async ({
  signedInPage: page,
}) => {
  const held = await holdSaves(page);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/dashboard/account/preferences');
    const alerts = page.getByTestId('preferences-hub-alerts');
    await expect(alerts).toBeVisible();
    await settled(page);
    for (let save = 0; save < 4; save++) await alerts.click();
    await expect.poll(() => held.length).toBe(4);
    const [refused, ...saves] = held.splice(0);
    await refused.abort('internetdisconnected');
    await expect(toasts(page, 'error')).toHaveText(OFFLINE);
    for (const save of saves) await save.continue();

    // The fourth comes in at once: the oldest saved one leaves for it, the error stays at the back.
    await expect(toasts(page, 'success')).toHaveCount(2);
    await expect(toasts(page)).toHaveCount(3);
    await expect(toasts(page).first()).toHaveAttribute('data-tone', 'success');
    await expect(toasts(page).last()).toHaveAttribute('data-tone', 'error');
    await expect(toasts(page, 'success').getByRole('button', { name: 'Close' })).toHaveCount(0);
    await settled(page);
    await expectAboveTabbar(page, viewport.width);

    // Under the pointer the stack opens into a list and stops its clocks: the error's «Close» can be pressed, and
    // nothing waited to take its place.
    await toasts(page).first().hover();
    await settled(page);
    await expectAboveTabbar(page, viewport.width);
    await page.screenshot({ path: shot(`PANEL-TOAST-STACK-${viewport.width}`) });
    await toasts(page, 'error').getByRole('button', { name: 'Close' }).click();
    await expect(toasts(page, 'error')).toHaveCount(0);
    await expect(toasts(page, 'success')).toHaveCount(2);
    await expect(toasts(page, 'success').filter({ hasText: SAVED })).toHaveCount(2);
  }
});
