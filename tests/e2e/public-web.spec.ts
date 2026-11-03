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

import type { Page, Route } from '@playwright/test';

import { djangoEnv } from './django-env';
import { horizontalOverflow } from './horizontal-overflow';
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
    const overflow = await horizontalOverflow(page);
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
    await expect(p.locator('section.hero-bg a.ep-button[href="/launch"]')).toBeVisible();
  });

  await expect(page.locator('section.hero-bg a.ep-button[href="/demo/"]')).toBeVisible();
  await expect(page.locator('section.hero-bg a.ep-button[href="/download/"]')).toBeVisible();
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
  // Every plan includes all the apps (ronda 2026-10-24b, PLAN §32): the home sells no tier of apps.
  await expect(page.locator('#planes .ep-section-sub')).toHaveText(
    'Every plan includes all the apps. Paid plans add unlimited devices, more capacity and higher AI and WhatsApp quotas.',
  );
  await expect(page.locator('#ecosystem')).toContainText('One ecosystem. Every app on every plan.');
  expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/premium|free apps/i);

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
    await expect(p.locator('#more-capacity a.ep-button[href="/launch"]')).toBeVisible();
    // The table gained a column (the apps turned on at once, hub#256): it still fits its surface at every width.
    const spill = await p.locator('#plan-compare').evaluate((table) => table.scrollWidth - (table.parentElement?.clientWidth ?? 0));
    expect(spill, `the plan table spills out of its surface at ${p.viewportSize()?.width}px`).toBeLessThanOrEqual(0);
  });

  // More capacity (PLAN-SAAS §9): Pro, Enterprise and Max from their rows, each saying when it opens instead of a
  // sign-up button, and one call to action to start free.
  const more = page.locator('#more-capacity');
  await expect(more.getByRole('heading', { level: 2 })).toHaveText('More capacity');
  await expect(more.locator('.ep-pricing-card__name')).toHaveText(['Pro', 'Enterprise', 'Max']);
  await expect(more.locator('.ep-pricing-card__amount')).toHaveText(['€109.99', '€209.99', '€419.99']);
  await expect(more.locator('.ep-pricing-card__cta')).toHaveText(Array(3).fill('Available once you are on Starter'));
  await expect(more.locator('.ep-pricing-card [href]')).toHaveCount(0);
  await expect(more.locator('[href]')).toHaveCount(1);
  await expect(more.locator('a.ep-button[href="/launch"]')).toContainText('Start free and upgrade whenever you want');
  const table = page.locator('#plan-compare');
  await expect(table.locator('tbody strong')).toHaveText(['Free', 'Starter', 'Standard', 'Pro', 'Enterprise', 'Max']);
  await expect(table.getByText('Available once you are on Starter')).toHaveCount(3);
  await expect(page.getByText('all your locations', { exact: false })).toHaveCount(0);
  // Every plan includes all the apps (PLAN §32): no tier of apps on the page, no «Apps included» column.
  await expect(page.getByText('Every plan includes all the apps. Paid plans add unlimited devices', { exact: false })).toBeVisible();
  await expect(table.locator('thead th')).toHaveCount(9);
  await expect(table.locator('thead th', { hasText: 'Apps included' })).toHaveCount(0);
  expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/premium/i);

  const starter = page.locator('.ep-pricing-card', { has: page.locator('.ep-pricing-card__name', { hasText: 'Starter' }) });
  await expect(starter).toContainText('€29.99');
  await expect(starter).toContainText('≈ €299.90/year · 2 months free');
  // The apps a business may turn on at once, the cap the Hub applies (hub#256), read from each plan's row: a column
  // next to the devices and users, and a line of every card right after what the plan includes.
  await expect(table.locator('thead th').nth(3)).toHaveText('Apps turned on at once');
  await expect(table.locator('thead th').nth(2)).toHaveText('Devices and users');
  await expect(table.locator('tbody td[data-title="Apps turned on at once"]')).toHaveText(['20', '40', '80', 'Unlimited', 'Unlimited', 'Unlimited']);
  await expect(starter.locator('li')).toContainText(['All apps included', 'Up to 40 apps turned on at once']);
  const pro = more.locator('.ep-pricing-card', { has: page.locator('.ep-pricing-card__name', { hasText: 'Pro' }) });
  await expect(pro.locator('li')).toContainText(['Everything in Standard', 'All the apps turned on at once']);
  await expect(page.getByText('Pay for the year and get 2 months free.')).toBeVisible();
  await page.locator('ion-accordion[value="storage"] ion-item').click();
  const storage = page.locator('ion-accordion[value="storage"] [slot="content"]');
  await expect(storage).toContainText('if its European provider is unavailable');
  // The assistant's voice provider is a transfer too (privacy policy §6): «the one exception» no longer holds.
  await expect(storage).toContainText('transcribing a voice dictation');
  await expect(storage).not.toContainText('The one exception');
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
  await expect(page.getByText('Up to 80 apps turned on at once')).toBeVisible();
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
    await expect(p.locator('a.ep-button[href="/legal/terms/"]', { hasText: 'Read section 7' })).toBeVisible();
  });
  await captureEverywhere(page, '/security/', 'PUBLIC-G50', async (p) => {
    await expect(p.getByText('HTTPS only, with TLS 1.2 or 1.3')).toBeVisible();
  });
  for (const claim of ['TLS 1.3 required', 'security audits', 'pentest']) {
    await expect(page.getByText(claim, { exact: false })).toHaveCount(0);
  }
  await page.locator('a.ep-button', { hasText: 'Contact Security Team' }).click();
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
    ['/', 'section.hero-bg a.ep-button[href="/launch"]'],
    ['/', '#planes a.ep-button[href="/launch"] >> nth=1'],
    ['/pricing/', '.ep-pricing-card a.ep-button[href="/launch"] >> nth=0'],
    ['/pricing/starter/', 'main a.ep-button[href="/launch"] >> nth=0'],
    ['/industries/hair_salon/', 'main a.ep-button[href="/launch"] >> nth=0'],
    ['/features/', 'main a.ep-button[href="/launch"] >> nth=0'],
    ['/compliance/', 'nav a.ep-button[href="/launch"]'],
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

