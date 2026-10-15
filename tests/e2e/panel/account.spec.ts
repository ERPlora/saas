// Account (`/account/:tab`, round 17: PLAN-SAAS §3.6 point 1; mockups `account.html`) in Ioan's Chrome, the «Hecho
// L3» flows of docs/plans/2026-10-13-panel-saas-unificado.md that L3-B covers: editing the profile; the theme and
// the language, kept after a reload; the password, changed with the current one; the sessions (a second browser signed in as the same account, «Close other
// sessions» ends it here and asks the Hub to end it in the businesses); an API key created after «Confirm it's you»
// with the password, opening the API once (`X-Api-Key`) and refused after «Revoke»; and the change of the email
// with the code read from the mail. Each tab at the three viewports, without scrolling sideways, leaves a
// screenshot in `$SHOTS_DIR` (or `.artifacts/panel/account/`) to compare with the mockup.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { type APIRequestContext, type Page, request as playwrightRequest } from '@playwright/test';

import {
  djangoPrint,
  expect,
  panelAccount,
  seedPanel,
  shot,
  signIn,
  startHubDouble,
  test,
  VIEWPORTS,
  waitForMail,
  watchPageErrors,
} from './fixtures';
import { PANEL_URL } from './project';

const SHOTS_DIR = process.env.SHOTS_DIR ?? join(shot('account-dir'), '..', 'account');
mkdirSync(SHOTS_DIR, { recursive: true });

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

/** A toast of the shell (`ion-toast`) saying `text`. */
const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });

/** The value of an Ionic field (its native `input` inside). */
const fieldValue = (page: Page, testid: string) => page.getByTestId(testid).locator('input');

/**
 * Makes the sign-in of `request`'s session look older than allauth's window (5 minutes), as if the person had
 * signed in this morning: a command that gives access asks «Confirm it's you» again. Only test data is touched.
 */
async function ageSignIn(request: APIRequestContext): Promise<void> {
  const { cookies } = await request.storageState();
  const key = cookies.find((cookie) => cookie.name === 'sessionid')?.value;
  if (!key) throw new Error('no sessionid cookie (sign in first)');
  const aged = djangoPrint(
    [
      'from importlib import import_module',
      'from django.conf import settings',
      `s=import_module(settings.SESSION_ENGINE).SessionStore(session_key=${JSON.stringify(key)})`,
      'records=s.get("account_authentication_methods", [])',
      'for record in records: record["at"] -= 3600',
      's["account_authentication_methods"]=records',
      's.save()',
      'print(len(records))',
    ].join('\n'),
  );
  expect(Number(aged), 'sign-in records aged').toBeGreaterThan(0);
}

/** What scrolls sideways on the page on screen (Ionic pins `body`: read its `ion-content` and every DataTable). */
async function sidewaysScroll(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(`ion-content ${scroll.scrollWidth} > ${scroll.clientWidth}`);
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
    }
    return found;
  });
}

test('editing the profile keeps the names after a reload', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('one'));
  await page.goto('/account');
  await expect(page).toHaveURL(/\/account\/profile$/);
  await expect(fieldValue(page, 'profile-first-name')).toHaveValue('Laura');
  // `ion-button` keeps `disabled` as a property of its own (Playwright's `toBeDisabled` reads native controls).
  await expect(page.getByTestId('profile-save')).toHaveJSProperty('disabled', true);
  await fieldValue(page, 'profile-first-name').fill('Lucía');
  await page.getByTestId('profile-save').click();
  await expect(toast(page, 'Changes saved')).toBeVisible();
  await page.reload();
  await expect(fieldValue(page, 'profile-first-name')).toHaveValue('Lucía');
  expect(errors).toEqual([]);
});

