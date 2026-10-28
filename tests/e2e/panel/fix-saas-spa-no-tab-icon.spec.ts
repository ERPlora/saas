// FIX-SAAS-SPA-NO-TAB-ICON in Chrome: the panel (the SPA of erplora.com) declares the public web's icons for the tab
// and the home screen, static files of the SaaS, and the page's own CSP lets them load. Headless Chrome paints no
// tab, so the icon is checked in the <head>, fetched (200, an image) and drawn in the page under its CSP. The launcher
// without a session and Businesses with one; accounts of panel_seed.py; at 390, 834 and 1440 px.
// flow: saas-spa-icon
import type { Page } from '@playwright/test';
import { expect, panelAccount, seedPanel, settled, shot, signIn, test, VIEWPORTS } from './fixtures';

const KEY = 'FIX-SAAS-SPA-NO-TAB-ICON';
const ICONS = [
  { rel: 'icon', href: '/static/img/favicon.ico', sizes: 'any' },
  { rel: 'apple-touch-icon', href: '/static/public/img/apple-touch-icon.png', sizes: null },
] as const;

/**
 * Errors the page throws and what its CSP refuses (Chrome logs each refusal as a console error) from now on. Not
 * every console error: without a session the launcher's session lookup answers 401 by design.
 */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  page.on('console', (message) => {
    if (message.type() === 'error' && /Content Security Policy|Refused to/.test(message.text()))
      errors.push(message.text());
  });
  return errors;
}

/** The icons the <head> links, and whether each one loads as an image under the page's CSP (its natural width). */
async function expectTheIcons(page: Page): Promise<void> {
  for (const icon of ICONS) {
    const link = page.locator(`head link[rel="${icon.rel}"]`);
    await expect(link, icon.rel).toHaveCount(1);
    await expect(link, icon.rel).toHaveAttribute('href', icon.href);
    expect(await link.getAttribute('sizes'), icon.rel).toBe(icon.sizes);

    const answer = await page.request.get(icon.href);
    expect(answer.status(), icon.href).toBe(200);
    expect(answer.headers()['content-type'], icon.href).toMatch(/^image\//);

    const width = await page.evaluate(
      (href) =>
        new Promise<number>((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve(image.naturalWidth);
          image.onerror = () => reject(new Error(`${href} did not load`));
          image.src = href;
        }),
      icon.href,
    );
    expect(width, icon.href).toBeGreaterThan(0);
  }
}

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('saas-spa-icon · the launcher declares the ERPlora icons of the public web and they load under its CSP, at 390, 834 and 1440 px', async ({
  page,
}) => {
  const errors = watchErrors(page);

  for (const size of VIEWPORTS) {
    await page.setViewportSize(size);
    await page.goto('/launch');
    await expect(page.getByTestId('login-form')).toBeVisible();
    await expectTheIcons(page);
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-${size.width}`), fullPage: true });
  }
  expect(errors).toEqual([]);
});

test('saas-spa-icon · the panel signed in declares the same icons on Businesses', async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page.request, panelAccount('several'));

  await page.goto('/dashboard/businesses');
  await expect(page.getByTestId('businesses-row').first()).toBeVisible();
  await expectTheIcons(page);
  expect(errors).toEqual([]);
});
