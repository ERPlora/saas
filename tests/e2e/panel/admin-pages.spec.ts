// The admin pages of our own in erplora.com's admin wear Django 6.1's breadcrumbs (MIGRATION-TASK APP-ASSISTANT-1):
// «Hubs» and the API key just issued (accounts), the review of a signed authorisation and ERPlora's stamp as
// representative (fiscal), at the three sizes of the migration (390×844, 834×1112, 1440×900), in English and in
// Spanish. They kept the older `<div class="breadcrumbs">`, which Django 6.1 no longer styles: a bare line of links
// above the title. config/tests/test_admin_templates.py keeps the markup of every page of our own; this spec looks at
// the four on screen. Rows: fiscal_seed.py (a business with its member and a signed authorisation) and the accounts
// of this spec, `e2e-admpages-…@example.com`.
// flow: ACCOUNTS-F31 — the key just issued, shown once.
// flow: FISCAL-F03 — the review page of a signed authorisation.
// flow: FISCAL-F06 — ERPlora's stamp as representative.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';
import { PANEL_MAIL_DIR } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PREFIX = 'e2e-admpages-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const ROOT = { email: `${PREFIX}root@example.com`, password: PASSWORD };
const TEAMMATE = `${PREFIX}qa@example.com`;
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

/** `fiscal_seed.py seed|clear`; `seed` files the authorisation and prints its id. */
function fiscalSeed(action: 'seed' | 'clear'): string {
  return execFileSync('uv', ['run', 'python', 'tests/e2e/panel/fiscal_seed.py', action], {
    cwd: SAAS_DIR,
    env: { ...djangoEnv(true), EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend', EMAIL_FILE_PATH: PANEL_MAIL_DIR },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
    .trim()
    .split('\n')
    .at(-1) as string;
}

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** A superuser who opens every page, and a team account of support to own the key it issues. */
function createAccounts(): void {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from accounts import services',
      `for email, group in (("${ROOT.email}", services.PLATFORM_ADMIN), ("${TEAMMATE}", services.PLATFORM_SUPPORT)):`,
      `    user = services.create_platform_user(email, group, "${PASSWORD}")[0]`,
      '    user.language = "en"; user.save(update_fields=["language"])',
      '    EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})',
    ].join('\n'),
  );
}

let grant = '';

test.beforeAll(() => {
  removeAccounts();
  grant = fiscalSeed('seed');
  expect(grant).toMatch(/^[0-9a-f-]{36}$/);
  createAccounts();
});

test.afterAll(() => {
  fiscalSeed('clear');
  removeAccounts();
});

/**
 * At each size: the page's breadcrumbs are Django 6.1's list (from «Home» to the page itself, `count` crumbs, the last
 * one the current page and no link), painted on the admin's band (a bare line of links has no background), on one line
 * at 1440; no sideways scroll; a capture `APP-ASSISTANT-1-<key>-<size>`. Back at 1440 after.
 */
async function crumbsAtEverySize(page: Page, key: string, home: string, current: string, count: number): Promise<void> {
  const crumbs = page.locator('nav[aria-label] ol.breadcrumbs > li');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(page.locator('div.breadcrumbs')).toHaveCount(0);
    await expect(crumbs).toHaveCount(count);
    await expect(crumbs.first()).toHaveText(home);
    await expect(crumbs.last()).toHaveText(current);
    await expect(crumbs.last()).toHaveAttribute('aria-current', 'page');
    await expect(crumbs.last().locator('a')).toHaveCount(0);
    await expect(page.locator('ol.breadcrumbs')).not.toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    if (size.name === '1440') {
      const tops = await crumbs.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)));
      expect(new Set(tops).size, `${key}: the crumbs on one line`).toBe(1);
    }
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ASSISTANT-1-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The four pages, each with its own crumbs, in the language the browser asks for. */
async function visitTheFourPages(page: Page, words: Record<'home' | 'hubs' | 'issued' | 'review' | 'stamp', string>, suffix: string) {
  const errors = watchPageErrors(page);
  await signIn(page.request, ROOT);

  await page.goto('/admin/accounts/hubs/');
  await expect(page.locator('#content-main table tbody tr').first()).toBeVisible();
  await crumbsAtEverySize(page, `admin-hubs${suffix}`, words.home, words.hubs, 3);

  await page.goto('/admin/accounts/apikey/add/');
  const form = page.locator('#apikey_form');
  await form.locator('select[name="user"]').selectOption({ label: TEAMMATE });
  await form.locator('input[name="name"]').fill(`Admin pages${suffix}`);
  await form.locator('input[name="scopes"][value="hubs.read"]').check();
  await form.locator('select[name="expires_in_days"]').selectOption('30');
  await form.locator('input[name="_save"]').click();
  await expect(page.locator('[data-api-key-secret]')).toBeVisible();
  await crumbsAtEverySize(page, `ACCOUNTS-F31-issued${suffix}`, words.home, words.issued, 4);

  await page.goto(`/admin/fiscal/representationgrant/${grant}/review/`);
  await crumbsAtEverySize(page, `FISCAL-F03-review${suffix}`, words.home, words.review, 5);

  await page.goto('/admin/fiscal/representationgrant/stamp/');
  await crumbsAtEverySize(page, `FISCAL-F06-stamp${suffix}`, words.home, words.stamp, 4);
  expect(errors).toEqual([]);
}

test('ACCOUNTS-F31 · FISCAL-F03 · FISCAL-F06: the admin pages of our own wear the admin\'s breadcrumbs', async ({ page }) => {
  await visitTheFourPages(
    page,
    { home: 'Home', hubs: 'Hubs', issued: 'API key issued', review: 'Review', stamp: "Representative's stamp" },
    '',
  );
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('ACCOUNTS-F31 · FISCAL-F03 · FISCAL-F06: the admin pages of our own wear the admin\'s breadcrumbs in Spanish', async ({
    page,
  }) => {
    await visitTheFourPages(
      page,
      { home: 'Inicio', hubs: 'Hubs', issued: 'Clave de API emitida', review: 'Revisar', stamp: 'Sello del representante' },
      '-es',
    );
  });
});
