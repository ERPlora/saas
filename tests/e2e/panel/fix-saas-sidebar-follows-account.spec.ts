// saas#292: the side menu comes translated by the server (`base.session.me`), so after choosing a language in
// Account → Preferences it kept the old one until a reload (ACCOUNTS-F22 step 3: «el panel cambia de idioma al
// momento»). Saving the language now reads the session again: the menu speaks the new one at once, there and back, in
// the pinned menu (1440 px) and in the drawer (390 and 834 px), on the same page. The name saved in Account → Profile
// reaches the top of the menu the same way (ACCOUNTS-F21).
import { type Page } from '@playwright/test';

import {
  closeMenu,
  djangoPrintWarm,
  expect,
  openMenu,
  provenAccount,
  removeAccountsOf,
  settled,
  shot,
  signIn,
  test,
  toast,
  VIEWPORTS,
  warmDjango,
  watchPageErrors,
} from './fixtures';

const PREFIX = 'e2e-fix292-';
const ACCOUNT = { email: `${PREFIX}menu@example.com`, password: 'e2e-fix292-password' };
/** The panel's menu on the web, as `base/navigation.py` names it in each language. */
const MENU = { en: ['Businesses', 'Store', 'Billing', 'Account'], es: ['Negocios', 'Tienda', 'Facturación', 'Cuenta'] };
/** Each switch: the option of «Language» and the toast that says it was saved, in the language chosen. */
const SWITCHES = [
  { lang: 'es', option: 'Español', saved: 'Preferencias guardadas' },
  { lang: 'en', option: 'English', saved: 'Preferences saved' },
] as const;

test.beforeAll(async () => {
  removeAccountsOf(PREFIX);
  provenAccount(ACCOUNT.email, ACCOUNT.password, 'en');
  // The beforeEach below asks this worker's warm Django: its boot here, on no test's clock.
  await warmDjango();
});
test.afterAll(() => removeAccountsOf(PREFIX));

/** Every run starts from an account speaking English, whatever a failed one left. */
test.beforeEach(async () => {
  await djangoPrintWarm(
    `from django.contrib.auth import get_user_model\nget_user_model().objects.filter(email=${JSON.stringify(ACCOUNT.email)}).update(language="en", first_name="", last_name="")`,
  );
});

/** Marks the page, so a spec can tell it was never reloaded (a reload starts a fresh window). */
const markPage = (page: Page) => page.evaluate(() => Object.assign(window, { fix292SamePage: true }));
const samePage = (page: Page) => page.evaluate(() => (window as Window & { fix292SamePage?: boolean }).fix292SamePage === true);

for (const size of VIEWPORTS) {
  test(`ACCOUNTS-F22 · the side menu speaks the language just chosen in Preferences, there and back, with no reload, at ${size.width} px`, async ({
    page,
  }) => {
    const errors = watchPageErrors(page);
    await page.setViewportSize(size);
    await signIn(page.request, ACCOUNT);
    await page.goto('/dashboard/account/preferences');
    await expect(page.getByTestId('preferences-language-card')).toBeVisible();
    await markPage(page);
    const menu = page.locator('ion-menu .nav-item');
    await openMenu(page);
    await expect(menu).toHaveText(MENU.en);
    await closeMenu(page);
    for (const { lang, option, saved } of SWITCHES) {
      await page.getByTestId('preferences-language').click();
      await page.locator('ion-popover ion-radio', { hasText: option }).click();
      await expect(toast(page, saved)).toBeVisible();
      await openMenu(page);
      await expect(menu).toHaveText(MENU[lang]);
      await settled(page);
      await page.screenshot({ path: shot(`FIX-SAAS-292-menu-${lang}-${size.width}`) });
      await closeMenu(page);
    }
    expect(await samePage(page)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test('ACCOUNTS-F21 · the name saved in Profile is the one at the top of the side menu, with no reload', async ({ page }) => {
  const errors = watchPageErrors(page);
  await page.setViewportSize(VIEWPORTS[2]);
  await signIn(page.request, ACCOUNT);
  await page.goto('/dashboard/account/profile');
  await markPage(page);
  const person = page.locator('ion-menu .sidebar-user-name');
  await expect(person).toHaveText(ACCOUNT.email);
  await page.getByTestId('profile-first-name').locator('input').fill('Marta');
  await page.getByTestId('profile-last-name').locator('input').fill('Ruiz');
  await page.getByTestId('profile-save').click();
  await expect(toast(page, 'Changes saved')).toBeVisible();
  await expect(person).toHaveText('Marta Ruiz');
  expect(await samePage(page)).toBe(true);
  expect(errors).toEqual([]);
});
