// The public web of erplora.com, flow by flow (APP-PUBLIC-1, public/WORKBOOK.md PUBLIC-F01…F14), in a real
// Chrome under the production CSP with zero violations: the home, the plans and the price painted against the
// price of each plan's page, the industries, the product pages, what the web promises, /compliance/, the
// company pages, every «Start free» down to the sign-in, the «coming soon» pages and the retired addresses,
// the footer's language switcher, and robots, the sitemap, llms.txt and the structured data. Each screen is
// captured at 390×844, 834×1112 and 1440×900 as `APP-PUBLIC-1-<key>-<width>.png` in `.artifacts/`.
// flow: PUBLIC-G30 PUBLIC-G31 PUBLIC-G32 PUBLIC-G33 PUBLIC-G34 PUBLIC-G35 PUBLIC-G36 PUBLIC-G37 PUBLIC-G42
// flow: PUBLIC-G48 PUBLIC-G49 PUBLIC-G50 PUBLIC-G51 PUBLIC-G52
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from './django-env';
import { expect, test } from './public-test';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..', '..');
const ARTIFACTS = join(HERE, '.artifacts');
const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
];

/** Every CSP violation and page error, however the browser reports it (as demo-door.spec.ts). */
async function watch(page: Page) {
  const reports: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return async (where: string) => {
    const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
    expect({ violations, reports, consoleErrors, pageErrors }, where).toEqual({
      violations: [],
      reports: [],
      consoleErrors: [],
      pageErrors: [],
    });
  };
}

