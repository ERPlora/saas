// flow: ninguno — contexto vivo del panel del SaaS (hermana de hub#190)
// FIX-SAAS-LIVE-ENDED-SESSION-KEEPS-RECEIVING (saas-live-session): a tab of the panel whose session ended stops
// receiving live results and leaves for the sign-in by itself. Two browsers of the same account on Account → Security
// (its live list of open sessions); the second one «Close the other sessions». The first one's next live re-run is the
// stream's end (`bye`, 401 `base.session_ended`, `base/operations.py`), its reopening without a session is a 401 and
// `@erplora/ui` reloads the page (ui#25), which ends at /launch. Before the fix, its list just lost a row and stayed.
// At the three sizes of the migration (390×844, 834×1112, 1440×900). Accounts of this spec: `e2e-liveend-…@example.com`,
// removed before and after.
import { type Browser } from '@playwright/test';

import { VIEWPORTS, djangoPrint, expect, sessionOf, settled, shot, signIn, test, watchPageErrors } from './fixtures';
import { PANEL_URL } from './project';

const PREFIX = 'e2e-liveend-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const KEY = 'FIX-SAAS-LIVE-ENDED-SESSION-KEEPS-RECEIVING';

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
