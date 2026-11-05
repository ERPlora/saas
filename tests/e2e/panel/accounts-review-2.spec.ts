// flow: ACCOUNTS-F25 ACCOUNTS-F26 ACCOUNTS-F27 ACCOUNTS-F28 ACCOUNTS-F29 ACCOUNTS-F30 ACCOUNTS-F31 ACCOUNTS-F33
// flow: ACCOUNTS-F34 ACCOUNTS-F36 ACCOUNTS-F38 ACCOUNTS-F43 ACCOUNTS-F47
// The review of the `hecho` flows of «the user menu, the data and the deletion of the account, the jump to a business
// and back, the API keys and their documentation, the audit log, reporting a problem and the panel's platform»
// (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-7, the second half of the review after accounts-review): every
// screen of those flows in English AND in Spanish, at the three sizes of the migration (language-review.ts). The flows
// themselves are played by accounts-profile, accounts-jump, accounts-keys, accounts-report and accounts-platform (in
// English); here each screen is checked in the language the person reads. The flows without a screen (F32, F35,
// F37, F39–F41, F45, F46) have their integration tests; F42's pages and F43's maintenance page and F46's mails are
// painted in both languages by public-errors, accounts-platform and accounts-mails.
// Accounts of this spec: `e2e-acc7-…@example.com`, removed before and after, with their businesses.
import { type Page } from '@playwright/test';

import { djangoPrint, expect, settled, signIn, signInThroughPage, test, watchPageErrors } from './fixtures';
import { closeOverlays, LANGUAGES, type Lang, openUserMenu, reviewOf, t } from './language-review';

const PREFIX = 'e2e-acc7-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const STATE = 'state-of-the-browser-that-started-the-jump-0123456789';
const SITE_SETTINGS = '/admin/base/sitesettings/';
const review = reviewOf('APP-ACCOUNTS-7');

/** The panel's menu as Django names it (base/navigation.py), in each language. */
const MENU: Record<Lang, string[]> = {
  en: ['Businesses', 'Store', 'Billing', 'Account'],
  es: ['Negocios', 'Tienda', 'Facturación', 'Cuenta'],
};

/** What the admin says in each language (Django's catalogues and ours, locale/es). */
const ADMIN: Record<Lang, Record<string, string>> = {
  en: {
    copyNow: 'Copy it now: it will not be shown again.',
    revoked: 'Keys revoked: 1.',
    maintenanceOn: 'Maintenance mode is on: only the ERPlora staff with a session uses erplora.com.',
    maintenanceOff: 'Maintenance mode is off: erplora.com is open to everyone.',
    saved: 'The site settings “Site settings” was changed successfully.',
  },
  es: {
    copyNow: 'Cópiala ahora: no se volverá a mostrar.',
    revoked: 'Claves revocadas: 1.',
    maintenanceOn: 'El modo mantenimiento está encendido: solo el personal de ERPlora con su sesión abierta usa erplora.com.',
    maintenanceOff: 'El modo mantenimiento está apagado: erplora.com está abierto a todo el mundo.',
    saved: 'El ajuste del sitio “Ajustes del sitio” se cambió correctamente.',
  },
};

// ── Accounts ──────────────────────────────────────────────────────────────────────────────────

const address = (name: string, lang: Lang) => `${PREFIX}${name}-${lang}-${Date.now()}@example.com`;

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from base.models import SiteSettings',
      'from hubs.models import Hub',
      'SiteSettings.objects.update(maintenance_mode=False, maintenance_message_en="", maintenance_message_es="")',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** An account speaking `lang`, its address proven; `superuser` and `team` make it ERPlora's admin or a team account. */