test('PUBLIC-G51 on a slow device, the buttons of the public web lead on even pressed before the page script has run', async ({
  page,
}) => {
  // The page's scripts have not arrived when the person presses (saas#238): held until the end. The stylesheet has,
  // so the page already reads whole and its buttons show.
  const held: Route[] = [];
  await page.route('**/static/spa/**/*.js', (route) => {
    held.push(route);
  });

  // By their address alone: what is under test is that pressing it leads there, whatever the element is.
  const buttons: Array<[string, string, RegExp]> = [
    ['/', 'nav.ep-navbar [href="/launch"]', /\/launch$/],
    ['/', 'nav.ep-navbar [href="/demo/"]', /\/demo\/$/],
    ['/', 'section.hero-bg [href="/launch"]', /\/launch$/],
    ['/', 'section.hero-bg [href="/demo/"]', /\/demo\/$/],
    ['/', 'section.hero-bg [href="/download/"]', /\/download\/$/],
    ['/', '#planes [href="/launch"] >> nth=1', /\/launch$/],
    ['/', '.ep-cta-band [href="/demo/"]', /\/demo\/$/],
    ['/pricing/', '.ep-pricing-card [href="/launch"] >> nth=0', /\/launch$/],
    ['/pricing/', '#more-capacity [href="/launch"]', /\/launch$/],
    ['/pricing/starter/', 'main [href="/launch"] >> nth=0', /\/launch$/],
    ['/pricing/no-such-plan/', 'main [href="/"]', /\/$/],
    ['/industries/', 'main [href="/apps/"]', /\/apps\/$/],
    ['/industries/hair_salon/', 'main [href="/launch"] >> nth=0', /\/launch$/],
    ['/features/', '.ep-cta-band [href="/launch"] >> nth=0', /\/launch$/],
    ['/updates/', '.ep-cta-band [href="/legal/terms/"]', /\/legal\/terms\/$/],
    ['/collaborate/', 'main [href="/contact/?subject=collaborate"] >> nth=0', /\/contact\/\?subject=collaborate$/],
    ['/download/', 'main [href="/launch"]', /\/launch$/],
    ['/app/', 'main [href="/pricing/"]', /\/pricing\/$/],
  ];
  for (const [path, button, destination] of buttons) {
    await page.goto(path, { waitUntil: 'commit' });
    await expect(page.locator(button), `${path} ${button}`).toBeVisible();
    // The control: the page's script has really not run, so nothing but the HTML can lead anywhere.
    expect(await page.evaluate(() => customElements.get('ion-button') === undefined), `${path} ${button}`).toBe(true);

    await page.locator(button).click();
    await expect(page, `${path} ${button}`).toHaveURL(destination);
  }

  // Before the script it already looks like a button, and not like a text link: the stylesheet is enough.
  await page.goto('/', { waitUntil: 'commit' });
  await expect(page.locator('section.hero-bg a.ep-button--large >> nth=0')).toHaveCSS('border-top-left-radius', '16px');
  expect(await page.evaluate(() => customElements.get('ion-button') === undefined)).toBe(true);

  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await Promise.all(held.map((route) => route.continue().catch(() => undefined)));
});

