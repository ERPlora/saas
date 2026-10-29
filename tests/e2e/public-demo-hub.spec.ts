// The demo's door against a real Hub (APP-PUBLIC-3, public/WORKBOOK.md PUBLIC-F28 and PUBLIC-F35): «Try the demo»
// creates an empty demo hub, the jump posts its one-time code and the browser lands in its shell as
// «Demo», with no account; back on the door, «Your demo is running» with the minutes left, «Back to my demo» into the
// same demo and «Start free» beside it. The door and the shell are captured at 390×844, 834×1112 and 1440×900 as
// `APP-PUBLIC-3-<key>-<width>.png` in `.artifacts/`.
//
// It needs a Hub whose SAAS_URL is this run's public server and this server's Hub variables exported for it (README
// of this folder, «La demo contra un Hub de verdad»): `E2E_DEMO_HUB` is that Hub's origin, and without it every test
// here is skipped and says so. The walk to the ended demo (410 → the door) is the Hub's tests/e2e/demo.spec.ts.
// flow: PUBLIC-G54 PUBLIC-G55 PUBLIC-G56 PUBLIC-G63
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { horizontalOverflow } from './horizontal-overflow';
import { expect, test } from './public-test';

const HERE = dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = join(HERE, '.artifacts');
const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
];
const DOOR = '/demo/';
const HUB = process.env.E2E_DEMO_HUB ?? '';
const HUB_PORT = HUB ? new URL(HUB).port : '';
const DEMO_HOST = new RegExp(`^http://(demo-[0-9a-f]{8})\\.localhost:${HUB_PORT}/`);

test.skip(!HUB, 'needs a real Hub: export E2E_DEMO_HUB (tests/e2e/README.md, «La demo contra un Hub de verdad»)');
test.use({ locale: 'en-GB' });

/** The demo's shell is up: the Hub's top bar. */
async function inTheDemo(page: Page): Promise<string> {
  await page.waitForURL(DEMO_HOST, { timeout: 30_000 });
  await expect(page.locator('[data-testid=topbar-apps]').first()).toBeAttached({ timeout: 30_000 });
  const slug = DEMO_HOST.exec(page.url())?.[1];
  if (!slug) throw new Error(`not on a demo host: ${page.url()}`);
  return slug;
}

test('PUBLIC-G54 PUBLIC-G55 PUBLIC-G56 a press creates the demo, opens it as «Demo» and the door takes it back', async ({
  page,
  context,
}) => {
  // Every address the browser asks for on the way in (redirects included): the jump's page posts itself at once, so
  // its «Opening your demo…» is checked by public/tests/test_demo.py, and here that the code never sits in one.
  const asked: string[] = [];
  page.on('request', (request) => asked.push(request.url()));

  await page.goto(DOOR);
  await page.getByTestId('demo-start').click();
  const slug = await inTheDemo(page);

  // Through the SaaS's entry with the Hub's state, and the code posted in a form, never in an address.
  expect(asked.filter((url) => url.includes('/demo/enter/?') && url.includes('state='))).toHaveLength(1);
  expect(asked.filter((url) => /[?&]code=/.test(url))).toEqual([]);

  const me = await context.request.get(`http://${slug}.localhost:${HUB_PORT}/api/me`, {
    headers: { Accept: 'application/json' },
  });
  expect(me.status()).toBe(200);
  const body = (await me.json()) as { user: { label: string } | null; demo: { expires_at: string } | null };
  expect(body.user?.label).toBe('Demo');
  expect(Date.parse(body.demo?.expires_at ?? '')).toBeGreaterThan(Date.now());

  mkdirSync(ARTIFACTS, { recursive: true });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);

    await page.goto(DOOR);
    const running = page.getByTestId('demo-state-ready');
    await expect(running).toContainText('Your demo is running');
    await expect(running).toContainText(/It ends in \d+ minutes?\./);
    await expect(page.getByTestId('demo-start')).toHaveCount(0);
    const startFree = await running.evaluate((element) =>
      [...element.querySelectorAll('[href="/launch"]')].map((link) => (link.textContent ?? '').trim()),
    );
    expect(startFree).toEqual(['Start free']);
    const overflow = await horizontalOverflow(page);
    expect(overflow, `the running door overflows at ${viewport.width}px`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(ARTIFACTS, `APP-PUBLIC-3-PUBLIC-G54-${viewport.width}.png`), fullPage: true });

    // «Back to my demo»: the same demo, not another one.
    await page.locator('ion-button', { hasText: 'Back to my demo' }).click();
    expect(await inTheDemo(page)).toBe(slug);
    await page.screenshot({ path: join(ARTIFACTS, `APP-PUBLIC-3-PUBLIC-G56-${viewport.width}.png`) });
  }
});
