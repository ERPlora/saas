// The public web of erplora.com, part 2 (APP-PUBLIC-2, public/WORKBOOK.md PUBLIC-F15…F28), in a real Chrome under
// the production CSP with zero violations: the help center and its search, the support routes, the contact form
// (its topic, what reaches support and what comes back when a message is refused), the cookie notice that only
// asks when there is something to ask, the legal texts and the responsible declaration, the documentation's old
// address, the app store with its filters and an app's page, the free hub on /download/ with the Free plan's
// limits, the app's page, the published version and the retired Bridge. Each screen is captured at 390×844,
// 834×1112 and 1440×900 as `APP-PUBLIC-2-<key>-<width>.png` in `.artifacts/`.
// flow: PUBLIC-G01 PUBLIC-G02 PUBLIC-G03 PUBLIC-G21 PUBLIC-G25 PUBLIC-G38 PUBLIC-G19 PUBLIC-G39 PUBLIC-G40
// flow: PUBLIC-G41 PUBLIC-G24 PUBLIC-G43 PUBLIC-G44 PUBLIC-G20 PUBLIC-G45 PUBLIC-G17 PUBLIC-G46 PUBLIC-G07
// flow: PUBLIC-G26 PUBLIC-G10 PUBLIC-G11 PUBLIC-G27 PUBLIC-G08 PUBLIC-G28 PUBLIC-G29 PUBLIC-G04
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page, expect, test } from '@playwright/test';

import { djangoEnv } from './django-env';
import { PUBLIC_MAIL_DIR } from './playwright.config';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..', '..');
const ARTIFACTS = join(HERE, '.artifacts');
const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
];
/** The app global-setup seeds (store_docs_seed.py): listed, with Spanish documentation, requiring another. */
const APP = 'e2e_store_docs';

/** Every CSP violation and page error, however the browser reports it (as public-web.spec.ts). */
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

/** The page at the three viewports, each loaded afresh, captured whole as `APP-PUBLIC-2-<key>-<width>.png`. */
async function captureEverywhere(page: Page, path: string, key: string, ready: (page: Page) => Promise<void>) {
  mkdirSync(ARTIFACTS, { recursive: true });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto(path);
    await ready(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} overflows sideways at ${viewport.width}px`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(ARTIFACTS, `APP-PUBLIC-2-${key}-${viewport.width}.png`), fullPage: true });
  }
}

const heading = (page: Page) => page.getByRole('heading', { level: 1 });

/** The mails the public server wrote (Django's file backend), newest last. */
function mails(): string[] {
  try {
    return readdirSync(PUBLIC_MAIL_DIR)
      .sort()
      .map((name) => readFileSync(join(PUBLIC_MAIL_DIR, name), 'utf8'));
  } catch {
    return [];
  }
}

/** Types into an ion-input / ion-textarea of the contact form. */
async function fill(page: Page, name: string, value: string) {
  await page.locator(`#contact-form [name="${name}"] :is(input, textarea)`).fill(value);
}

test.beforeAll(() => {
  // The cookie groups every deploy seeds (saas-migrate runs init_cookie_groups): the same here.
  execFileSync('uv', ['run', 'python', 'manage.py', 'init_cookie_groups'], { cwd: SAAS_DIR, env: djangoEnv(true) });
});

// Reduced motion paints every revealed block at once, so a full-page capture shows the whole page.
test.use({ locale: 'en-GB', reducedMotion: 'reduce' });

test('PUBLIC-G01 G02 G03 G21 G25 G38 the help center lists the guides, opens one and finds by search', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/help/', 'PUBLIC-G01', async (p) => {
    await expect(heading(p)).toContainText('Help center.');
    await expect(p.locator('[data-help-section]')).not.toHaveCount(0);
  });

  const first = page.locator('[data-help-section]').first();
  await first.locator('ion-item[slot="header"]').click();
  await expect(first.locator('[slot="content"]')).toBeVisible();

  await page.locator('#help-search input').fill('zzzz-no-guide-says-this');
  await expect(page.locator('#help-no-results')).toBeVisible();
  await page.locator('#help-search input').fill('');
  await expect(page.locator('#help-no-results')).toBeHidden();
  await clean('/help/');
});