test('PUBLIC-G51 a button that is a real link looks and reacts exactly like an ion-button', async ({ page }) => {
  /** One of each the public web uses: the attributes of the ion-button and the classes of the link it became. */
  const looks = (where: string, variants: Array<[Record<string, string>, string[]]>) => ({ where, variants });
  const scenes = [
    looks('main', [
      [{}, []],
      [{ size: 'small' }, ['ep-button--small']],
      [{ size: 'large' }, ['ep-button--large']],
      [{ fill: 'outline' }, ['ep-button--outline']],
      [{ fill: 'outline', size: 'small' }, ['ep-button--outline', 'ep-button--small']],
      [{ fill: 'outline', size: 'large' }, ['ep-button--outline', 'ep-button--large']],
      [{ fill: 'clear', size: 'small' }, ['ep-button--clear', 'ep-button--small']],
      [{ fill: 'clear', size: 'large' }, ['ep-button--clear', 'ep-button--large']],
      [{ size: 'large', color: 'light' }, ['ep-button--large', 'ep-button--light']],
      [{ expand: 'block' }, ['ep-button--block']],
      [{ expand: 'block', fill: 'outline' }, ['ep-button--block', 'ep-button--outline']],
      [{ expand: 'block', size: 'large' }, ['ep-button--block', 'ep-button--large']],
    ]),
    looks('.ep-cta-band--solid .ep-cta-band__actions', [
      [{ size: 'large', color: 'light' }, ['ep-button--large', 'ep-button--light']],
    ]),
  ];

  /** What a person sees of it, read off the element that paints it: an ion-button's inner link, or the link itself. */
  const seen = (id: string) =>
    page.evaluate((id) => {
      const outer = document.getElementById(id) as HTMLElement;
      const painted = outer.shadowRoot?.querySelector<HTMLElement>('.button-native') ?? outer;
      const box = outer.getBoundingClientRect();
      const host = getComputedStyle(outer);
      const style = getComputedStyle(painted);
      const overlay = getComputedStyle(painted, '::after');
      return {
        width: Math.round(box.width * 2) / 2,
        height: Math.round(box.height * 2) / 2,
        margin: host.margin,
        opacity: host.opacity,
        fontKerning: host.fontKerning,
        background: style.backgroundColor,
        color: style.color,
        border: [style.borderTopWidth, style.borderTopStyle, style.borderTopColor],
        radius: style.borderTopLeftRadius,
        padding: style.padding,
        font: [style.fontSize, style.fontWeight, style.letterSpacing, style.lineHeight, style.textTransform],
        align: style.textAlign,
        underline: style.textDecorationLine,
        cursor: style.cursor,
        overlay: [overlay.backgroundColor, overlay.opacity],
      };
    }, id);

  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForFunction(() => customElements.get('ion-button') !== undefined);
  // On the solid band an outline button turns white: no ion-button is left there to compare it with.
  await expect(page.locator('.ep-cta-band--solid a.ep-button--outline').first()).toHaveCSS('color', 'rgb(255, 255, 255)');
  for (const [scene, { where, variants }] of scenes.entries()) {
    await page.evaluate(
      ({ scene, where, variants }) => {
        const row = document.createElement('div');
        row.style.width = '24rem';
        const icon = (attribute: string, value: string) => {
          const span = document.createElement('span');
          span.setAttribute(attribute, value);
          span.textContent = '>';
          return span;
        };
        variants.forEach(([attributes, classes], index) => {
          const button = document.createElement('ion-button');
          button.id = `parity-${scene}-${index}-button`;
          Object.entries(attributes).forEach(([name, value]) => button.setAttribute(name, value));
          button.setAttribute('href', '#');
          button.style.setProperty('--transition', 'none');
          button.append('Start free', icon('slot', 'end'));
          const link = document.createElement('a');
          link.id = `parity-${scene}-${index}-link`;
          link.className = ['ep-button', ...classes].join(' ');
          link.href = '#';
          link.style.transition = 'none';
          link.append('Start free', icon('class', 'ep-button__end'));
          row.append(button, link);
        });
        document.querySelector(where)?.append(row);
      },
      { scene, where, variants },
    );
    for (const index of variants.keys()) {
      const name = `${where} ${JSON.stringify(variants[index][0])}`;
      const button = `parity-${scene}-${index}-button`;
      const link = `parity-${scene}-${index}-link`;
      await expect(page.locator(`#${button} .button-native`), name).toBeVisible();
      expect(await seen(link), `${name} at rest`).toEqual(await seen(button));

      await page.locator(`#${button}`).hover();
      const hovered = await seen(button);
      await page.locator(`#${link}`).hover();
      expect(await seen(link), `${name} under the pointer`).toEqual(hovered);
    }
  }
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
