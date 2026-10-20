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
  settled,
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

// flow: ninguno — FIX accounts
test('opening the profile with no first name says nothing; leaving the empty field says it', async ({ page }) => {
  const errors = watchPageErrors(page);
  // e2e-jorge: the seeded account with no names yet. Nothing is saved: the account stays as seeded.
  await signIn(page.request, panelAccount('jorge'));
  const first = page.getByTestId('profile-first-name');
  const said = first.locator('.error-text');
  for (const { width, height } of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.goto('/account/profile');
    await expect(fieldValue(page, 'profile-first-name')).toHaveValue('');
    await expect(first).not.toHaveClass(/ion-invalid/);
    await expect(said).toBeHidden();
    await expect(page.getByTestId('profile-save')).toHaveJSProperty('disabled', true);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: shot(`FIX-SAAS-ACCOUNT-NAME-ERROR-${width}`), fullPage: true });
  }
  await fieldValue(page, 'profile-first-name').focus();
  await expect(said).toBeHidden();
  await fieldValue(page, 'profile-first-name').blur();
  await expect(first).toHaveClass(/ion-invalid/);
  await expect(said).toHaveText('Write your first name.');
  await page.screenshot({ path: shot('FIX-SAAS-ACCOUNT-NAME-ERROR-left-1440'), fullPage: true });
  await fieldValue(page, 'profile-first-name').fill('Jorge');
  await expect(said).toBeHidden();
  expect(errors).toEqual([]);
});

// flow: ninguno — FIX accounts
test('changing only the last name with no first name says why «Save changes» stays off', async ({ page }) => {
  const errors = watchPageErrors(page);
  // e2e-jorge: no names yet. Nothing is saved: the account stays as seeded.
  await signIn(page.request, panelAccount('jorge'));
  await page.setViewportSize(VIEWPORTS[0]);
  await page.goto('/account/profile');
  const first = page.getByTestId('profile-first-name');
  await expect(first).not.toHaveClass(/ion-invalid/);
  await fieldValue(page, 'profile-last-name').fill('Gómez');
  await expect(first).toHaveClass(/ion-invalid/);
  await expect(first.locator('.error-text')).toHaveText('Write your first name.');
  await expect(page.getByTestId('profile-save')).toHaveJSProperty('disabled', true);
  await page.evaluate(() => document.fonts.ready);
  // The last name's floating label is still rising after the typing.
  await page.waitForTimeout(300);
  await page.screenshot({ path: shot(`FIX-SAAS-ACCOUNT-NAME-ERROR-last-name-${VIEWPORTS[0].width}`), fullPage: true });
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

/** Sessions of the e2e's sign-ins: more than one live result of the whole list carried (256 KiB, ~1,300 rows). */
const MANY_SESSIONS = 1800;

/** `count` more sessions that still sign `email` in, used a minute apart before now, as as many sign-ins elsewhere. */
function moreSessions(email: string, count: number): number {
  const made = djangoPrint(
    [
      'from datetime import timedelta',
      'from importlib import import_module',
      'from allauth.usersessions.models import UserSession',
      'from django.conf import settings',
      'from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model',
      'from django.utils import timezone',
      'from django.utils.crypto import get_random_string',
      `user = get_user_model().objects.get(email=${JSON.stringify(email)})`,
      'store = import_module(settings.SESSION_ENGINE).SessionStore',
      'model = store.get_model_class()',
      'data = store().encode({SESSION_KEY: str(user.pk), BACKEND_SESSION_KEY: settings.AUTHENTICATION_BACKENDS[0], HASH_SESSION_KEY: user.get_session_auth_hash()})',
      'now = timezone.now()',
      `keys = [get_random_string(32, "abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(${count})]`,
      'model.objects.bulk_create(model(session_key=k, session_data=data, expire_date=now + timedelta(days=1)) for k in keys)',
      'ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"',
      'UserSession.objects.bulk_create(UserSession(user=user, session_key=k, ip="81.33.10.4", user_agent=ua, last_seen_at=now - timedelta(minutes=n + 1)) for n, k in enumerate(keys))',
      'print(len(keys))',
    ].join('\n'),
  );
  return Number(made);
}

// flow: ninguno — FIX accounts (FIX-SAAS-SESSIONS-RESULT-TOO-BIG): the list said «The result exceeds 262144 bytes».
test('with more sessions than a page, «Active sessions» loads, this one first, and pages', async ({ page }) => {
  const errors = watchPageErrors(page);
  const account = panelAccount('carlos');
  await signIn(page.request, account);
  expect(moreSessions(account.email, MANY_SESSIONS)).toBe(MANY_SESSIONS);
  const rows = page.getByTestId('sessions-row');
  const pager = page.locator('.data-table__pager');
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/account/security');
    await expect(rows).toHaveCount(25);
    await expect(rows.first()).toContainText('This session');
    await expect(pager).toContainText('Showing 1–25 of');
    await expect(pager).toContainText(/1,?801 sessions/);
    await expect(page.getByTestId('sessions-retry')).toHaveCount(0);
    await settled(page);
    await page.screenshot({ path: shot(`FIX-SAAS-SESSIONS-RESULT-TOO-BIG-${viewport.width}`) });
    if (viewport.width < 640) {
      // More sessions than one page of the server holds (100): the phone pages too, never a «Load more» that
      // brings nothing, and every session stays reachable — here past the 100th.
      await expect(page.getByTestId('sessions-load-more')).toHaveCount(0);
      await expect(pager.locator('.data-table__page-of')).toHaveText('1 / 73');
      for (let n = 0; n < 4; n += 1) await page.getByTestId('sessions-page-next').click();
      await expect(pager).toContainText('Showing 101–125 of');
      await expect(pager.locator('.data-table__page-of')).toHaveText('5 / 73');
      await expect(rows).toHaveCount(25);
      await expect(rows.filter({ hasText: 'This session' })).toHaveCount(0);
      await settled(page);
      await page.screenshot({ path: shot(`FIX-SAAS-SESSIONS-RESULT-TOO-BIG-${viewport.width}-page-5`) });
      await page.getByTestId('sessions-page-prev').click();
      await expect(pager).toContainText('Showing 76–100 of');
    } else {
      await page.getByTestId('sessions-page-next').click();
      await expect(pager).toContainText('Showing 26–50 of');
      await expect(rows).toHaveCount(25);
      await expect(rows.filter({ hasText: 'This session' })).toHaveCount(0);
    }
  }
  // From the second page, «Close other sessions» counts every page's and ends them; the list steps back to this one.
  await page.getByTestId('sessions-close-others').click();
  await expect(page.getByTestId('sessions-close-others-dialog')).toContainText(/1,?800 sessions will be closed/);
  await page.getByTestId('sessions-close-others-dialog-submit').click();
  await expect(toast(page, /Sessions closed: 1,?800/)).toBeVisible({ timeout: 30_000 });
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('This session');
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
