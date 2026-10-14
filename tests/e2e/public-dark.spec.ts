// The public web follows the visitor's colour mode, as the panel does (Ioan, 2026-10-14): light on a
// light system, dark on a dark one, with no flash and live when the system changes. A signed-in
// account's own choice (Account → Preferences) is written by the server and covered by
// public/tests/test_templates.py; here, the system's, in Ioan's visible Chrome.
//
// Every page is checked at 390 and 1440 px in both schemes: the canvas (<html>), the text and the
// page hero (a soft band that turned grey in dark) must be dark or light as the scheme says, under the
// public CSP with zero violations. The screenshots stay in `.artifacts/public-dark/` for review.
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page, expect, test } from '@playwright/test';

const ARTIFACTS = join(dirname(fileURLToPath(import.meta.url)), '.artifacts', 'public-dark');
const PAGES = ['/', '/pricing/', '/apps/', '/legal/privacy/'];
const WIDTHS = [390, 1440];
const SCHEMES = ['dark', 'light'] as const;

type Scheme = (typeof SCHEMES)[number];

/** Every CSP violation of the page, however the browser reports it (as store-docs.spec.ts). */
async function watchCsp(page: Page) {
  const reports: string[] = [];
  const consoleErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return async () => ({
    violations: await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp),
    reports,
    consoleErrors,
  });
}

/** WCAG relative luminance of the colours that paint the page: 0 is black, 1 is white. */
async function luminances(page: Page) {
  return page.evaluate(() => {
    // A canvas turns any CSS colour (rgb, oklab, color-mix…) into sRGB bytes.
    const context = document.createElement('canvas').getContext('2d')!;
    const luminance = (css: string) => {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = '#000';
      context.fillStyle = css;
      context.fillRect(0, 0, 1, 1);
      const [r, g, b] = [...context.getImageData(0, 0, 1, 1).data].map((byte) => {
        const c = byte / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const hero = document.querySelector('.ep-hero');
    return {
      canvas: luminance(getComputedStyle(document.documentElement).backgroundColor),
      text: luminance(getComputedStyle(document.body).color),
      hero: hero ? luminance(getComputedStyle(hero).backgroundColor) : null,
      dark: document.documentElement.classList.contains('ion-palette-dark'),
    };
  });
}

function expectScheme(seen: Awaited<ReturnType<typeof luminances>>, scheme: Scheme, where: string) {
  if (scheme === 'dark') {
    expect(seen.dark, where).toBe(true);
    expect(seen.canvas, `${where}: dark canvas`).toBeLessThan(0.05);
    expect(seen.text, `${where}: light text`).toBeGreaterThan(0.7);
    if (seen.hero !== null) expect(seen.hero, `${where}: dark hero`).toBeLessThan(0.05);
  } else {
    expect(seen.dark, where).toBe(false);
    expect(seen.canvas, `${where}: light canvas`).toBeGreaterThan(0.85);
    expect(seen.text, `${where}: dark text`).toBeLessThan(0.05);
    if (seen.hero !== null) expect(seen.hero, `${where}: light hero`).toBeGreaterThan(0.85);
  }
}

function shot(scheme: Scheme, width: number, path: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  const slug = path.replace(/^\/|\/$/g, '').replace(/\//g, '-') || 'home';
  return join(ARTIFACTS, `${scheme}-${width}-${slug}.png`);
}

for (const scheme of SCHEMES) {
  test.describe(`a ${scheme} system`, () => {
    // Reduced motion: the scroll reveal shows every block at once, so a full-page shot shows them all.
    test.use({ colorScheme: scheme, reducedMotion: 'reduce' });

    for (const width of WIDTHS) {
      test(`paints the public pages ${scheme} at ${width} px, with no CSP violation`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        const csp = await watchCsp(page);

        for (const path of PAGES) {
          const response = await page.goto(path);
          expect(response?.status(), path).toBe(200);
          await expect(page.locator('html')).toHaveAttribute('data-ep-theme', 'system');

          expectScheme(await luminances(page), scheme, `${path} at ${width}`);
          await page.screenshot({ path: shot(scheme, width, path), fullPage: true });
        }

        await page.waitForTimeout(1000); // late violations (lazy chunks, fonts, styles)
        expect(await csp()).toEqual({ violations: [], reports: [], consoleErrors: [] });
      });
    }
  });
}

test.describe('the system changing', () => {
  test.use({ colorScheme: 'dark', reducedMotion: 'reduce' });

  test('turns an open page light and back to dark, live', async ({ page }) => {
    await page.goto('/pricing/');
    expectScheme(await luminances(page), 'dark', 'before');

    await page.emulateMedia({ colorScheme: 'light' });
    await expect(page.locator('html')).not.toHaveClass(/ion-palette-dark/);
    expectScheme(await luminances(page), 'light', 'after the system went light');

    await page.emulateMedia({ colorScheme: 'dark' });
    await expect(page.locator('html')).toHaveClass(/ion-palette-dark/);
    expectScheme(await luminances(page), 'dark', 'after the system went dark again');
  });

  test("is dark from the first paint, before the entry's script runs", async ({ page }) => {
    // Without frontend/public.ts the head's inline script alone must have darkened the page: the
    // module script runs after the first paint could happen, so a page that waited for it flashed.
    await page.route(/\/static\/spa\/assets\/public-[^/]+\.js$/, (route) => route.abort());

    await page.goto('/pricing/');

    expectScheme(await luminances(page), 'dark', 'without the entry script');
  });
});