function createAccount(
  email: string,
  lang: Lang,
  role: 'customer' | 'superuser' | 'team' = 'customer',
): { email: string; password: string } {
  const create = {
    customer: `get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", first_name="Lucía", last_name="Fernández", language="${lang}")`,
    superuser: `services.create_platform_user("${email}", services.PLATFORM_ADMIN, "${PASSWORD}")[0]`,
    team: `services.create_platform_user("${email}", services.PLATFORM_SUPPORT, "${PASSWORD}")[0]`,
  }[role];
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from accounts import services',
      `user = ${create}`,
      `user.language = "${lang}"; user.save(update_fields=["language"])`,
      'EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

/** A business `email` owns (hubs' own fixture, as accounts-profile builds it). */
function ownBusiness(email: string, name: string): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.tests.conftest import create_business',
      `create_business(get_user_model().objects.get(email="${email}"), name="${name}")`,
    ].join('\n'),
  );
}

// ── The panel's menus ─────────────────────────────────────────────────────────────────────────

/** The panel's menu: the side menu from `lg`, its drawer behind the topbar's menu button below. */
async function openMenu(page: Page): Promise<void> {
  const entries = page.locator('ion-menu .nav-item');
  await expect(entries.first()).toBeAttached();
  await settled(page);
  if (!(await entries.first().isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(entries.first()).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => (document.querySelector('ion-menu') as (HTMLElement & { isOpen: () => Promise<boolean> }) | null)?.isOpen() ?? false),
      )
      .toBe(true);
  }
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

