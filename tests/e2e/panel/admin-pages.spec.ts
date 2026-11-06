// The admin pages of our own in erplora.com's admin wear Django 6.1's breadcrumbs (MIGRATION-TASK APP-ASSISTANT-1):
// «Hubs» and the API key just issued (accounts), the review of a signed authorisation and ERPlora's stamp as
// representative (fiscal), at the three sizes of the migration (390×844, 834×1112, 1440×900), in English and in
// Spanish. They kept the older `<div class="breadcrumbs">`, which Django 6.1 no longer styles: a bare line of links
// above the title. config/tests/test_admin_templates.py keeps the markup of every page of our own; this spec looks at
// the four on screen. Rows: fiscal_seed.py (a business with its member and a signed authorisation) and the accounts
// of this spec, `e2e-admpages-…@example.com`.
// The admin's index too: each section with a name of its own (allauth's `account` and our `accounts` were both
// «Accounts»/«Cuentas») and every one of them in Spanish (Cookie consent, the authenticators, the sessions and live's
// outbox kept their English); config/tests/test_admin_index.py walks them all.
// flow: ACCOUNTS-F31 — the key just issued, shown once.
// flow: FISCAL-F03 — the review page of a signed authorisation.
// flow: FISCAL-F06 — ERPlora's stamp as representative.
import type { Page } from '@playwright/test';

import { captureAtEverySize, djangoPrint, expect, MAILING, runSeed, signIn, test, watchPageErrors } from './fixtures';

const atEverySize = captureAtEverySize('APP-ASSISTANT-1');

const PREFIX = 'e2e-admpages-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const ROOT = { email: `${PREFIX}root@example.com`, password: PASSWORD };
const TEAMMATE = `${PREFIX}qa@example.com`;

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
  // `fiscal_seed.py seed` files the authorisation and prints its id.
  grant = runSeed('fiscal_seed.py', 'seed', MAILING);
  expect(grant).toMatch(/^[0-9a-f-]{36}$/);
  createAccounts();
});

test.afterAll(() => {
  runSeed('fiscal_seed.py', 'clear', MAILING);
  removeAccounts();
});

/**
 * At each size: the page's breadcrumbs are Django 6.1's list (from «Home» to the page itself, `count` crumbs, the last
 * one the current page and no link), painted on the admin's band (a bare line of links has no background), on one line
 * at 1440; no sideways scroll; a capture `APP-ASSISTANT-1-<key>-<size>`. Back at 1440 after.
 */
async function crumbsAtEverySize(page: Page, key: string, home: string, current: string, count: number): Promise<void> {
  const crumbs = page.locator('nav[aria-label] ol.breadcrumbs > li');
  await atEverySize(page, key, async (size) => {
    await expect(page.locator('div.breadcrumbs')).toHaveCount(0);
    await expect(crumbs).toHaveCount(count);
    await expect(crumbs.first()).toHaveText(home);
    await expect(crumbs.last()).toHaveText(current);
    await expect(crumbs.last()).toHaveAttribute('aria-current', 'page');
    await expect(crumbs.last().locator('a')).toHaveCount(0);
    await expect(page.locator('ol.breadcrumbs')).not.toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    if (size.width === 1440) {
      const tops = await crumbs.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)));
      expect(new Set(tops).size, `${key}: the crumbs on one line`).toBe(1);
    }
  });
}

type IndexNames = Record<
  'emails' | 'accounts' | 'consent' | 'groups' | 'records' | 'authenticators' | 'sessions' | 'live' | 'outbox',
  string
>;

/**
 * The admin's index at each size: no two sections share a name, the four that did or spoke English say `names`, no
 * sideways scroll, a capture `APP-ASSISTANT-1-admin-index<suffix>-<size>`. Back at 1440 after.
 */
async function indexAtEverySize(page: Page, names: IndexNames, suffix: string): Promise<void> {
  const errors = watchPageErrors(page);
  await signIn(page.request, ROOT);
  await page.goto('/admin/');
  const main = page.locator('#content-main');
  await atEverySize(page, `admin-index${suffix}`, async () => {
    const sections = (await main.locator('caption a.section').allTextContents()).map((name) => name.trim());
    expect(sections.length).toBeGreaterThan(10);
    expect(sections.filter((name, at) => sections.indexOf(name) !== at), 'sections sharing a name').toEqual([]);
    await expect(main.locator('.app-account caption')).toHaveText(names.emails);
    await expect(main.locator('.app-accounts caption')).toHaveText(names.accounts);
    await expect(main.locator('.app-cookie_consent caption')).toHaveText(names.consent);
    await expect(main.locator('.app-cookie_consent .model-cookiegroup th')).toHaveText(names.groups);
    await expect(main.locator('.app-cookie_consent .model-logitem th')).toHaveText(names.records);
    await expect(main.locator('.app-mfa .model-authenticator th')).toHaveText(names.authenticators);
    await expect(main.locator('.app-usersessions .model-usersession th')).toHaveText(names.sessions);
    await expect(main.locator('.app-live caption')).toHaveText(names.live);
    await expect(main.locator('.app-live .model-outboxevent th')).toHaveText(names.outbox);
  });
  expect(errors).toEqual([]);
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

test('the admin\'s index names each section once', async ({ page }) => {
  await indexAtEverySize(
    page,
    {
      emails: 'Email addresses',
      accounts: 'Accounts',
      // The package's own English, untouched; its Spanish is ours (public's catalog).
      consent: 'cookie consent',
      groups: 'Cookie Groups',
      records: 'Log items',
      authenticators: 'Authenticators',
      sessions: 'User sessions',
      live: 'Live',
      outbox: 'Outbox events',
    },
    '',
  );
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('the admin\'s index names each section once, in Spanish', async ({ page }) => {
    await indexAtEverySize(
      page,
      {
        emails: 'Direcciones de correo electrónico',
        accounts: 'Cuentas',
        consent: 'Consentimiento de cookies',
        groups: 'Grupos de cookies',
        records: 'Registros de consentimiento',
        authenticators: 'Autenticadores',
        sessions: 'Sesiones de usuario',
        live: 'Tiempo real',
        outbox: 'Eventos de la bandeja de salida',
      },
      '-es',
    );
  });

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
