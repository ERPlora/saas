// The flows of «the plan, the rights and the catalogue's taxonomy» (hubs/WORKBOOK.md, MIGRATION-TASK APP-HUBS-4) that
// have a screen, at the three sizes of the migration (390×844, 834×1112, 1440×900), in English and in Spanish. Each test
// names its flow by its registry key; in hubs/WORKBOOK.md: G101=F31 (the snapshot: what a plan gives, changed in the
// admin, reaches its businesses), G05 and G01=F36 (the sectors and the business types in the admin).
// flow: HUBS-F31 — the staff change what a plan gives; the next pass of reconcile_hub_states takes it to the Hub.
// flow: HUBS-F36 — the staff keep the sectors and the business types of the sign-up.
//
// The spec plays the Hub (`startHubDouble`, as panel/hubs-people.spec.ts): it sees the snapshot each business gets. The
// pass of `reconcile_hub_states` is run as the scheduled task runs it, against this run's database. Its rows: a staff
// account and an owner with a business on Starter (`e2e-hubs4-…@example.com`), the taxonomy every deploy seeds
// (`seed_taxonomy`); Starter's places are put back after the test that changes them.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import {
  djangoPrint,
  expect,
  type HubCall,
  type HubDouble,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  startHubDouble,
  test,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PREFIX = 'e2e-hubs4-';
const PASSWORD = 'Harina-de-espelta-26';
const STAFF = { email: `${PREFIX}staff@example.com`, password: PASSWORD };
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

/** `ready` at each size: no sideways scroll and a capture `APP-HUBS-4-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-HUBS-4-${key}-${size.name}`), fullPage: true });
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

/** A superuser of the staff, their address proven. */
function createStaff(): void {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_superuser(email="${STAFF.email}", password="${PASSWORD}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
}

/**
 * A business that pays Starter, created by `hubs.business.create` as the panel creates it, ready and with nothing owed
 * to the Hub: from here only what the staff change owes it a snapshot. Its id.
 */
function businessOnStarter(): string {
  return djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from django.db.models import F',
      'from django.utils import timezone',
      'from hubs import services',
      'from hubs.models import Hub, Plan, Subscription',
      'from hubs.schemas import BusinessCreateIn',
      'from hubs.tests.conftest import ctx_for',
      `owner = get_user_model().objects.create_user(email="${PREFIX}owner-${Date.now()}@example.com", password="${PASSWORD}")`,
      'created = services.business_create(ctx_for(owner), BusinessCreateIn(name="Peluquería Ana", country="ES"))',
      'Subscription.objects.filter(hub_id=created.id).update(plan=Plan.objects.get(slug="starter"))',
      'Hub.objects.filter(pk=created.id).update(status="active", ready_at=timezone.now(), pending_hub_call="", pushed_state_version=F("state_version"))',
      'print(created.id)',
    ].join('\n'),
  )
    .split('\n')
    .at(-1) as string;
}

/** Starter's `max_users` now. */
function starterPlaces(): number {
  return Number(djangoPrint('from hubs.models import Plan;print(Plan.objects.get(slug="starter").max_users)'));
}

/** The pass of `reconcile_hub_states` (every 15 minutes in production), with the Hub this spec plays. */
function nextPass(): void {
  djangoPrint(
    [
      'from django.conf import settings',
      `settings.HUB_INTERNAL_URL = "http://127.0.0.1:${HUB_DOUBLE_PORT}"`,
      'from hubs import services',
      'services.reconcile()',
    ].join('\n'),
  );
}

const snapshots = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${id}/state`);

function placesInLastSnapshot(hub: HubDouble, id: string): number | undefined {
  const plan = snapshots(hub, id).at(-1)?.body.plan as { max_users?: number } | undefined;
  return plan?.max_users;
}

let hub: HubDouble;

test.beforeAll(async () => {
  removeOwnRows();
  createStaff();
  // The taxonomy every deploy seeds (saas-migrate runs seed_taxonomy), as public-web.spec.ts: the same here.
  execFileSync('uv', ['run', 'python', 'manage.py', 'seed_taxonomy'], { cwd: SAAS_DIR, env: djangoEnv(true), stdio: 'pipe' });
  hub = await startHubDouble();
});
test.afterAll(async () => {
  await hub?.close();
  removeOwnRows();
});

/** The staff raise Starter's places by three in its admin page; the notice says who gets it. */
async function raiseStarterPlaces(page: Page, notice: RegExp, key: string): Promise<number> {
  const places = starterPlaces() + 3;
  await signIn(page.request, STAFF);
  await page.goto('/admin/hubs/plan/?q=starter');
  await page.locator('#result_list tbody th a', { hasText: /^starter$/ }).click();
  await page.locator('input[name="max_users"]').fill(String(places));
  await page.locator('input[name="_save"]').click();
  const told = page.locator('ul.messagelist li', { hasText: notice });
  await atEverySize(page, key, async () => {
    await expect(told).toBeVisible();
  });
  return places;
}

for (const run of [
  { language: 'en', locale: 'en-US', suffix: '', notice: /^\d+ business(es)? on this plan gets? the change within 15 minutes\.$/ },
  {
    language: 'es',
    locale: 'es-ES',
    suffix: '-es',
    notice: /^\d+ negocios? con este plan recibe(n)? el cambio en los próximos 15 minutos\.$/,
  },
]) {
  test.describe(`in ${run.language}`, () => {
    test.use({ locale: run.locale });

    test(`HUBS-G101 (F31): the staff raise the places of a plan in the admin; its businesses get them at the Hub on the next pass${run.suffix}`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const before = starterPlaces();
      const id = businessOnStarter();
      try {
        const places = await raiseStarterPlaces(page, run.notice, `HUBS-G101${run.suffix}`);
        expect(placesInLastSnapshot(hub, id), 'nothing leaves before the pass').toBeUndefined();

        nextPass();

        await expect.poll(() => placesInLastSnapshot(hub, id)).toBe(places);
      } finally {
        djangoPrint(`from hubs.models import Plan;Plan.objects.filter(slug="starter").update(max_users=${before})`);
      }
      expect(errors).toEqual([]);
    });

    test(`HUBS-G05 + HUBS-G01 (F36): the staff keep the sectors and the business types of the sign-up in the admin${run.suffix}`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      await signIn(page.request, STAFF);

      await page.goto('/admin/hubs/sector/');
      const sectors = page.locator('#result_list tbody tr');
      await atEverySize(page, `HUBS-G05${run.suffix}`, async () => {
        expect(await sectors.count()).toBeGreaterThan(5);
        // Each language its own column (no translation tabs): the admin's headings in the page's language.
        await expect(page.locator('#result_list thead')).toContainText(run.language === 'es' ? 'Nombre (español)' : 'Name (Spanish)');
      });

      await page.goto('/admin/hubs/businesstype/?q=hair_salon');
      const types = page.locator('#result_list tbody tr');
      await atEverySize(page, `HUBS-G01-list${run.suffix}`, async () => {
        await expect(types.first()).toBeVisible();
      });

      await types.first().locator('th a').click();
      await atEverySize(page, `HUBS-G01${run.suffix}`, async () => {
        for (const field of ['code', 'name_en', 'name_es', 'description_en', 'description_es', 'vertical', 'icon', 'display_order']) {
          await expect(page.locator(`[name="${field}"]`)).toBeVisible();
        }
        await expect(page.locator('[name="sector"]')).toBeAttached();
      });
      expect(errors).toEqual([]);
    });
  });
}