test('PUBLIC-G19 the support page offers the guides, the form and the address', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/support/', 'PUBLIC-G19', async (p) => {
    await expect(heading(p)).toContainText('We are here to help.');
  });

  const routes = page.locator('.ep-grid-cards a');
  await expect(routes).toHaveCount(3);
  await routes.nth(1).click();
  await expect(page).toHaveURL(/\/contact\/$/);
  await clean('/support/');
});

test('PUBLIC-G39 G40 G41 a message from Collaborate reaches support on its topic, answerable by «Reply»', async ({ page }) => {
  const clean = await watch(page);
  rmSync(PUBLIC_MAIL_DIR, { recursive: true, force: true });

  await captureEverywhere(page, '/contact/?subject=collaborate', 'PUBLIC-G39', async (p) => {
    await expect(heading(p)).toContainText('Get in Touch');
    await expect(p.locator('#contact-form input[name="subject"]')).toHaveValue('collaborate');
  });
  // One address, one chat and one reply time (G41).
  await expect(page.getByText('Within 4 business hours', { exact: true })).toBeVisible();
  await expect(page.locator('a[href^="https://wa.me/"]')).toHaveCount(1);
  await expect(page.locator('a[href="mailto:info@erplora.com"]')).toHaveCount(0);

  // From Collaborate, its button opens the form on its topic (G40).
  await page.goto('/collaborate/');
  await page.locator('ion-button[href="/contact/?subject=collaborate"]').first().click();
  await expect(page).toHaveURL(/\/contact\/\?subject=collaborate$/);

  await fill(page, 'first_name', 'Anne');
  await fill(page, 'last_name', 'Garcia');
  await fill(page, 'email', 'anne@example.com');
  await fill(page, 'message', 'We would like to join the programme.');
  await page.locator('#contact-form ion-button[type="submit"]').click();

  await expect(page).toHaveURL(/\/contact\/#contacto$/);
  await expect(page.locator('ion-toast')).toContainText('within 4 business hours');
  const [mail] = mails();
  expect(mail).toContain('Subject: Contact Form [Collaborator program]: Anne Garcia');
  expect(mail).toContain('Reply-To: anne@example.com');
  expect(mail).toContain('We would like to join the programme.');
  await clean('/contact/');
});

test('PUBLIC-G39 a refused message comes back with what was typed', async ({ page }) => {
  const clean = await watch(page);
  rmSync(PUBLIC_MAIL_DIR, { recursive: true, force: true });
  await page.goto('/contact/');

  await fill(page, 'first_name', 'Anne');
  await fill(page, 'last_name', 'Garcia');
  // The browser's check takes it (a dot after the @); the server's does not.
  await fill(page, 'email', 'anne@example..com');
  await fill(page, 'message', 'Please call me back.');
  await page.locator('#contact-form ion-button[type="submit"]').click();

  await expect(page.locator('ion-toast')).toContainText('Enter a valid email address.');
  await expect(page.locator('#contact-form [name="first_name"] input')).toHaveValue('Anne');
  await expect(page.locator('#contact-form [name="email"] input')).toHaveValue('anne@example..com');
  await expect(page.locator('#contact-form [name="message"] textarea')).toHaveValue('Please call me back.');
  expect(mails()).toEqual([]);
  await clean('/contact/ refused');
});

test('PUBLIC-G24 G43 G44 G20 no tracker configured: no notice, only technical cookies, and the choice per group', async ({
  page,
  context,
}) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/legal/cookies/', 'PUBLIC-G43', async (p) => {
    await expect(heading(p)).toBeVisible();
    await expect(p.locator('.cookie-banner, #cookie-banner, [data-cookie-banner]')).toHaveCount(0);
  });
  await page.goto('/');
  const names = (await context.cookies()).map((cookie) => cookie.name).sort();
  expect(names.every((name) => ['csrftoken', 'sessionid', 'django_language', '_lang', 'messages'].includes(name))).toBe(true);

  await captureEverywhere(page, '/cookies/', 'PUBLIC-G44', async (p) => {
    await expect(p.getByText('Manage optional cookies')).toBeVisible();
  });
  await expect(page.getByText('Essential cookies', { exact: true })).toBeVisible();
  await expect(page.getByText('Analytical cookies', { exact: true })).toBeVisible();
  await clean('/cookies/');
});

