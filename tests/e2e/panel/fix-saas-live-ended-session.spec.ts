// flow: ninguno — contexto vivo del panel del SaaS (hermana de hub#190)
// flow: ACCOUNTS-F09 — signing out in another tab of the same browser (FIX-SAAS-ACCOUNTS-SIGNOUT-AND-PASSWORD-DO-NOT-WAKE-STREAMS)
// flow: ACCOUNTS-F08 — a new password from another browser (FIX-SAAS-ACCOUNTS-SIGNOUT-AND-PASSWORD-DO-NOT-WAKE-STREAMS)
// FIX-SAAS-LIVE-ENDED-SESSION-KEEPS-RECEIVING (saas-live-session): a tab of the panel whose session ended stops
// receiving live results and leaves for the sign-in by itself. Two browsers of the same account on Account → Security
// (its live list of open sessions); the second one «Close the other sessions». The first one's next live re-run is the
// stream's end (`bye`, 401 `base.session_ended`, `base/operations.py`), its reopening without a session is a 401 and
// `@erplora/ui` reloads the page (ui#25), which ends at /launch. Before the fix, its list just lost a row and stayed.
// At the three sizes of the migration (390×844, 834×1112, 1440×900). Accounts of this spec: `e2e-liveend-…@example.com`,
// removed before and after.
import { type Browser, type Page } from '@playwright/test';

import { VIEWPORTS, djangoPrint, expect, sessionOf, settled, shot, signIn, test, watchPageErrors } from './fixtures';
import { PANEL_URL } from './project';