test('the theme and the language stay after a reload', async ({ page }) => {
  const errors = watchPageErrors(page);
  // An account of its own: the others' specs read English.
  await signIn(page.request, panelAccount('invited'));
  await page.goto('/account/preferences');
  await page.getByTestId('preferences-theme').locator('ion-segment-button', { hasText: 'Dark' }).click();
  await expect(page.locator('html')).toHaveClass(/ion-palette-dark/);
  await expect(toast(page, 'Preferences saved')).toBeVisible();
  await page.getByTestId('preferences-language').click();
  await page.locator('ion-popover ion-radio', { hasText: 'Español' }).click();
  await expect(toast(page, 'Preferencias guardadas')).toBeVisible();
  await expect(page.getByTestId('preferences-appearance')).toContainText('Apariencia');
  await page.reload();
  await expect(page.getByTestId('preferences-appearance')).toContainText('Apariencia');
  await expect(page.locator('html')).toHaveClass(/ion-palette-dark/);
  await expect(page.getByTestId('preferences-theme')).toHaveJSProperty('value', 'dark');
  expect(errors).toEqual([]);
});

test('«Close other sessions» ends the other browser here and in the businesses', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const account = panelAccount('several');
  await signIn(page.request, account);
  const other = await browser.newContext({ baseURL: PANEL_URL });
  const hub = await startHubDouble();
  try {
    await signIn(other.request, account);
    await page.goto('/account/security');
    const rows = page.getByTestId('sessions-row');
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText('This session');
    await page.getByTestId('sessions-close-others').click();
    const dialog = page.getByTestId('sessions-close-others-dialog');
    await expect(dialog).toContainText('1 session will be closed');
    await page.getByTestId('sessions-close-others-dialog-submit').click();
    await expect(toast(page, 'Sessions closed: 1')).toBeVisible();
    await expect(rows).toHaveCount(1);
    const me = await other.request.get('/api/me');
    expect(((await me.json()) as { user: unknown }).user).toBeNull();
    // The Hub is asked to end the account's sessions in its businesses too (PLAN-SAAS §2.1).
    await expect.poll(() => hub.calls.filter((call) => call.path === '/internal/sessions/revoke' && call.signed).length).toBeGreaterThan(0);
  } finally {
    await hub.close();
    await other.close();
  }
  expect(errors).toEqual([]);
});

test('the password changes with the current one, and only the new one signs in after', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const account = panelAccount('free');
  const changed = 'Pan-de-centeno-2026';
  await signIn(page.request, account);
  await page.goto('/account/security');
  await expect(page.getByTestId('sign-in-card')).toContainText('Password');
  await page.getByTestId('password-row-change').click();
  await page.getByTestId('password-current').locator('input').fill('not-the-password');
  await page.getByTestId('password-new').locator('input').fill(changed);
  await expect(page.getByTestId('password-new')).toContainText('Strong.');
  await page.getByTestId('password-change-submit').click();
  // allauth's refusal of a wrong current password, under its field.
  await expect(page.getByTestId('password-current')).toHaveClass(/ion-invalid/);
  await page.getByTestId('password-current').locator('input').fill(account.password);
  await page.getByTestId('password-change-submit').click();
  await expect(toast(page, 'Password changed')).toBeVisible();
  await expect(page.getByTestId('password-change')).toBeHidden();

  const fresh = await browser.newContext({ baseURL: PANEL_URL });
  try {
    await fresh.request.get('/launch');
    const { cookies } = await fresh.request.storageState();
    const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
    const old = await fresh.request.post('/_allauth/browser/v1/auth/login', { headers: { 'X-CSRFToken': csrf }, data: account });
    expect(old.status(), 'the old password no longer signs in').toBe(400);
    await signIn(fresh.request, { email: account.email, password: changed });
  } finally {
    await fresh.close();
  }
  expect(errors).toEqual([]);
});

