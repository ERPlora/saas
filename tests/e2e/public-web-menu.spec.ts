// PUBLIC-F11 on a phone, on the public web of erplora.com: the mobile menu opens and closes, and its buttons lead on,
// even pressed before the page's script has run; once the script has run one press still opens it and one closes it;
// and while it is open Tab goes round inside it and the page behind waits until it closes.
// flow: PUBLIC-F11
import { join } from 'node:path';

import type { Page, Route } from '@playwright/test';

import { horizontalOverflow } from './horizontal-overflow';
import { expect, test } from './public-test';
import { ARTIFACTS, watch } from './public-web';

// Reduced motion paints every revealed block at once, so a full-page capture shows the whole page (as public-dark.spec.ts).
test.use({ locale: 'en-GB', reducedMotion: 'reduce' });

/** The mobile menu's pieces (public/partials/navbar.html) and what each state of it must say. */
function mobileMenu(page: Page) {
  const navbar = page.locator('nav[data-navbar]');
  const burger = page.locator('button[data-navbar-toggle]');
  const panel = page.locator('#ep-navbar-panel');
  const close = page.locator('button[data-navbar-close]');
  return {
    burger,
    close,
    panel,
    backdrop: page.locator('.ep-navbar__backdrop'),
    async isOpen(where: string) {
      await expect(navbar, where).toHaveAttribute('data-open', '');
      await expect(panel, where).toBeVisible();
      await expect(burger, where).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('html'), where).toHaveClass(/\bep-navbar-open\b/);
      await expect(close, where).toBeFocused();
    },
    async isClosed(where: string) {
      await expect(navbar, where).not.toHaveAttribute('data-open', '');
      await expect(panel, where).toBeHidden();
      await expect(burger, where).toHaveAttribute('aria-expanded', 'false');
      await expect(page.locator('html'), where).not.toHaveClass(/\bep-navbar-open\b/);
    },
  };
}

test('PUBLIC-F11 on a slow device, the mobile menu opens and closes even pressed before the page script has run', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 667 });
  // The page's scripts have not arrived when the person presses (saas#243): held until the end. The stylesheet has,
  // so the page already reads whole and the burger shows.
  const held: Route[] = [];
  await page.route('**/static/spa/**/*.js', (route) => {
    held.push(route);
  });
  const clean = await watch(page);
  const menu = mobileMenu(page);
  // The control: the page's script has really not run, so nothing but the HTML can open anything.
  const scriptHasNotRun = async (where: string) =>
    expect(await page.evaluate(() => customElements.get('ion-button') === undefined), where).toBe(true);

  // The home, the door (its own policy, wider only on form-action) and the public 404: each renders the navbar and its nonce.
  for (const path of ['/', '/demo/', '/pricing/no-such-plan/']) {
    await page.goto(path, { waitUntil: 'commit' });
    await menu.burger.click();
    await menu.isOpen(`${path} opened`);
    await scriptHasNotRun(path);
    await clean(path);
  }

  // Each way out says it is closed; the two that leave the focus in the panel give it back to the burger.
  await page.goto('/', { waitUntil: 'commit' });
  await menu.burger.click();
  await menu.isOpen('before Escape');
  await page.keyboard.press('Escape');
  await menu.isClosed('Escape');
  await expect(menu.burger).toBeFocused();

  await menu.burger.click();
  await menu.isOpen('before the close button');
  await menu.close.click();
  await menu.isClosed('the close button');
  await expect(menu.burger).toBeFocused();

  await menu.burger.click();
  await menu.isOpen('before the backdrop');
  // The strip the panel leaves free on the left, above the cookie notice.
  await menu.backdrop.click({ position: { x: 16, y: 120 } });
  await menu.isClosed('the backdrop');

  // Back to the desktop bar with the panel open: nothing stays locked.
  await menu.burger.click();
  await menu.isOpen('before widening');
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator('nav[data-navbar]')).not.toHaveAttribute('data-open', '');
  await expect(page.locator('html')).not.toHaveClass(/\bep-navbar-open\b/);
  await page.setViewportSize({ width: 375, height: 667 });
  await menu.isClosed('widened and back');

  // The keyboard too: every stop of the panel is a real link or button, so it goes round the same with no module.
  await menu.burger.click();
  await menu.isOpen('before Tab');
  const stops = await panelLinks(page);
  expect(stops, 'what the keyboard goes through').toEqual(expect.arrayContaining(['/features/', '/demo/', '/launch']));
  await pressThrough(page, 'Tab', [...stops, 'close']);
  await pressThrough(page, 'Shift+Tab', [...stops].reverse().concat('close'));
  await page.keyboard.press('Escape');
  await menu.isClosed('Escape after going round');
  await expect(menu.burger).toBeFocused();

  // What the menu is for: the sign-up and the demo are in it, and a link of the panel leads on, closing it on its way.
  await menu.burger.click();
  await menu.isOpen('before a link');
  await expect(menu.panel.locator('[href="/launch"]')).toBeVisible();
  await expect(menu.panel.locator('[href="/demo/"]')).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, 'PUBLIC-G51-menu-before-the-script-375x667.png'), animations: 'disabled' });
  await menu.panel.locator('a[href="/features/"]').click();
  await expect(page).toHaveURL(/\/features\/$/);
  await menu.isClosed('the page the link led to');
  await scriptHasNotRun('after every press');
  await clean('after every press');

  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await Promise.all(held.map((route) => route.continue().catch(() => undefined)));
});

