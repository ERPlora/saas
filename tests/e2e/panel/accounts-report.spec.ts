// «Report a problem» of the user menu (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-4), at the three sizes of the
// migration (390×844, 834×1112, 1440×900): the person writes «Subject» and «What happened?», the report reaches the
// support mailbox with the account, its business, the page it came from and the browser, «Reply-To» the account, and
// the page says «Report sent». In accounts/WORKBOOK.md: G117 = G01 = F38. Accounts of this spec: `e2e-acc4r-…`.
import { readMails } from '@erplora/ui/testing/mail';
import { type Page } from '@playwright/test';

import { djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test, waitForMail, watchPageErrors } from './fixtures';
import { PANEL_MAIL_DIR } from './project';

const PREFIX = 'e2e-acc4r-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const BUSINESS = 'e2e-acc4r-bar';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

function removeAccounts(): void {
  djangoPrint(
    `from django.contrib.auth import get_user_model\nget_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
  );
}

/** An account in English with its address proven, admin of one business. */
function createAccount(email: string): { email: string; password: string } {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from accounts.models import HubMembership',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="en")`,
      'EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})',
      `HubMembership.objects.create(user=user, hub_slug="${BUSINESS}", role=HubMembership.Role.ADMIN)`,
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

/** The user menu: in the side menu, a drawer behind the topbar's menu button below `lg`. */
async function openUserMenu(page: Page): Promise<void> {
  const trigger = page.getByTestId('user-menu-trigger');
  await expect(trigger).toBeAttached();
  await settled(page);
  if (!(await trigger.isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(trigger).toBeVisible();
  }
  await trigger.click();
  await expect(page.getByTestId('user-menu-report')).toBeVisible();
}

/** Each size: the page as `ready` leaves it, no sideways scroll, and its shot. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-4-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.beforeAll(() => removeAccounts());
test.afterAll(() => removeAccounts());

test('ACCOUNTS-G117 · G01 · report a problem from the user menu: support gets it with the account and its business, «Report sent»', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const support = djangoPrint('from django.conf import settings\nprint(settings.SUPPORT_EMAIL)');
  const me = createAccount(`${PREFIX}owner-${Date.now()}@example.com`);
  await signIn(page.request, me);

  await page.goto('/account/profile');
  await openUserMenu(page);
  await page.getByTestId('user-menu-report').click();
  await expect(page).toHaveURL(/\/report-a-problem$/);
  const send = page.getByTestId('report-send');
  await atEverySize(page, 'ACCOUNTS-G117-form', async () => {
    await expect(page.getByTestId('report-subject')).toBeVisible();
    await expect(send).toBeVisible();
  });

  await page.getByTestId('report-subject').locator('input').fill('The printer stops');
  await expect(send).toHaveAttribute('disabled', '');
  await page.getByTestId('report-description').locator('textarea').fill('I sell a ticket and nothing prints.');
  await expect(send).not.toHaveAttribute('disabled', '');
  const since = Date.now();
  await send.click();

  const sent = page.getByTestId('report-sent');
  await expect(sent).toContainText('Report sent');
  await expect(sent).toContainText(`will reply to ${me.email} as soon as possible`);
  // The text, and under it what goes on its own (Reply-To, a header, is test_support_report.py's).
  expect(await waitForMail(support, since, /(I sell a ticket and nothing prints\.)/)).toBeTruthy();
  const mail = readMails(PANEL_MAIL_DIR).filter((one) => one.to.includes(support.toLowerCase()) && one.body.includes(me.email));
  expect(mail.map((one) => one.subject)).toEqual(['[Support] The printer stops']);
  expect(await waitForMail(support, since, /^Account: (\S+)/m)).toBe(me.email);
  expect(await waitForMail(support, since, /^Businesses: (.+)$/m)).toBe(`${BUSINESS} (hub_admin)`);
  expect(await waitForMail(support, since, /^Page: (.+)$/m)).toBe('/account/profile');
  expect(await waitForMail(support, since, /^Browser: (.+)$/m)).toContain('Mozilla/5.0');
  await atEverySize(page, 'ACCOUNTS-G117-sent', async () => {
    await expect(sent).toBeVisible();
  });

  await page.getByTestId('report-back').click();
  await expect(page).toHaveURL(/\/account\/profile$/);
  expect(errors).toEqual([]);
});