test('an API key asks «Confirm it’s you», opens the API once and is refused once revoked', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('one'));
  await ageSignIn(page.request);
  await page.goto('/account/api-keys');
  await expect(page.getByTestId('api-keys-empty')).toBeVisible();
  await page.getByTestId('api-keys-empty-new').click();
  await page.getByTestId('new-key-name').locator('input').fill('Gestoría Martínez');
  await page.getByTestId('new-key-scope-hubs.read').click();
  await page.getByTestId('new-key-submit').click();
  // The sign-in is older than 5 minutes: the password again.
  await expect(page.getByTestId('reauth-modal')).toContainText("Confirm it's you");
  await page.screenshot({ path: join(SHOTS_DIR, 'account-api-keys-reauth-1280-light.png') });
  await page.getByTestId('reauth-password').locator('input').fill(panelAccount('one').password);
  await page.getByTestId('reauth-modal-submit').click();
  const secret = (await page.getByTestId('new-key-secret').textContent())?.trim() ?? '';
  expect(secret).toMatch(/^erps_live_[0-9A-Za-z]{48}$/);
  await expect(toast(page, 'Key created: «Gestoría Martínez»')).toBeVisible();
  await page.screenshot({ path: join(SHOTS_DIR, 'account-api-keys-created-1280-light.png') });
  await page.getByTestId('new-key-done').click();
  await expect(page.getByTestId('api-keys-row')).toHaveCount(1);
  await expect(page.getByTestId('api-keys-row').first()).toContainText(secret.slice(0, 14));

  const api = await playwrightRequest.newContext({ baseURL: PANEL_URL });
  try {
    const opened = await api.get('/api/hubs/businesses?limit=50&offset=0', { headers: { 'X-Api-Key': secret } });
    expect(opened.status(), await opened.text()).toBe(200);
    expect(JSON.stringify(await opened.json())).toContain('Panadería López');

    const row = page.getByTestId('api-keys-row').first();
    await row.locator('[data-testid$="-revoke"]').click();
    await expect(page.getByTestId('revoke-key')).toContainText('«Gestoría Martínez»');
    await page.getByTestId('revoke-key-submit').click();
    await expect(toast(page, 'Key revoked: «Gestoría Martínez»')).toBeVisible();
    await expect(page.getByTestId('api-keys-empty')).toBeVisible();

    const refused = await api.get('/api/hubs/businesses?limit=50&offset=0', { headers: { 'X-Api-Key': secret } });
    expect(refused.status()).toBe(401);
    expect(((await refused.json()) as { error: { code: string } }).error.code).toBe('api_key_invalid');
  } finally {
    await api.dispose();
  }
  expect(errors).toEqual([]);
});

test('the email changes with the code mailed to the new address', async ({ page }) => {
  const errors = watchPageErrors(page);
  const next = 'e2e-first-new@example.com';
  await signIn(page.request, panelAccount('first'));
  await page.goto('/account/profile');
  await expect(page.getByTestId('profile-email')).toContainText('e2e-first@example.com');
  await page.getByTestId('profile-email-change').click();
  await page.getByTestId('email-change-address').locator('input').fill(next);
  const since = Date.now();
  await page.getByTestId('email-change-submit').click();
  await expect(page.getByTestId('email-change-sent')).toContainText(next);
  const code = await waitForMail(next, since, /\b\d{6}\b/);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('email-change-submit').click();
  await expect(toast(page, `Your email is now ${next}`)).toBeVisible();
  await expect(page.getByTestId('profile-email')).toContainText(next);
  expect(errors).toEqual([]);
});

test('each tab at the three viewports, light and dark, without scrolling sideways', async ({ browser }) => {
  const signing = await browser.newContext({ baseURL: PANEL_URL });
  await signIn(signing.request, panelAccount('several'));
  const state = await signing.storageState();
  await signing.close();
  const TABS: Array<{ tab: string; ready: (page: Page) => ReturnType<Page['getByTestId']> }> = [
    { tab: 'profile', ready: (p) => p.getByTestId('profile-card') },
    { tab: 'security', ready: (p) => p.getByTestId('sign-in-card') },
    { tab: 'preferences', ready: (p) => p.getByTestId('preferences-appearance') },
    { tab: 'api-keys', ready: (p) => p.getByTestId('api-keys-empty') },
  ];
  for (const theme of ['light', 'dark'] as const) {
    const context = await browser.newContext({ baseURL: PANEL_URL, storageState: state, colorScheme: theme, locale: 'es-ES' });
    try {
      const page = await context.newPage();
      const errors = watchPageErrors(page);
      for (const { width, height } of VIEWPORTS) {
        await page.setViewportSize({ width, height });
        for (const { tab, ready } of TABS) {
          await page.goto(`/account/${tab}`);
          await expect(ready(page)).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          expect(await sidewaysScroll(page), `account-${tab}-${width}-${theme}`).toEqual([]);
          await page.screenshot({ path: join(SHOTS_DIR, `account-${tab}-${width}-${theme}.png`), fullPage: true });
        }
      }
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  }
});
