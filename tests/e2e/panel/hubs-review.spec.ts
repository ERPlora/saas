// The review of the hubs flows marked «hecho» (MIGRATION-TASK APP-HUBS-5): each screen of hubs/WORKBOOK.md, in
// English and in Spanish, at the three sizes of the migration (390×844, 834×1112, 1440×900). The account speaks the
// run's language (User.language wins on the panel) and each screen is checked with its catalogue's own words
// (hubs/frontend/locale/<language>.json), so an untranslated text or one that drifted from the catalogue fails here;
// in Spanish the English words of the same screen must not show. Each screen: no sideways scroll, no field's label
// cut with «…», no page error, and a capture `APP-HUBS-5-<flow>-<size>-<language>`. The flows' own behaviour is in hubs-flows, hubs-settings,
// hubs-people and hubs-rights (English captures there); this spec only looks at the screens.
// Accounts of this spec: `e2e-hubs5-…@example.com` (panel_seed.py's `clear` removes every `e2e-…@example.com`).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Browser, type Locator, type Page } from '@playwright/test';

import {
  apiPost,
  djangoPrint,
  expect,
  seedPanel,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  test,
  watchPageErrors,
} from './fixtures';
import { PANEL_URL } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PREFIX = 'e2e-hubs5-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const LANGUAGES = [
  { language: 'en', locale: 'en-US' },
  { language: 'es', locale: 'es-ES' },
] as const;
type Language = (typeof LANGUAGES)[number]['language'];

const CATALOGUES = Object.fromEntries(
  LANGUAGES.map(({ language }) => [
    language,
    JSON.parse(readFileSync(resolve(SAAS_DIR, 'hubs', 'frontend', 'locale', `${language}.json`), 'utf8')) as Record<string, unknown>,
  ]),
) as Record<Language, Record<string, unknown>>;

/** The catalogue's text of `key` in `language`, with its `{placeholders}` filled. */
function say(language: Language, key: string, params: Record<string, string> = {}): string {
  const text = key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], CATALOGUES[language]);
  if (typeof text !== 'string') throw new Error(`no text ${key} in ${language}`);
  return text.replace(/\{(\w+)\}/g, (_, name: string) => params[name] ?? `{${name}}`);
}

/** The page Ionic shows (it keeps the pages it left in the DOM, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

interface Account {
  email: string;
  first: string;
  name: string;
}

/** A fresh account of this spec speaking `language`, its address proven. */
function account(who: string, first: string, last: string, language: Language): Account {
  const email = `${PREFIX}${who}-${language}-${Date.now()}@example.com`;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="${language}", first_name="${first}", last_name="${last}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  return { email, first, name: `${first} ${last}` };
}

/** A business of `page`'s account called `name`, ready as the Hub leaves it, on Starter when `paid`. */
async function businessOf(page: Page, name: string, { paid = false } = {}): Promise<string> {
  const created = await apiPost(page.request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), await created.text()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  djangoPrint(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub, Plan, Subscription',
      `Hub.objects.filter(pk="${id}").update(status="active", ready_at=timezone.now(), pending_hub_call="")`,
      paid ? `Subscription.objects.filter(hub_id="${id}").update(plan=Plan.objects.get(slug="starter"))` : '',
    ].join('\n'),
  );
  return id;
}

/** `person` invited to business `id` as an employee by `page`'s account; accepted when `accept`. Their member id. */
async function invite(page: Page, browser: Browser, id: string, person: Account, accept: boolean): Promise<string> {
  const invited = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: person.email, role: 'hub_employee', message: '' });
  expect(invited.status(), await invited.text()).toBe(200);
  const member = ((await invited.json()) as { id: string }).id;
  if (accept) {
    const context = await browser.newContext({ baseURL: PANEL_URL });
    await signIn(context.request, { email: person.email, password: PASSWORD });
    const accepted = await apiPost(context.request, '/api/hubs/invitations/accept', { id: member });
    expect(accepted.status(), await accepted.text()).toBe(200);
    await context.close();
  }
  return member;
}

/** The labels of the fields on screen that Ionic cuts with «…» because they do not fit. */
async function cutLabels(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('ion-input .label-text, ion-select .label-text, ion-textarea .label-text')]
      .filter((label) => label.offsetParent !== null && label.scrollWidth > label.clientWidth + 1)
      .map((label) => label.textContent?.trim() ?? ''),
  );
}

/**
 * `ready` at each size: no sideways scroll, a capture `APP-HUBS-5-<key>-<size>-<language>`, and in Spanish none of
 * `english` (the same screen's English words) on `where`; back at 1440 after.
 */