test('PUBLIC-G45 G17 the legal texts read, each with its own page', async ({ page }) => {
  const clean = await watch(page);
  for (const [path, key] of [
    ['/legal/privacy/', 'PUBLIC-G45-privacy'],
    ['/legal/terms/', 'PUBLIC-G45-terms'],
    ['/legal/legal-notice/', 'PUBLIC-G45-legal-notice'],
  ] as const) {
    await captureEverywhere(page, path, key, async (p) => {
      await expect(heading(p)).toBeVisible();
    });
  }
  await page.goto('/legal/privacy/');
  await expect(page.getByText('Ireland region, eu-west-1', { exact: false }).first()).toBeVisible();
  await clean('legal');
});

test('PUBLIC-G46 the responsible declaration in force, with its archive', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/legal/declaracion-responsable/', 'PUBLIC-G46', async (p) => {
    await expect(heading(p)).toBeVisible();
  });
  await expect(page.locator('a[href*="/legal/declaracion-responsable/v"]').first()).toBeVisible();
  await clean('/legal/declaracion-responsable/');
});

test('PUBLIC-G07 the documentation address leads to the help center', async ({ page }) => {
  const response = await page.goto('/documentation/');

  expect(response?.url()).toMatch(/\/help\/$/);
  await expect(heading(page)).toContainText('Help center.');
});

test('PUBLIC-G26 G10 G11 the store lists the apps by section, filters them and takes the old addresses', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/apps/', 'PUBLIC-G26', async (p) => {
    await expect(p.locator(`a[href="/apps/${APP}/"]`).first()).toBeVisible();
  });
  await page.locator('.ep-store-filters__chip').filter({ hasText: 'Premium' }).click();
  await expect(page).toHaveURL(/premium=1/);
  await page.goto('/apps/?q=zzzz-nothing');
  await expect(page.getByText('No app matches your search.')).toBeVisible();

  for (const old of ['/modules/', '/solutions/', '/marketplace/']) {
    const response = await page.goto(old);
    expect(new URL(response!.url()).pathname, old).toBe('/apps/');
  }
  await clean('/apps/');
});

test('PUBLIC-G27 G08 an app page: overview, required apps and its documentation', async ({ page }) => {
  const clean = await watch(page);

  await captureEverywhere(page, `/apps/${APP}/`, 'PUBLIC-G27', async (p) => {
    await expect(heading(p)).toBeVisible();
    await expect(p.getByText('Required apps')).toBeVisible();
  });
  await captureEverywhere(page, `/apps/${APP}/docs/`, 'PUBLIC-G08', async (p) => {
    await expect(p.locator('.mermaid svg, pre.mermaid').first()).toBeVisible();
  });
  expect((await page.goto('/apps/no-such-app/'))?.status()).toBe(404);
  await clean(`/apps/${APP}/`);
});

test('PUBLIC-G28 G04 G29 the ways to get the app, the Free plan on /download/ and the version published', async ({
  page,
  request,
}) => {
  const clean = await watch(page);

  await captureEverywhere(page, '/download/', 'PUBLIC-G28', async (p) => {
    await expect(heading(p)).toBeVisible();
    // The Free plan seeded by the migrations: 1 device, 3 users.
    await expect(p.getByText('1 device · 3 users')).toBeVisible();
  });
  await expect(page.getByText('3 local users')).toHaveCount(0);

  await captureEverywhere(page, '/app/', 'PUBLIC-G28-app', async (p) => {
    await expect(p.getByText('You need a hub before you need the app.')).toBeVisible();
  });

  expect((await page.goto('/bridge/'))?.status()).toBe(404);
  const release = await request.get('/api/v1/app/release/');
  expect(release.status()).toBe(200);
  expect(Object.keys(await release.json())).toEqual(['version']);
  await clean('/download/ and /app/');
});
