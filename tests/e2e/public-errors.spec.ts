// The error pages of erplora.com (accounts/WORKBOOK.md, ACCOUNTS-G30 · G81; MIGRATION-TASK APP-ACCOUNTS-5), at the
// three sizes of the migration (390×844, 834×1112, 1440×900), in English and in Spanish, against the production-like
// server of this project (DEBUG off: Django renders the project's handlers, never its debug pages):
//   - an unknown page of the public web: its own 404, with the navbar and a way home;
//   - an unknown page of the private half (`/accounts/…`): the error layout's 404, «Home» and «Contact Support»;
//   - the 500 pages: no route fails on purpose, so each one is rendered by Django exactly as its handler renders it
//     (`public.errors`, tested in base/tests/test_error_pages.py and public/tests/test_errors.py) and served to the
//     browser under this origin, which loads its own styles: what is checked here is how it paints.
// The screenshots stay in `.artifacts/errors/`.
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page, expect, test } from '@playwright/test';

import { djangoEnv } from './django-env';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
const ARTIFACTS = join(HERE, '.artifacts', 'errors');
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const LANGUAGES = [
  { code: 'en', locale: 'en-GB' },
  { code: 'es', locale: 'es-ES' },
] as const;

/**
 * The 500 page of `side` as Django answers a view that fails, in `language`: the project's `handler500` through the
 * whole middleware (CSP nonce included), on a URLconf of its own that adds one failing route to the project's, under
 * the public web's namespace (`public`) or outside it.
 */
function rendered500(side: 'private' | 'public', language: string): string {
  const code = [
    'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()',
    'from django.test import Client, override_settings',
    'from django.urls import include, path',
    'import config.urls as project',
    'def fails(request):',
    '    raise RuntimeError("the 500 page of the e2e")',
    side === 'public'
      ? 'urlpatterns = [path("", include(([path("pricing/fails/", fails)], "public"))), *project.urlpatterns]'
      : 'urlpatterns = [path("accounts/fails/", fails), *project.urlpatterns]',
    'handler404, handler500 = project.handler404, project.handler500',
    'with override_settings(ROOT_URLCONF="__main__", ALLOWED_HOSTS=["localhost"]):',
    `    answer = Client(raise_request_exception=False).get("/${side === 'public' ? 'pricing' : 'accounts'}/fails/", HTTP_HOST="localhost", HTTP_ACCEPT_LANGUAGE="${language}")`,
    'assert answer.status_code == 500, answer.status_code',
    'print(answer.content.decode())',
  ].join('\n');
  return execFileSync('uv', ['run', 'python', '-c', code], {
    cwd: SAAS_DIR,
    env: { ...djangoEnv(true), DEBUG: 'False', SECRET_KEY: 'e2e-only-500-page', INTERNAL_SHARED_SECRET: 'e2e-only', FISCAL_DOCUMENTS_KEY: '2EBDB2KSnvz5lBG1RHG5ldNq34ZjWvGZ_t5r4wl5Mpw=', GOOGLE_OAUTH_CLIENT_ID: 'e2e', GOOGLE_OAUTH_CLIENT_SECRET: 'e2e' },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

async function sidewaysScroll(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

async function atEverySize(page: Page, key: string, check: () => Promise<void>): Promise<void> {
  mkdirSync(ARTIFACTS, { recursive: true });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await check();
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(ARTIFACTS, `APP-ACCOUNTS-5-${key}-${size.name}.png`), fullPage: true });
  }
}

const TEXTS = {
  en: {
    publicNotFound: 'Page not found',
    privateNotFound: "We couldn't find this page",
    publicError: 'Something went wrong',
    privateError: 'Something went wrong on our end',
    home: 'Home',
    support: 'Contact Support',
  },
  es: {
    publicNotFound: 'Página no encontrada',
    privateNotFound: 'No hemos podido encontrar esta página',
    publicError: 'Algo ha fallado',
    privateError: 'Algo ha ido mal por nuestra parte',
    home: 'Inicio',
    support: 'Contactar Soporte',
  },
} as const;

for (const { code, locale } of LANGUAGES) {
  test.describe(`in ${code}`, () => {
    test.use({ locale, extraHTTPHeaders: { 'Accept-Language': locale } });

    test(`ACCOUNTS-G81 · an unknown page of the public web is its 404, with a way home (${code})`, async ({ page }) => {
      const answer = await page.goto('/pricing/no-such-plan/');
      expect(answer?.status()).toBe(404);
      await atEverySize(page, `ACCOUNTS-G81-public-404-${code}`, async () => {
        await expect(page.locator('body')).toContainText(TEXTS[code].publicNotFound);
        await expect(page.locator('a[href="/"]').first()).toBeAttached();
      });
    });

    test(`ACCOUNTS-G30 · G81 · an unknown page of the private half is the error layout's 404 (${code})`, async ({ page }) => {
      const answer = await page.goto('/accounts/no-such-page/');
      expect(answer?.status()).toBe(404);
      await atEverySize(page, `ACCOUNTS-G81-private-404-${code}`, async () => {
        await expect(page.locator('h1')).toHaveText(TEXTS[code].privateNotFound);
        await expect(page.getByRole('link', { name: TEXTS[code].home })).toBeVisible();
        await expect(page.getByRole('link', { name: TEXTS[code].support })).toBeVisible();
      });
    });

    for (const side of ['private', 'public'] as const) {
      test(`ACCOUNTS-G81 · the ${side} 500 page paints at every size (${code})`, async ({ page }) => {
        const html = rendered500(side, code);
        await page.route('**/__the-500-page__', (route) =>
          route.fulfill({ status: 500, contentType: 'text/html; charset=utf-8', body: html }),
        );
        const answer = await page.goto('/__the-500-page__');
        expect(answer?.status()).toBe(500);
        const key = `ACCOUNTS-G81-${side}-500-${code}`;
        await atEverySize(page, key, async () => {
          await expect(page.locator('body')).toContainText(
            side === 'private' ? TEXTS[code].privateError : TEXTS[code].publicError,
          );
          // Its own styles load from this origin: the page is laid out, not raw HTML.
          const styled = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
          expect(styled).not.toBe('');
        });
      });
    }
  });
}