test('PUBLIC-F11 on a slow phone, the buttons of the menu lead on even pressed before the page script has run', async ({
  page,
}) => {
  // Pressing before the page's scripts arrive, on a phone, where the header's buttons live in the menu (which opens
  // without the script, saas#243).
  await page.setViewportSize({ width: 375, height: 667 });
  const held: Route[] = [];
  await page.route('**/static/spa/**/*.js', (route) => {
    held.push(route);
  });
  const menu = mobileMenu(page);

  for (const [button, destination] of [
    ['[href="/launch"]', /\/launch$/],
    ['[href="/demo/"]', /\/demo\/$/],
  ] as const) {
    await page.goto('/pricing/', { waitUntil: 'commit' });
    await menu.burger.click();
    await menu.isOpen(button);
    // The control: the page's script has really not run, so nothing but the HTML can lead anywhere.
    expect(await page.evaluate(() => customElements.get('ion-button') === undefined), button).toBe(true);

    await menu.panel.locator(button).click();
    await expect(page, button).toHaveURL(destination);
  }

  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await Promise.all(held.map((route) => route.continue().catch(() => undefined)));
});

test('PUBLIC-F11 once the page script has run, one press opens the mobile menu and one closes it', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  const clean = await watch(page);
  const menu = mobileMenu(page);

  // public.ts is a module with no `async`: it has run by DOMContentLoaded. A second binding of the burger would
  // answer the same press again and close what it opened, which only shows once the script is there.
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  expect(await page.evaluate(() => customElements.get('ion-button') !== undefined)).toBe(true);

  await menu.burger.click();
  await menu.isOpen('opened');
  expect(await horizontalOverflow(page), 'the open panel').toBe(0);
  await page.screenshot({ path: join(ARTIFACTS, 'PUBLIC-G51-menu-375x667.png'), animations: 'disabled' });
  await menu.close.click();
  await menu.isClosed('closed');
  await expect(menu.burger).toBeFocused();
  await clean('with the script');
});

/** Where the focus is, as the person would read it: the `href` of a link, `close`, or what it is out of the panel. */
function focusedStop(page: Page): Promise<string> {
  return page.evaluate(() => {
    const active = document.activeElement!;
    const stop = active.matches('button[data-navbar-close]') ? 'close' : (active.getAttribute('href') ?? active.tagName);
    return active.closest('#ep-navbar-panel') ? stop : `outside: ${stop}`;
  });
}

/** The `href` of each link of the panel, in order: what Tab goes through after the close button. */
function panelLinks(page: Page): Promise<string[]> {
  return page.locator('#ep-navbar-panel a[href]').evaluateAll((links) => links.map((link) => link.getAttribute('href')!));
}

/** Presses the key once per expected stop and checks where the focus landed each time. */
async function pressThrough(page: Page, key: 'Tab' | 'Shift+Tab', stops: string[]) {
  for (const [press, stop] of stops.entries()) {
    await page.keyboard.press(key);
    expect(await focusedStop(page), `${key} number ${press + 1}`).toBe(stop);
  }
}

test('PUBLIC-F11 with the mobile menu open, Tab goes round inside it and the page behind waits until it closes', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  const clean = await watch(page);
  const menu = mobileMenu(page);
  await page.goto('/');
  const behind = page.locator('footer a[href]').first();

  await menu.burger.click();
  await menu.isOpen('opened');
  const links = await panelLinks(page);
  expect(links, 'what the panel is for').toEqual(expect.arrayContaining(['/features/', '/demo/', '/launch']));

  // Two whole rounds forward, from the close button that opening focused, and one back.
  await pressThrough(page, 'Tab', [...links, 'close', ...links, 'close']);
  await pressThrough(page, 'Shift+Tab', [...links].reverse().concat('close'));

  // Pressing the bare panel takes the focus off every stop: the next Tab still comes back to it, not to the bar behind.
  await menu.panel.click({ position: { x: 8, y: 8 } });
  expect(await focusedStop(page), 'a press on the bare panel').toBe('outside: BODY');
  await pressThrough(page, 'Shift+Tab', [links.at(-1)!]);
  await pressThrough(page, 'Tab', ['close']);

  // Not even by hand: what is behind takes no focus until the panel closes, also for assistive technology. The brand and
  // the burger are behind too: the panel and the backdrop cover them.
  for (const [what, element] of Object.entries({ page: behind, brand: page.locator('.ep-navbar__brand'), burger: menu.burger })) {
    await element.focus();
    expect(await focusedStop(page), `the ${what} behind, open`).toBe('close');
  }

  // On a slow connection the rest of the page can arrive with the panel already open: it waits behind as well.
  await page.evaluate(() => document.body.append(Object.assign(document.createElement('a'), { id: 'arrived-late', href: '/late/' })));
  const late = page.locator('#arrived-late');
  await expect(late, 'what arrives with the panel open').toHaveAttribute('inert', '');

  await page.keyboard.press('Escape');
  await menu.isClosed('Escape');
  await expect(menu.burger).toBeFocused();
  await expect(late, 'what arrived, once closed').not.toHaveAttribute('inert', '');

  // Closed, nothing stays locked: Tab goes on to the page, and what was behind takes the focus again.
  await page.keyboard.press('Tab');
  await expect(menu.burger, 'Tab with the panel closed moves on').not.toBeFocused();
  expect(await focusedStop(page), 'Tab with the panel closed').toMatch(/^outside: /);
  await behind.focus();
  await expect(behind).toBeFocused();

  // The other way out that has no press in the panel: widening to the desktop bar leaves nothing locked either.
  await menu.burger.click();
  await menu.isOpen('before widening');
  await page.setViewportSize({ width: 1440, height: 900 });
  // The window tells the script when it can: closed in the same step, so the page is back once this says so.
  await expect(page.locator('nav[data-navbar]')).not.toHaveAttribute('data-open', '');
  await behind.focus();
  await expect(behind).toBeFocused();
  await clean('after every press');
});