const PREFIX = 'e2e-liveend-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const KEY = 'FIX-SAAS-LIVE-ENDED-SESSION-KEEPS-RECEIVING';
const WAKE_KEY = 'FIX-SAAS-ACCOUNTS-SIGNOUT-AND-PASSWORD-DO-NOT-WAKE-STREAMS';
const NEW_PASSWORD = 'Pan-de-espelta-y-sal-2026';
/** Account → Security, left for the sign-in that brings it back there. */
const LEFT_FOR_SIGN_IN = /\/launch\?next=(%2F|\/)dashboard(%2F|\/)account(%2F|\/)security$/;

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** An account with its address proven, as one that signed in before. */
function createAccount(name: string): { email: string; password: string } {
  const email = `${PREFIX}${name}-${Date.now()}@example.com`;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

async function newContextOn(browser: Browser, baseURL: string) {
  return browser.newContext({ baseURL, locale: 'en-US' });
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

for (const size of VIEWPORTS) {
  test(`saas-live-session: a tab whose session was closed from another browser stops receiving live results and leaves for the sign-in (${size.width})`, async ({
    page,
    browser,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(String(size.width));
    await page.setViewportSize(size);
    await signIn(page.request, account);
    const other = await newContextOn(browser, PANEL_URL);
    try {
      await signIn(other.request, account);
      await page.goto('/dashboard/account/security');
      const rows = page.getByTestId('sessions-row');
      await expect(rows).toHaveCount(2);
      await expect(rows.first()).toContainText('This session');

      // The other browser closes every session but its own: this tab's among them.
      const otherPage = await other.newPage();
      await otherPage.goto('/dashboard/account/security');
      await expect(otherPage.getByTestId('sessions-row')).toHaveCount(2);
      await otherPage.getByTestId('sessions-close-others').click();
      await otherPage.getByTestId('sessions-close-others-dialog-submit').click();
      await expect(otherPage.getByTestId('sessions-row')).toHaveCount(1);

      // This tab never touched a button: its live list's next run ends its stream and the page leaves for the sign-in.
      await expect(page).toHaveURL(/\/launch\?next=(%2F|\/)dashboard(%2F|\/)account(%2F|\/)security$/);
      await expect(page.getByTestId('sessions-row')).toHaveCount(0);
      expect((await sessionOf(page.request)).user).toBeNull();
      expect((await sessionOf(other.request)).user).toMatchObject({ label: account.email });
      await settled(page);
      await page.screenshot({ path: shot(`${KEY}-${size.width}`), fullPage: true });
    } finally {
      await other.close();
    }
    expect(errors).toEqual([]);
  });
}

/** The user menu's «Sign out» (`UserMenuPopover`): in the side menu, a drawer behind the topbar's menu button below `lg`. */
async function signOutFromUserMenu(page: Page): Promise<void> {
  const trigger = page.getByTestId('user-menu-trigger');
  await expect(trigger).toBeAttached();
  await settled(page);
  if (!(await trigger.isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(trigger).toBeVisible();
  }
  await trigger.click();
  await page.getByTestId('user-menu-logout').click();
}

// FIX-SAAS-ACCOUNTS-SIGNOUT-AND-PASSWORD-DO-NOT-WAKE-STREAMS: signing out (allauth.headless `DELETE auth/session`) and a
// new password (`account/password/change`) record `accounts.session.closed` on the account's channel, as «Close the other
// sessions» does: the tabs whose session ended leave for the sign-in by themselves, without reloading and without waiting
// for another event. Before the fix the outbox stayed empty and the tab stayed on screen with what it last saw.
for (const size of VIEWPORTS) {
  test(`ACCOUNTS-F09: signing out in another tab of the same browser takes this tab to the sign-in, and the other browser's list loses that session (${size.width})`, async ({
    page,
    browser,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(`${size.width}-signout`);
    await page.setViewportSize(size);
    await signIn(page.request, account);
    const other = await newContextOn(browser, PANEL_URL);
    try {
      await signIn(other.request, account);
      await page.goto('/dashboard/account/security');
      await expect(page.getByTestId('sessions-row')).toHaveCount(2);
      const otherPage = await other.newPage();
      await otherPage.goto('/dashboard/account/security');
      await expect(otherPage.getByTestId('sessions-row')).toHaveCount(2);

      // A second tab of this browser (the same session) signs out from the user menu.
      const tab = await page.context().newPage();
      await tab.setViewportSize(size);
      await tab.goto('/dashboard/account/security');
      await expect(tab.getByTestId('sessions-row')).toHaveCount(2);
      await signOutFromUserMenu(tab);
      await expect(tab).toHaveURL(/\/launch/);

      // This tab never touched a button: the sign-out wakes its live list, whose run ends the stream.
      await expect(page).toHaveURL(LEFT_FOR_SIGN_IN);
      await expect(page.getByTestId('sessions-row')).toHaveCount(0);
      expect((await sessionOf(page.request)).user).toBeNull();
      // The other browser stays in, and its live list drops the session that ended, without reloading.
      await expect(otherPage.getByTestId('sessions-row')).toHaveCount(1);
      expect((await sessionOf(other.request)).user).toMatchObject({ label: account.email });
      await settled(page);
      await page.screenshot({ path: shot(`${WAKE_KEY}-signout-${size.width}`), fullPage: true });
    } finally {
      await other.close();
    }
    expect(errors).toEqual([]);
  });

  test(`ACCOUNTS-F08: a new password from another browser takes this tab to the sign-in, and that browser stays in (${size.width})`, async ({
    page,
    browser,
  }) => {
    const errors = watchPageErrors(page);
    const account = createAccount(`${size.width}-password`);
    await page.setViewportSize(size);
    await signIn(page.request, account);
    const other = await newContextOn(browser, PANEL_URL);
    try {
      await signIn(other.request, account);
      await page.goto('/dashboard/account/security');
      await expect(page.getByTestId('sessions-row')).toHaveCount(2);

      // The other browser changes the password on Account → Security.
      const otherPage = await other.newPage();
      await otherPage.setViewportSize(size);
      await otherPage.goto('/dashboard/account/security');
      await otherPage.getByTestId('password-row-change').click();
      await otherPage.getByTestId('password-current').locator('input').fill(account.password);
      await otherPage.getByTestId('password-new').locator('input').fill(NEW_PASSWORD);
      await otherPage.getByTestId('password-change-submit').click();
      await expect(otherPage.getByTestId('password-change')).toBeHidden();

      // This tab's session was opened with the old password: the change wakes its live list, whose run ends the stream.
      await expect(page).toHaveURL(LEFT_FOR_SIGN_IN);
      await expect(page.getByTestId('sessions-row')).toHaveCount(0);
      expect((await sessionOf(page.request)).user).toBeNull();
      await expect(otherPage.getByTestId('sessions-row')).toHaveCount(1);
      expect((await sessionOf(other.request)).user).toMatchObject({ label: account.email });
      await settled(page);
      await page.screenshot({ path: shot(`${WAKE_KEY}-${size.width}`), fullPage: true });
    } finally {
      await other.close();
    }
    expect(errors).toEqual([]);
  });
}