for (const { lang, locale } of LANGUAGES) {
  test.describe(`in ${lang}`, () => {
    test.use({ locale });

    test(`ACCOUNTS-F47 · ACCOUNTS-F25 · ACCOUNTS-F26 · ACCOUNTS-F27 · ACCOUNTS-F30 (${lang}): the panel's menu, the user menu, «Export your data» and «Delete your account»`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('panel', lang), lang);
      ownBusiness(account.email, 'Panadería de Lucía');
      await signIn(page.request, account);

      await page.goto('/dashboard/businesses');
      await review(page, lang, 'ACCOUNTS-F47', async () => {
        await closeOverlays(page);
        await openMenu(page);
        await expect(page.locator('ion-menu .nav-item')).toHaveText(MENU[lang]);
        await expect(page.locator('ion-menu .nav-item[aria-current="page"]')).toHaveText(MENU[lang][0]);
      });
      await review(page, lang, 'ACCOUNTS-F25', async () => {
        await closeOverlays(page);
        await openUserMenu(page);
        await expect(page.locator('ion-popover.sidebar-user-popover ion-item')).toHaveText([
          t(lang, 'saas.userMenu.account'),
          t(lang, 'saas.userMenu.reportProblem'),
          t(lang, 'userMenu.help'),
          t(lang, 'userMenu.theme'),
          t(lang, 'userMenu.logout'),
        ]);
      });
      await closeOverlays(page);

      // An owner is held: the card names its business and «Delete account» is off.
      await page.goto('/dashboard/account/profile');
      await review(page, lang, 'ACCOUNTS-F26-F27-held', async () => {
        await expect(page.getByTestId('profile-export-card')).toContainText(t(lang, 'accounts.account.export.lead'));
        await expect(page.getByTestId('profile-export')).toHaveText(t(lang, 'accounts.account.export.download'));
        await expect(page.getByTestId('profile-danger-business')).toHaveText('Panadería de Lucía');
        await expect(page.getByTestId('profile-delete')).toHaveJSProperty('disabled', true);
      });

      // Its business deleted (90 days to recover it): nothing holds it, and the dialog says what goes.
      djangoPrint(
        [
          'from django.utils import timezone',
          'from hubs.models import Hub',
          `Hub.objects.filter(members__user__email="${account.email}").update(status=Hub.Status.DELETED, deletion_requested_at=timezone.now())`,
        ].join('\n'),
      );
      await page.reload();
      await expect(page.getByTestId('profile-delete')).toHaveJSProperty('disabled', false);
      await page.getByTestId('profile-delete').click();
      await review(page, lang, 'ACCOUNTS-F27-dialog', async () => {
        const dialog = page.getByTestId('delete-account');
        await expect(dialog).toContainText(t(lang, 'accounts.account.delete.message'));
        await expect(page.getByTestId('delete-account-input')).toBeVisible();
        await expect(page.getByTestId('delete-account-submit')).toBeInViewport({ ratio: 1 });
      });
      await closeOverlays(page);

      // The account on its own, as the installed app opens it: nothing that sells.
      await page.goto('/dashboard/account/profile?surface=account');
      await review(page, lang, 'ACCOUNTS-F30', async () => {
        await closeOverlays(page);
        await openMenu(page);
        await expect(page.locator('ion-menu .nav-item')).toHaveText(MENU[lang].filter((_, at) => at !== 1));
      });
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F31 · ACCOUNTS-F33 · ACCOUNTS-F34 (${lang}): «API keys» empty, «New API key», the key shown once, «Revoke» and the documentation`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('keys', lang), lang);
      await signIn(page.request, account);

      await page.goto('/dashboard/account/api-keys');
      await review(page, lang, 'ACCOUNTS-F31-empty', async () => {
        await expect(page.getByTestId('api-keys-empty')).toContainText(t(lang, 'accounts.account.keys.empty'));
        await expect(page.getByTestId('api-keys-docs')).toHaveText(t(lang, 'accounts.account.keys.docs'));
      });
      await page.getByTestId('api-keys-empty-new').click();
      await review(page, lang, 'ACCOUNTS-F31-new', async () => {
        await expect(page.getByText(t(lang, 'accounts.account.keys.newTitle'), { exact: true })).toBeVisible();
        await expect(page.getByTestId('new-key-name')).toBeVisible();
        await expect(page.getByTestId('new-key-submit')).toBeInViewport({ ratio: 1 });
      });
      await page.getByTestId('new-key-name').locator('input').fill('Postman');
      await page.getByTestId('new-key-scope-hubs.read').click();
      await page.getByTestId('new-key-submit').click();
      const created = t(lang, 'accounts.account.keys.created').replace('{name}', 'Postman');
      await review(page, lang, 'ACCOUNTS-F31-shown-once', async () => {
        await expect(page.getByTestId('new-key-secret')).toHaveText(/^erps_live_[A-Za-z0-9]{48}$/);
        await expect(page.getByText(t(lang, 'accounts.account.keys.copyNow'))).toBeVisible();
        await expect(page.getByTestId('new-key-done')).toHaveText(t(lang, 'accounts.account.keys.saved'));
        // Nothing covers the key on a phone: «Key created» waits for the sheet to go.
        await expect(page.getByText(created)).toHaveCount(0);
      });
      await page.getByTestId('new-key-done').click();
      await expect(page.getByText(created)).toBeVisible();
      const row = page.getByTestId('api-keys-row').filter({ hasText: 'Postman' }).first();
      await review(page, lang, 'ACCOUNTS-F31-listed', async () => {
        await expect(row).toBeVisible();
        await expect(row).toContainText('erps_live_');
      });

      const id = await row.getAttribute('data-id');
      await page.getByTestId(`api-keys-row-${id}-revoke`).first().click();
      await review(page, lang, 'ACCOUNTS-F33-confirm', async () => {
        await expect(page.getByText(t(lang, 'accounts.account.keys.revokeTitle').replace('{name}', 'Postman'))).toBeVisible();
        await expect(page.getByText(t(lang, 'accounts.account.keys.revokeMessage'))).toBeVisible();
        await expect(page.getByTestId('revoke-key-submit')).toBeInViewport({ ratio: 1 });
      });
      await page.getByTestId('revoke-key-submit').click();
      await review(page, lang, 'ACCOUNTS-F33-revoked', async () => {
        await expect(page.getByText(t(lang, 'accounts.account.keys.revoked').replace('{name}', 'Postman'))).toBeVisible();
        await expect(page.getByTestId('api-keys-empty')).toBeVisible();
      });

      await page.goto('/api/docs');
      await review(
        page,
        lang,
        'ACCOUNTS-F34',
        async () => {
          await expect(page.getByRole('heading', { name: /ERPlora Cloud API/ }).first()).toBeVisible();
          await expect(page.locator('#redoc-ui')).toContainText('/api/accounts/api-keys');
        },
        { fullPage: false },
      );
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F31 · ACCOUNTS-F33 · ACCOUNTS-F36 · ACCOUNTS-F43 (${lang}): the admin's keys, its audit log and its site settings`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const root = createAccount(address('root', lang), lang, 'superuser');
      const teammate = createAccount(address('team', lang), lang, 'team');
      await signIn(page.request, root);

      await page.goto('/admin/accounts/apikey/add/');
      const form = page.locator('#apikey_form');
      await review(page, lang, 'ACCOUNTS-F31-admin-form', async () => {
        await expect(form).toBeVisible();
        await expect(form.locator('select[name="user"] option', { hasText: teammate.email })).toHaveCount(1);
      });
      await form.locator('select[name="user"]').selectOption({ label: teammate.email });
      await form.locator('input[name="name"]').fill(`QA monitor ${lang}`);
      await form.locator('input[name="scopes"][value="hubs.read"]').check();
      await form.locator('input[name="_save"]').click();
      await review(page, lang, 'ACCOUNTS-F31-admin-issued', async () => {
        await expect(page.locator('[data-api-key-secret]')).toBeVisible();
        await expect(page.getByText(ADMIN[lang].copyNow)).toBeVisible();
      });

      await page.goto('/admin/accounts/apikey/');
      await page.locator('#result_list tbody tr', { hasText: `QA monitor ${lang}` }).locator('input.action-select').check();
      await page.locator('select[name="action"]').selectOption('revoke');
      await page.locator('button[name="index"]').click();
      await review(page, lang, 'ACCOUNTS-F33-admin', async () => {
        await expect(page.locator('.messagelist')).toContainText(ADMIN[lang].revoked);
        // What the key may open, in words: never the raw `["hubs.read"]`.
        await expect(
          page.locator('#result_list tbody tr', { hasText: `QA monitor ${lang}` }).locator('td.field-permissions'),
        ).toHaveText(lang === 'es' ? 'Negocios · lectura' : 'Businesses · read');
      });

      // The key just issued and revoked is in the audit log, in the staff's language.
      await page.goto(`/admin/auditlog/logentry/?q=${encodeURIComponent(teammate.email)}`);
      const entries = page.locator('#result_list tbody tr');
      await review(page, lang, 'ACCOUNTS-F36-list', async () => {
        await expect(entries.first()).toBeVisible();
        // auditlog writes these two in English whatever the language: ours says them in the staff's (accounts/admin.py).
        await expect(page.locator('#result_list thead')).toContainText(lang === 'es' ? 'ID de correlación' : 'Correlation ID');
        await expect(entries.first()).toContainText(lang === 'es' ? /\d+ cambios?: / : /\d+ changes?: /);
      });
      await entries.first().locator('th a, td a').first().click();
      await review(page, lang, 'ACCOUNTS-F36-entry', async () => {
        await expect(page.locator('#content-main')).toBeVisible();
      });

      // «Site settings»: the switch says what it does, on and off, in the staff's language.
      try {
        await page.goto(SITE_SETTINGS);
        await expect(page).toHaveURL(/\/admin\/base\/sitesettings\/[0-9a-f-]+\/change\/$/);
        await page.locator('#id_maintenance_mode').check();
        await page.locator('input[name="_save"]').click();
        await review(page, lang, 'ACCOUNTS-F43-on', async () => {
          await expect(page.locator('.messagelist')).toContainText(ADMIN[lang].maintenanceOn);
          await expect(page.locator('.messagelist')).toContainText(ADMIN[lang].saved);
        });
        await page.locator('#id_maintenance_mode').uncheck();
        await page.locator('input[name="_save"]').click();
        await review(page, lang, 'ACCOUNTS-F43-off', async () => {
          await expect(page.locator('.messagelist')).toContainText(ADMIN[lang].maintenanceOff);
        });
      } finally {
        djangoPrint('from base.models import SiteSettings\nSiteSettings.objects.update(maintenance_mode=False)');
      }
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F28 · ACCOUNTS-F29 (${lang}): the jump refused (no access, a link to no business, too many) and a foreign address after signing in`, async ({
      page,
      browser,
      baseURL,
    }) => {
      const errors = watchPageErrors(page);
      const stranger = createAccount(address('stranger', lang), lang);
      await signIn(page.request, stranger);
      const hub = `${PREFIX}not-mine`;

      await page.goto(`/hub-login/?hub=${hub}&next=/&state=${STATE}`);
      await expect(page).toHaveURL(/\/login\/error\?code=not_a_member/);
      await review(page, lang, 'ACCOUNTS-F28-no-access', async () => {
        await expect(page.getByRole('heading', { name: t(lang, 'accounts.loginError.notAMember.heading') })).toBeVisible();
        await expect(page.getByTestId('login-error-badge')).toHaveText(t(lang, 'accounts.loginError.notAMember.badge'));
        await expect(page.getByText(new RegExp(`${hub}\\.`))).toBeVisible();
        await expect(page.getByText('Panadería')).toHaveCount(0);
        await expect(page.getByTestId('login-error-links')).toContainText(t(lang, 'accounts.loginError.contactSupport'));
      });
      await page.goto(`/hub-login/?hub=www&next=/&state=${STATE}`);
      await expect(page).toHaveURL(/\/login\/error\?code=invalid_hub/);
      await review(page, lang, 'ACCOUNTS-F28-no-business', async () => {
        await expect(page.getByRole('heading', { name: t(lang, 'accounts.loginError.invalidHub.heading') })).toBeVisible();
      });
      await page.goto('/login/error?code=too_many');
      await review(page, lang, 'ACCOUNTS-F28-too-many', async () => {
        await expect(page.getByRole('heading', { name: t(lang, 'accounts.loginError.tooMany.heading') })).toBeVisible();
        await expect(page.getByText(t(lang, 'accounts.loginError.tooMany.message'))).toBeVisible();
      });

      // Back from a business on a browser with no session of erplora.com: an address that is not erplora.com is not
      // followed after signing in; the person lands on the Entrada with its session.
      const other = await browser.newContext({ baseURL, locale });
      try {
        const fresh = await other.newPage();
        const freshErrors = watchPageErrors(fresh);
        await fresh.goto('/launch?next=https://evil.example.com/account');
        await signInThroughPage(fresh, stranger);
        await expect(fresh).toHaveURL(`${new URL(baseURL!).origin}/launch`);
        await review(fresh, lang, 'ACCOUNTS-F29-foreign-address', async () => {
          // The Entrada of an account with no business: «Create your business» and «Go to the panel», never the spinner.
          await expect(fresh.getByTestId('launch-panel')).toBeVisible();
          await expect(fresh.getByTestId('launch-loading')).toHaveCount(0);
          await expect(fresh.getByText(t(lang, 'hubs.common.signedInAs').replace('{email}', stranger.email))).toBeVisible();
        });
        expect(freshErrors).toEqual([]);
      } finally {
        await other.close();
      }
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F38 (${lang}): «Report a problem» from the user menu, sent, and back`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const account = createAccount(address('report', lang), lang);
      await signIn(page.request, account);

      await page.goto('/dashboard/account/security');
      await openUserMenu(page);
      await page.getByTestId('user-menu-report').click();
      await expect(page).toHaveURL(/\/dashboard\/report-a-problem/);
      await review(page, lang, 'ACCOUNTS-F38-form', async () => {
        await expect(page.getByTestId('report-intro')).toHaveText(t(lang, 'accounts.report.intro'));
        await expect(page.getByTestId('report-context')).toContainText(t(lang, 'accounts.report.context'));
        await expect(page.getByTestId('report-send')).toHaveJSProperty('disabled', true);
      });
      await page.getByTestId('report-subject').locator('input').fill('La factura no se descarga');
      await page.getByTestId('report-description').locator('textarea').fill('Pulso «Descargar» y no pasa nada.');
      await page.getByTestId('report-send').click();
      await review(page, lang, 'ACCOUNTS-F38-sent', async () => {
        await expect(page.getByTestId('report-sent')).toContainText(t(lang, 'accounts.report.sentTitle'));
        await expect(page.getByTestId('report-sent')).toContainText(account.email);
      });
      await page.getByTestId('report-back').click();
      await expect(page).toHaveURL(/\/dashboard\/account\/security$/);
      expect(errors).toEqual([]);
    });
  });
}
