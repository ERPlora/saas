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
import type { APIRequestContext, Page } from '@playwright/test';

import {
  captureAtEverySize,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  type HubCall,
  type HubDouble,
  removeAccountsWarm,
  signIn,
  startHubDouble,
  test,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const atEverySize = captureAtEverySize('APP-HUBS-4');

const PREFIX = 'e2e-hubs4-';
const PASSWORD = 'Harina-de-espelta-26';
const STAFF = { email: `${PREFIX}staff@example.com`, password: PASSWORD };

/**
 * A business that pays Starter, created by `hubs.business.create` as the panel creates it, ready and with nothing owed
 * to the Hub: from here only what the staff change owes it a snapshot. Its id.
 */
async function businessOnStarter(): Promise<string> {
  return (
    await djangoPrintWarm(
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
  )
    .split('\n')
    .at(-1) as string;
}

/** Starter's `max_users` now, as the plans on sale say it (`hubs.plan.list`, the Store's). */
async function starterPlaces(request: APIRequestContext): Promise<number> {
  const listed = await request.get('/api/plans');
  expect(listed.status(), await listed.text()).toBe(200);
  const { plans } = (await listed.json()) as { plans: Array<{ slug: string; max_users: number }> };
  const starter = plans.find((plan) => plan.slug === 'starter');
  if (!starter) throw new Error('Starter is not on sale');
  return starter.max_users;
}

/**
 * The pass of `reconcile_hub_states` (every 15 minutes in production), with the Hub this spec plays, which answers
 * while it runs: the pass also takes whatever else the run's database owes the Hub (saas#176). Run by the warm Django,
 * its Hub only for this pass (the warm process outlives the spec).
 */
async function nextPass(): Promise<void> {
  await djangoPrintWarm(
    [
      'from django.test import override_settings',
      'from hubs import services',
      `with override_settings(HUB_INTERNAL_URL="http://127.0.0.1:${HUB_DOUBLE_PORT}"):`,
      '    services.reconcile()',
    ].join('\n'),
  );
}

const snapshots = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${id}/state`);

function placesInLastSnapshot(hub: HubDouble, id: string): number | undefined {
  const plan = snapshots(hub, id).at(-1)?.body.plan as { max_users?: number } | undefined;
  return plan?.max_users;
}

/** Whether the SaaS still owes business `id`'s Hub a snapshot: it never heard the Hub take the last one (only Django knows). */
async function snapshotOwed(id: string): Promise<boolean> {
  return (
    (await djangoPrintWarm(
      `from django.db.models import F;from hubs.models import Hub;print(Hub.objects.filter(pk="${id}", pushed_state_version__lt=F("state_version")).exists())`,
    )) === 'True'
  );
}

let hub: HubDouble;

// Django's boots on no test's clock (saas#354): the warm Django starts here, with the spec's staff.
test.beforeAll(async () => {
  await removeAccountsWarm(PREFIX);
  await createAccountWarm(STAFF.email, PASSWORD, { role: 'superuser' });
  // The taxonomy every deploy seeds (saas-migrate runs seed_taxonomy), as public-web.spec.ts: the same here.
  await djangoPrintWarm('from django.core.management import call_command\ncall_command("seed_taxonomy")');
  hub = await startHubDouble();
});
test.afterAll(async () => {
  await hub?.close();
  await removeAccountsWarm(PREFIX);
});

/** What a plan's admin says in each language: its list's columns, its form's labels and the saved plan's name. */
interface PlanWords {
  notice: RegExp;
  columns: string[];
  labels: string[];
  saved: RegExp;
}

/**
 * The staff raise Starter's places by three in its admin page, in the page's language: the form's labels (HUBS-F05's
 * screen, which read «PRICE MONTHLY» and «Por is active» in Spanish), then the list with the notice saying who gets it.
 */
async function raiseStarterPlaces(page: Page, words: PlanWords, key: string): Promise<number> {
  const places = (await starterPlaces(page.request)) + 3;
  await signIn(page.request, STAFF);
  await page.goto('/admin/hubs/plan/?q=starter');
  await page.locator('#result_list tbody th a', { hasText: /^starter$/ }).click();
  await atEverySize(page, `${key}-form`, async () => {
    for (const label of words.labels) {
      await expect(page.locator('#plan_form label', { hasText: new RegExp(`^${label}:?$`) })).toBeVisible();
    }
  });
  await page.locator('input[name="max_users"]').fill(String(places));
  await page.locator('input[name="_save"]').click();
  const told = page.locator('ul.messagelist li', { hasText: words.notice });
  await atEverySize(page, key, async () => {
    await expect(told).toBeVisible();
    await expect(page.locator('ul.messagelist li', { hasText: words.saved })).toBeVisible();
    for (const column of words.columns) {
      await expect(page.locator('#result_list thead')).toContainText(column);
    }
  });
  return places;
}

for (const run of [
  {
    language: 'en',
    locale: 'en-US',
    suffix: '',
    plan: {
      notice: /^\d+ business(es)? on this plan gets? the change within 15 minutes\.$/,
      columns: ['Identifier', 'Monthly price', 'Trial days', 'Only as an upgrade'],
      labels: ['Monthly price', 'Level of modules', 'Support', 'People', 'Devices'],
      saved: /Starter · \d+\.\d{2} €\/month/,
    },
  },
  {
    language: 'es',
    locale: 'es-ES',
    suffix: '-es',
    plan: {
      notice: /^\d+ negocios? con este plan recibe(n)? el cambio en los próximos 15 minutos\.$/,
      columns: ['Identificador', 'Precio al mes', 'Días de prueba', 'Solo como mejora'],
      labels: ['Precio al mes', 'Nivel de módulos', 'Soporte', 'Personas', 'Dispositivos'],
      saved: /Starter · \d+,\d{2} €\/mes/,
    },
  },
]) {
  test.describe(`in ${run.language}`, () => {
    test.use({ locale: run.locale });

    test(`HUBS-G101 (F31): the staff raise the places of a plan in the admin; its businesses get them at the Hub on the next pass${run.suffix}`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const before = await starterPlaces(page.request);
      const id = await businessOnStarter();
      try {
        const places = await raiseStarterPlaces(page, run.plan, `HUBS-G101${run.suffix}`);
        expect(placesInLastSnapshot(hub, id), 'nothing leaves before the pass').toBeUndefined();

        await nextPass();

        await expect.poll(() => placesInLastSnapshot(hub, id)).toBe(places);
        // The Hub answered during the pass (saas#176): a double that cannot answer leaves the snapshot owed, and each
        // call of the pass waits out its timeout (80 queued revocations held the pass ~6 minutes).
        expect(await snapshotOwed(id), 'the SaaS heard the Hub take the snapshot').toBe(false);
      } finally {
        await djangoPrintWarm(`from hubs.models import Plan;Plan.objects.filter(slug="starter").update(max_users=${before})`);
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