async function atEverySize(
  page: Page,
  key: string,
  language: Language,
  ready: () => Promise<void>,
  { where, english = [] }: { where?: Locator; english?: string[] } = {},
): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    expect(await cutLabels(page), `${key}: a field's label cut at ${size.name}`).toEqual([]);
    if (language === 'es' && where) {
      for (const text of english) await expect(where, `${key}: English left in Spanish`).not.toContainText(text);
    }
    await page.screenshot({ path: shot(`APP-HUBS-5-${key}-${size.name}-${language}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

function removeOwnRows(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import Hub',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}").delete()`,
    ].join('\n'),
  );
}

test.beforeAll(() => {
  removeOwnRows();
  seedPanel();
});
test.afterAll(() => {
  removeOwnRows();
  seedPanel('clear');
});

for (const { language, locale } of LANGUAGES) {
  test.describe(`in ${language}`, () => {
    test.use({ locale });

    test(`HUBS-F01 + HUBS-F02 + HUBS-F04 (${language}): the sign-up from erplora.com and from the app, then «Preparing»`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const owner = account('first', 'Olga', 'Ruiz', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });

      await page.goto('/shell/');
      await atEverySize(page, 'HUBS-F02', language, async () => {
        await expect(shown(page).getByText(say(language, 'hubs.launch.first.title'), { exact: true })).toBeVisible();
      });
      await page.goto('/launch');
      const card = shown(page);
      await atEverySize(
        page,
        'HUBS-F01',
        language,
        async () => {
          await expect(card.getByText(say(language, 'hubs.launch.first.title'), { exact: true })).toBeVisible();
          await expect(card).toContainText(say(language, 'hubs.launch.first.lead'));
          await expect(card.getByTestId('create-submit')).toContainText(say(language, 'hubs.create.submit'));
        },
        { where: card, english: [say('en', 'hubs.launch.first.lead'), say('en', 'hubs.create.submit')] },
      );
      await card.getByTestId('create-name').locator('input').fill('Panadería Dulce');
      await card.getByTestId('create-submit').click();
      await atEverySize(
        page,
        'HUBS-F04',
        language,
        async () => {
          await expect(card).toContainText(say(language, 'hubs.launch.preparing.title', { name: 'Panadería Dulce' }));
          await expect(card).toContainText(say(language, 'hubs.launch.preparing.lead'));
        },
        { where: card, english: [say('en', 'hubs.launch.preparing.lead')] },
      );
      expect(errors).toEqual([]);
    });

    test(`HUBS-F11 + HUBS-F12 (${language}): the start with one business, then the app's start with several`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const owner = account('enter', 'Olga', 'Ruiz', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      await businessOf(page, 'Bar Manolo', { paid: true });

      await page.goto('/launch');
      await atEverySize(
        page,
        'HUBS-F11',
        language,
        async () => {
          await expect(shown(page)).toContainText(say(language, 'hubs.launch.one.greeting', { name: 'Olga' }));
          await expect(shown(page).getByTestId('launch-open')).toContainText(say(language, 'hubs.common.openName', { name: 'Bar Manolo' }));
        },
        { where: shown(page), english: [say('en', 'hubs.launch.one.lead')] },
      );
      await businessOf(page, 'Café Lola');
      await page.goto('/shell/');
      await atEverySize(
        page,
        'HUBS-F12',
        language,
        async () => {
          await expect(shown(page)).toContainText(say(language, 'hubs.launch.several.title'));
          await expect(shown(page).getByTestId('launch-business')).toHaveCount(2);
        },
        { where: shown(page), english: [say('en', 'hubs.launch.several.title')] },
      );
      expect(errors).toEqual([]);
    });

    test(`HUBS-F03 + HUBS-F09 + HUBS-F10 + HUBS-F19 (${language}): Businesses with a deleted one, «Create business» and «Recover»`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const owner = account('list', 'Olga', 'Ruiz', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      await businessOf(page, 'Bar Manolo', { paid: true });
      const gone = await businessOf(page, 'Café Lola');
      const deleted = await apiPost(page.request, '/api/hubs/businesses/delete', { id: gone, confirm_name: 'Café Lola' });
      expect(deleted.status(), await deleted.text()).toBe(200);

      // The old overview of the panel leads to Businesses, its home (HUBS-F10).
      await page.goto('/dashboard/');
      await expect(page).toHaveURL(/\/dashboard\/businesses$/);
      const list = shown(page);
      await atEverySize(
        page,
        'HUBS-F09',
        language,
        async () => {
          await expect(list.getByText(say(language, 'hubs.list.title'), { exact: true }).first()).toBeVisible();
          await expect(list.getByTestId('businesses-row')).toHaveCount(2);
          await expect(list.getByRole('button', { name: say(language, 'hubs.list.actions.restoreName', { name: 'Café Lola' }) })).toBeVisible();
        },
        { where: list, english: [say('en', 'hubs.list.create')] },
      );
      await list.getByTestId('businesses-add').click();
      const dialog = page.getByTestId('create-modal');
      await atEverySize(
        page,
        'HUBS-F03',
        language,
        async () => {
          await expect(dialog.getByTestId('create-modal-submit')).toBeInViewport({ ratio: 1 });
          await expect(dialog).toContainText(say(language, 'hubs.createModal.title'));
          await expect(dialog).toContainText(say(language, 'hubs.create.heading'));
        },
        { where: dialog, english: [say('en', 'hubs.create.heading')] },
      );
      await page.keyboard.press('Escape');
      await page.goto(`/dashboard/businesses/${gone}/summary`);
      await atEverySize(
        page,
        'HUBS-F19',
        language,
        async () => {
          await expect(shown(page).getByTestId('business-deleted')).toBeVisible();
          await expect(shown(page).getByTestId('business-restore')).toBeVisible();
        },
        { where: shown(page), english: [say('en', 'hubs.danger.restore')] },
      );
      expect(errors).toEqual([]);
    });

    test(`HUBS-F13 + HUBS-F15 + HUBS-F16 (${language}): the Summary's devices card, «General» and «Change address»`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const owner = account('settings', 'Olga', 'Ruiz', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      const id = await businessOf(page, 'Bar Manolo');

      await page.goto(`/dashboard/businesses/${id}/summary`);
      const summary = shown(page);
      await atEverySize(
        page,
        'HUBS-F13',
        language,
        async () => {
          await expect(summary.getByTestId('device-access-card')).toContainText(say(language, 'hubs.business.devices.eyebrow'));
          await expect(summary.getByTestId('device-access-card').getByLabel(say(language, 'hubs.business.devices.address'))).toBeVisible();
          await expect(summary.getByTestId('summary-plan-store')).toHaveText(say(language, 'hubs.business.plan.upgrade'));
        },
        { where: summary, english: [say('en', 'hubs.business.devices.title')] },
      );
      await page.goto(`/dashboard/businesses/${id}/settings`);
      const settings = shown(page);
      await atEverySize(
        page,
        'HUBS-F15',
        language,
        async () => {
          await expect(settings.getByTestId('settings-general')).toContainText(say(language, 'hubs.settings.title'));
          await expect(settings.getByTestId('danger-zone')).toContainText(say(language, 'hubs.danger.title'));
        },
        { where: settings, english: [say('en', 'hubs.danger.title')] },
      );
      await settings.getByTestId('settings-change-address').click();
      const dialog = page.getByTestId('address-dialog');
      await atEverySize(
        page,
        'HUBS-F16',
        language,
        async () => {
          await expect(dialog.getByTestId('address-dialog-submit')).toBeInViewport({ ratio: 1 });
          await expect(dialog.getByTestId('address-dialog-submit')).toContainText(say(language, 'hubs.addressDialog.submit'));
        },
        { where: dialog, english: [say('en', 'hubs.addressDialog.submit')] },
      );
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      // «Delete business» (HUBS-F18, `parcial` for what it lacks, not for this screen): its field's label fits.
      await settings.getByTestId('danger-delete').click();
      const deleting = page.getByTestId('delete-dialog');
      await atEverySize(
        page,
        'HUBS-F18',
        language,
        async () => {
          await expect(deleting.getByTestId('delete-dialog-submit')).toBeInViewport({ ratio: 1 });
          await expect(deleting).toContainText(say(language, 'hubs.danger.confirmTitle', { name: 'Bar Manolo' }));
          await expect(deleting.getByTestId('delete-dialog-input')).toBeVisible();
        },
        { where: deleting, english: [say('en', 'hubs.danger.confirmMessage')] },
      );
      expect(errors).toEqual([]);
    });

    test(`HUBS-F24 + HUBS-F26 + HUBS-F27 + HUBS-F28 + HUBS-F29 (${language}): «Team» and its dialogs`, async ({ page, browser }) => {
      const errors = watchPageErrors(page);
      const owner = account('team', 'Olga', 'Ruiz', language);
      const ana = account('team-ana', 'Ana', 'Gil', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      const id = await businessOf(page, 'Bar Manolo', { paid: true });
      const member = await invite(page, browser, id, ana, true);

      await page.goto(`/dashboard/businesses/${id}/members`);
      const team = shown(page);
      await atEverySize(
        page,
        'HUBS-F29',
        language,
        async () => {
          await expect(team).toContainText(say(language, 'hubs.members.title'));
          await expect(team.getByTestId('members-row')).toHaveCount(2);
        },
        { where: team, english: [say('en', 'hubs.members.title')] },
      );
      await team.getByTestId('members-add').click();
      const inviting = page.getByTestId('invite-modal');
      await atEverySize(page, 'HUBS-F24', language, async () => {
        await expect(inviting.getByTestId('invite-modal-submit')).toBeInViewport({ ratio: 1 });
        await expect(inviting).toContainText(say(language, 'hubs.members.inviteModal.title', { name: 'Bar Manolo' }));
      });
      await page.keyboard.press('Escape');
      await expect(inviting).toBeHidden();

      await team.getByTestId(`members-row-${member}-change_role`).click();
      const role = page.getByTestId('role-modal');
      await atEverySize(page, 'HUBS-F26', language, async () => {
        await expect(role.getByTestId('role-modal-submit')).toBeInViewport({ ratio: 1 });
        await expect(role).toContainText(say(language, 'hubs.members.roleModal.title', { name: ana.name }));
      });
      await page.keyboard.press('Escape');
      await expect(role).toBeHidden();

      await team.getByTestId(`members-row-${member}-remove`).click();
      const removing = page.getByTestId('remove-dialog');
      await atEverySize(page, 'HUBS-F27', language, async () => {
        await expect(removing.getByTestId('remove-dialog-submit')).toBeInViewport({ ratio: 1 });
        await expect(removing).toContainText(say(language, 'hubs.members.remove.title', { name: ana.name }));
      });
      await page.keyboard.press('Escape');
      await expect(removing).toBeHidden();

      await team.getByTestId(`members-row-${member}-menu`).click();
      await page.locator('ion-popover.data-table__row-menu').getByTestId(`members-row-${member}-transfer`).click();
      const transfer = page.getByTestId('transfer-dialog');
      await atEverySize(page, 'HUBS-F28', language, async () => {
        await expect(transfer.getByTestId('transfer-dialog-submit')).toBeInViewport({ ratio: 1 });
        await expect(transfer).toContainText(say(language, 'hubs.members.transfer.title', { business: 'Bar Manolo' }));
      });
      expect(errors).toEqual([]);
    });

    test(`HUBS-F25 (${language}): «You have been invited» for whoever has an invitation waiting`, async ({ page, browser }) => {
      const errors = watchPageErrors(page);
      const owner = account('invites', 'Olga', 'Ruiz', language);
      const lucia = account('invited', 'Lucía', 'Pérez', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      const id = await businessOf(page, 'Bar Manolo');
      await invite(page, browser, id, lucia, false);

      await page.context().clearCookies();
      await signIn(page.request, { email: lucia.email, password: PASSWORD });
      await page.goto('/invitation');
      const card = shown(page);
      await atEverySize(
        page,
        'HUBS-F25',
        language,
        async () => {
          await expect(card).toContainText(say(language, 'hubs.invitation.pageTitle'));
          await expect(card.getByTestId('invitation-accept')).toBeVisible();
        },
        { where: card, english: [say('en', 'hubs.invitation.pageTitle')] },
      );
      expect(errors).toEqual([]);
    });

    test(`HUBS-F23 + HUBS-F30 (${language}): the staff's page of a business and the accesses list in the admin`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const owner = account('admin', 'Olga', 'Ruiz', language);
      await signIn(page.request, { email: owner.email, password: PASSWORD });
      const id = await businessOf(page, 'Bar Manolo');
      const staff = `${PREFIX}staff-${language}-${Date.now()}@example.com`;
      djangoPrint(
        [
          'from allauth.account.models import EmailAddress',
          'from django.contrib.auth import get_user_model',
          `user = get_user_model().objects.create_superuser(email="${staff}", password="${PASSWORD}", language="${language}")`,
          'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
        ].join('\n'),
      );
      await page.context().clearCookies();
      await signIn(page.request, { email: staff, password: PASSWORD });

      await page.goto(`/admin/hubs/hub/${id}/change/`);
      await atEverySize(page, 'HUBS-F23', language, async () => {
        await expect(page.locator('#content')).toContainText(owner.email);
        await expect(page.locator('html')).toHaveAttribute('lang', language);
      });
      await page.goto(`/admin/hubs/hubmember/?q=${encodeURIComponent(owner.email)}`);
      await atEverySize(page, 'HUBS-F30', language, async () => {
        await expect(page.locator('#result_list tbody tr')).toHaveCount(1);
        await expect(page.locator('#changelist-filter')).toBeVisible();
      });
      expect(errors).toEqual([]);
    });
  });
}