/** The page at the three viewports, each loaded afresh, captured whole as `APP-PUBLIC-1-<key>-<width>.png`. */
async function captureEverywhere(page: Page, path: string, key: string, ready: (page: Page) => Promise<void>) {
  mkdirSync(ARTIFACTS, { recursive: true });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto(path);
    await ready(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} overflows sideways at ${viewport.width}px`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(ARTIFACTS, `APP-PUBLIC-1-${key}-${viewport.width}.png`), fullPage: true });
  }
}

const heading = (page: Page) => page.getByRole('heading', { level: 1 });

test.beforeAll(() => {
  // The industries are the taxonomy every deploy seeds (saas-migrate runs seed_taxonomy): the same here.
  execFileSync('uv', ['run', 'python', 'manage.py', 'seed_taxonomy'], { cwd: SAAS_DIR, env: djangoEnv(true) });
});

// Reduced motion paints every revealed block at once, so a full-page capture shows the whole page (as public-dark.spec.ts).
test.use({ locale: 'en-GB', reducedMotion: 'reduce' });

test('PUBLIC-G30 the home shows the product, its apps, its plans and its three doors', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/', 'PUBLIC-G30', async (p) => {
    await expect(heading(p)).toContainText('One ERP.');
    await expect(p.locator('section.hero-bg ion-button[href="/launch"]')).toBeVisible();
  });

  await expect(page.locator('section.hero-bg ion-button[href="/demo/"]')).toBeVisible();
  await expect(page.locator('section.hero-bg ion-button[href="/download/"]')).toBeVisible();
  await expect(page.locator('#planes .ep-pricing-card')).not.toHaveCount(0);
  await clean('/');
});

test('PUBLIC-G49 the home and the plans promise only what the product does', async ({ page }) => {
  const clean = await watch(page);
  await page.goto('/');

  const stack = page.locator('table.ep-table-stack', { has: page.locator('tr.font-semibold') });
  const rows = stack.locator('tbody tr:not(.font-semibold) td.font-mono');
  const costs = (await rows.allTextContents()).map((cell) => Number(cell.replace('€', '')));
  const total = Number((await stack.locator('tr.font-semibold td.font-mono').textContent())!.replace('€', ''));
  expect(costs.length).toBeGreaterThan(0);
  expect(total).toBe(costs.reduce((sum, cost) => sum + cost, 0));
  for (const claim of ['v3.4', 'QuickBooks', 'HR and payroll', 'Support tickets', 'Healthcare']) {
    await expect(page.getByText(claim, { exact: false })).toHaveCount(0);
  }

  await captureEverywhere(page, '/pricing/', 'PUBLIC-G49', async (p) => {
    await expect(p.locator('.compare-table').first()).toBeVisible();
  });
  for (const claim of ['TicketBAI', 'bank reconciliation', 'multi-warehouse']) {
    await expect(page.getByText(claim, { exact: false })).toHaveCount(0);
  }
  await clean('/ and /pricing/');
});

test('PUBLIC-G31 the plans: a card per plan on sale, the upgrade-only ones under More capacity, the annual saving worked out and the storage answer', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/pricing/', 'PUBLIC-G31', async (p) => {
    // Three plans to sign up on, then the three upgrade-only ones under «More capacity» (Ioan, 2026-10-24).
    await expect(p.locator('.ep-pricing-card')).toHaveCount(6);
    await expect(p.locator('#more-capacity .ep-pricing-card')).toHaveCount(3);
    await expect(p.locator('#more-capacity ion-button[href="/launch"]')).toBeVisible();
  });

  // More capacity (PLAN-SAAS §9): Pro, Enterprise and Max from their rows, each saying when it opens instead of a
  // sign-up button, and one call to action to start free.
  const more = page.locator('#more-capacity');
  await expect(more.getByRole('heading', { level: 2 })).toHaveText('More capacity');
  await expect(more.locator('.ep-pricing-card__name')).toHaveText(['Pro', 'Enterprise', 'Max']);
  await expect(more.locator('.ep-pricing-card__amount')).toHaveText(['€109.99', '€209.99', '€419.99']);
  await expect(more.locator('.ep-pricing-card__cta')).toHaveText(Array(3).fill('Available once you are on Starter'));
  await expect(more.locator('.ep-pricing-card ion-button')).toHaveCount(0);
  await expect(more.locator('ion-button')).toHaveCount(1);
  await expect(more.locator('ion-button[href="/launch"]')).toContainText('Start free and upgrade whenever you want');
  const table = page.locator('#plan-compare');
  await expect(table.locator('tbody strong')).toHaveText(['Free', 'Starter', 'Standard', 'Pro', 'Enterprise', 'Max']);
  await expect(table.getByText('Available once you are on Starter')).toHaveCount(3);
  await expect(page.getByText('all your locations', { exact: false })).toHaveCount(0);

  const starter = page.locator('.ep-pricing-card', { has: page.locator('.ep-pricing-card__name', { hasText: 'Starter' }) });
  await expect(starter).toContainText('€29.99');
  await expect(starter).toContainText('≈ €299.90/year · 2 months free');
  await expect(page.getByText('Pay for the year and get 2 months free.')).toBeVisible();
  await page.locator('ion-accordion[value="storage"] ion-item').click();
  const storage = page.locator('ion-accordion[value="storage"] [slot="content"]');
  await expect(storage).toContainText('if its European provider is unavailable');
  await expect(storage.getByRole('link', { name: 'Read the privacy policy' })).toHaveAttribute('href', '/legal/privacy/');
  await clean('/pricing/');
});

test('PUBLIC-G32 PUBLIC-G33 a plan page paints the price of its card', async ({ page }) => {
  const clean = await watch(page);
  await page.goto('/pricing/');
  const painted = await page
    .locator('.ep-pricing-card', { has: page.locator('.ep-pricing-card__name', { hasText: 'Standard' }) })
    .locator('.ep-pricing-card__amount')
    .textContent();

  await captureEverywhere(page, '/pricing/standard/', 'PUBLIC-G32', async (p) => {
    await expect(heading(p)).toContainText('Standard');
  });

  expect(painted).toBe('€54.99');
  await expect(page.getByText('54.99 €', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('All prices exclude VAT', { exact: false }).first()).toBeVisible();
  expect((await page.goto('/pricing/pro/'))?.status()).toBe(404);
  await clean('/pricing/standard/');
});

test('PUBLIC-G34 the industries: the list, one business type and its links', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/industries/', 'PUBLIC-G34', async (p) => {
    await expect(p.locator('a.ep-product-card[href="/industries/hair_salon/"]')).toBeVisible();
  });
  await page.locator('a.ep-product-card[href="/industries/hair_salon/"]').click();
  await expect(page).toHaveURL(/\/industries\/hair_salon\/$/);

  await captureEverywhere(page, '/industries/hair_salon/', 'PUBLIC-G06', async (p) => {
    await expect(heading(p)).toContainText('hair salon', { ignoreCase: true });
  });
  await expect(page.locator('a.ep-feature-card[href="/compliance/"]')).toBeVisible();
  await clean('/industries/');
});

test('PUBLIC-G35 PUBLIC-G50 features, security and updates say what runs', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/features/', 'PUBLIC-G35', async (p) => {
    await expect(heading(p)).toBeVisible();
  });
  await captureEverywhere(page, '/updates/', 'PUBLIC-G16', async (p) => {
    await expect(p.locator('ion-button[href="/legal/terms/"]', { hasText: 'Read section 7' })).toBeVisible();
  });
  await captureEverywhere(page, '/security/', 'PUBLIC-G50', async (p) => {
    await expect(p.getByText('HTTPS only, with TLS 1.2 or 1.3')).toBeVisible();
  });
  for (const claim of ['TLS 1.3 required', 'security audits', 'pentest']) {
    await expect(page.getByText(claim, { exact: false })).toHaveCount(0);
  }
  await page.locator('ion-button', { hasText: 'Contact Security Team' }).click();
  // The form opens on the security topic (PUBLIC-G40, APP-PUBLIC-2).
  await expect(page).toHaveURL(/\/contact\/\?subject=security$/);
  await expect(page.locator('form[action="/contact/submit/"]')).toBeVisible();
  await clean('/security/ → /contact/');
});

test('PUBLIC-G36 compliance: the countries, the one connected and the rest, from the footer', async ({ page }) => {
  const clean = await watch(page);
  await page.goto('/');
  await page.locator('footer a[href="/compliance/"]').click();
  await expect(page).toHaveURL(/\/compliance\/$/);

  await captureEverywhere(page, '/compliance/', 'PUBLIC-G36', async (p) => {
    await expect(heading(p)).toContainText('EU compliance.');
    await expect(p.locator('[data-country="ES"]')).toContainText('VeriFactu');
  });
  await expect(page.locator('[data-country]')).toHaveCount(27);
  await expect(page.locator('[data-figure="connected"]')).toHaveText('1');
  await expect(page.locator('[data-country="ES"]')).toContainText('TicketBAI');
  await expect(page.locator('[data-country="FR"]')).toContainText('Not connected yet');
  await clean('/compliance/');
});

test('PUBLIC-G37 the company: about, collaborate, the old address and the coming-soon pages', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/about/', 'PUBLIC-G37', async (p) => {
    await expect(heading(p)).toContainText('About ERPlora.');
  });
  await captureEverywhere(page, '/collaborate/', 'PUBLIC-G12', async (p) => {
    await expect(p.getByText('valued at €299.90/year', { exact: false })).toBeVisible();
  });
  await page.goto('/company/');
  await expect(page).toHaveURL(/\/about\/$/);
  await clean('/about/, /collaborate/, /company/');
});

test('PUBLIC-G51 every «Start free» and «Get started» ends at the sign-in, which also signs up', async ({ page }) => {
  const doors: Array<[string, string]> = [
    ['/', 'section.hero-bg ion-button[href="/launch"]'],
    ['/', '#planes ion-button[href="/launch"] >> nth=1'],
    ['/pricing/', '.ep-pricing-card ion-button[href="/launch"] >> nth=0'],
    ['/pricing/starter/', 'main ion-button[href="/launch"] >> nth=0'],
    ['/industries/hair_salon/', 'main ion-button[href="/launch"] >> nth=0'],
    ['/features/', 'main ion-button[href="/launch"] >> nth=0'],
    ['/compliance/', 'nav ion-button[href="/launch"]'],
  ];
  for (const [path, door] of doors) {
    await page.goto(path);
    await page.locator(door).click();
    await expect(page, `${path} ${door}`).toHaveURL(/\/launch$/);
    await expect(page.getByTestId('login-form')).toBeVisible();
  }
  await expect(page.locator('#planes')).toHaveCount(0);

  await captureEverywhere(page, '/launch', 'PUBLIC-G51', async (p) => {
    await expect(p.getByTestId('login-form')).toBeVisible();
  });
  await page.goto('/');
  await expect(page.locator('#planes .ep-pricing-card').first()).toContainText('Start free');
  await expect(page.locator('#planes .ep-pricing-card').nth(1)).toContainText('Get started');
});

test('PUBLIC-G52 the coming-soon pages are not indexed and the retired addresses answer for good', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/blog/', 'PUBLIC-G52', async (p) => {
    await expect(heading(p)).toBeVisible();
  });
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  for (const path of ['/careers/', '/press/']) {
    await page.goto(path);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  }
  for (const path of ['/developers/', '/bridge/']) {
    expect((await page.goto(path))?.status(), path).toBe(404);
  }
  for (const path of ['/marketplace/', '/solutions/', '/modules/']) {
    await page.goto(path);
    await expect(page, path).toHaveURL(/\/apps\/$/);
  }
  await clean('coming soon and retired');
});

test('PUBLIC-G42 a visitor switches the language from the footer and it stays', async ({ page, context }) => {
  const clean = await watch(page);
  await page.goto('/pricing/');
  await expect(heading(page)).toContainText('Start free.');

  await page.locator('.ep-footer__language ion-button[lang="es"]').click();

  await expect(page).toHaveURL(/\/pricing\/$/);
  await expect(heading(page)).toContainText('Empieza gratis.');
  // Ionic moves aria-current into the native button of its shadow, where assistive technology reads it.
  await expect(page.locator('.ep-footer__language ion-button[lang="es"] button')).toHaveAttribute('aria-current', 'true');
  expect((await context.cookies()).find((cookie) => cookie.name === '_lang')?.value).toBe('es');
  await page.goto('/compliance/');
  await expect(heading(page)).toContainText('Cumplimiento en la UE.');
  await expect(page.locator('[data-country="FR"]')).toContainText('Francia');

  await captureEverywhere(page, '/compliance/', 'PUBLIC-G42', async (p) => {
    await expect(p.locator('.ep-footer__language')).toBeVisible();
  });
  await page.locator('.ep-footer__language ion-button[lang="en"]').click();
  await expect(heading(page)).toContainText('EU compliance.');
  await clean('language switch');
});

test('PUBLIC-G48 robots, the sitemap, llms.txt and the structured data', async ({ page, request }) => {
  const robots = await request.get('/robots.txt');
  expect(robots.status()).toBe(200);
  expect(await robots.text()).toContain('User-agent: *');

  const sitemap = await (await request.get('/sitemap.xml')).text();
  for (const path of ['/compliance/</loc>', '/pricing/</loc>', '/industries/hair_salon/</loc>']) {
    expect(sitemap).toContain(path);
  }
  const llms = await (await request.get('/llms.txt')).text();
  expect(llms).toContain('/compliance/)');

  await page.goto('/');
  const blocks = await page.locator('script[type="application/ld+json"]').allTextContents();
  const application = blocks.map((block) => JSON.parse(block)).find((block) => block['@type'] === 'SoftwareApplication');
  expect(application.operatingSystem).toBe('Web, Windows, Linux, Android');
});
