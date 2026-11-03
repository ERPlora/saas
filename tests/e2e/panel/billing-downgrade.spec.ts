// flow: BILLING-F11 BILLING-F14 HUBS-F32 HUBS-F34
// A paying business moves to a cheaper plan (PLAN-SAAS §31), on its screens at the three sizes, against the panel's own
// Django and the rows of billing_seed.py: the Store says what it charges today (nothing) and when it changes, Billing ›
// Subscriptions says it too, «Keep the plan» undoes it from either, and when the paid period ends the plan arrives and
// the Hub takes its new limits. The panel's server has no Stripe here, so the routes that call it run in a process of
// their own with only Stripe doubled (billing_stripe_played.py); that process and the signed webhook write the database
// the page lives on, so what changes on screen is what the server wrote.
//
// «Next invoice» of a row is saas#213's, and its own tests'; nothing here fixes it.
import { execFile, execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import type { Locator, Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { apiPost, businessIdOf, djangoPrint, expect, type HubDouble, panelAccount, qaAccount, settled, shot, sidewaysScroll, signIn, startHubDouble, test, watchPageErrors } from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const BILLING = qaAccount('BILLING', panelAccount('billing'));
const BAKERY = 'Panadería López';
const HUB_URL = `http://127.0.0.1:${HUB_DOUBLE_PORT}`;
const GIB = 1024 ** 3;
const STRIPE_ROUTES = /\/api\/billing\/(checkout\/start|plan\/change|plan\/keep)$/;
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const execFileAsync = promisify(execFile);

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], { cwd: SAAS_DIR, env: djangoEnv(true), stdio: 'pipe' });
}

interface Played {
  status: number;
  body: Record<string, unknown>;
}

/** The Stripe of this spec, in its own process and without blocking this one: the Hub it pushes to is played here (saas#176). */
async function stripePlayed(...args: string[]): Promise<Played> {
  const { stdout } = await execFileAsync('uv', ['run', 'python', 'tests/e2e/panel/billing_stripe_played.py', ...args, HUB_URL], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
  });
  return JSON.parse(stdout.trim().split('\n').at(-1) ?? '') as Played;
}

const callTheRoute = (path: string, body: unknown) => stripePlayed('api', BILLING.email, path, JSON.stringify(body));

/** The page's calls that reach Stripe go through the real routes of `billing_stripe_played.py`. */
async function playStripe(page: Page): Promise<void> {
  await page.route(STRIPE_ROUTES, async (route) => {
    const answer = await callTheRoute(new URL(route.request().url()).pathname, route.request().postDataJSON());
    await route.fulfill({ status: answer.status, json: answer.body });
  });
}

/** The downgrade to Starter as the dialog asks it: its preview, then the change at the preview's moment. */
async function downgradeToStarter(bakery: string): Promise<void> {
  const asked = { hub_id: bakery, plan: 'starter', interval: 'month' };
  const start = await callTheRoute('/api/billing/checkout/start', asked);
  expect(start.status, JSON.stringify(start.body)).toBe(200);
  const preview = start.body.preview as { proration_date: number };
  const change = await callTheRoute('/api/billing/plan/change', { ...asked, proration_date: preview.proration_date });
  expect(change.status, JSON.stringify(change.body)).toBe(200);
}

const held = (bakery: string): { plan: string; waiting: string | null } =>
  JSON.parse(
    djangoPrint(
      `import json;from billing.models import PlanChangeSchedule as W;from hubs.models import Subscription as S;` +
        `print(json.dumps({'plan':S.objects.get(hub_id='${bakery}').plan.slug,'waiting':(W.objects.filter(hub_id='${bakery}').values_list('plan_slug',flat=True).first())}))`,
    ),
  ) as { plan: string; waiting: string | null };

/** The last day of the period, as the panel writes it in `locale` (`billing/frontend/format.ts`). */
function periodEnd(bakery: string, locale: 'en' | 'es'): string {
  const end = djangoPrint(`from hubs.models import Subscription as S;print(S.objects.get(hub_id='${bakery}').current_period_end.isoformat())`);
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(end));
}

const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });
const rowOf = (page: Page, bakery: string): Locator => page.locator(`[data-testid="subscriptions-row"][data-id="${bakery}"]`);

/** `ready` at each size: no sideways scroll, a capture `BILLING-DOWNGRADE-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`BILLING-DOWNGRADE-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.describe('a downgrade waits for the end of the paid period', () => {
  let hub: HubDouble;
  let bakery: string;

  test.beforeAll(async () => {
    hub = await startHubDouble();
  });
  test.afterAll(async () => {
    await hub.close();
    seedBilling('clear');
  });

  test.beforeEach(async ({ page }) => {
    seedBilling('seed');
    await signIn(page.request, BILLING);
    bakery = await businessIdOf(page.request, BAKERY);
    djangoPrint(`from hubs.models import Plan,Subscription as S;print(S.objects.filter(hub_id='${bakery}').update(plan=Plan.objects.get(slug='standard')))`);
    hub.calls.length = 0;
    await playStripe(page);
  });

  test('BILLING-F11: from Standard, the Store charges nothing today and says when Starter starts', async ({ page }) => {
    const errors = watchPageErrors(page);
    const until = periodEnd(bakery, 'en');
    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    const standard = page.getByTestId('plan-standard');
    const starter = page.getByTestId('plan-starter');
    await atEverySize(page, 'store', async () => {
      await expect(standard.getByTestId('plan-current')).toBeVisible();
      await expect(starter.getByTestId('plan-change')).toBeVisible();
    });

    await starter.getByTestId('plan-change').click();
    const dialog = page.getByTestId('proration-modal');
    await expect(dialog.getByTestId('proration-trial')).toContainText(`Nothing is charged today: it is charged from ${until}`);
    await expect(dialog.getByTestId('proration-row')).toHaveCount(0);
    const submit = page.getByTestId('proration-modal-submit');
    await expect(submit).toHaveText('Change plan');
    await page.screenshot({ path: shot('BILLING-DOWNGRADE-dialog-1440') });
    await submit.click();

    await expect(toast(page, `${BAKERY} moves to Starter on ${until}`)).toBeVisible();
    await expect(dialog).toBeHidden();
    await atEverySize(page, 'store-waiting', async () => {
      await expect(standard.getByTestId('plan-note')).toHaveText(`Downgrade scheduled: Standard until ${until}, then Starter.`);
      await expect(standard.getByTestId('plan-keep')).toHaveText('Keep the plan');
      await expect(starter.getByTestId('plan-note')).toHaveText(`The business moves to Starter on ${until}.`);
      await expect(starter.getByTestId('plan-change')).toHaveCount(0);
    });
    expect(held(bakery)).toEqual({ plan: 'standard', waiting: 'starter' });
    expect(hub.calls.filter((call) => call.path.endsWith('/state')), 'the Hub hears nothing until it arrives').toEqual([]);
    expect(errors).toEqual([]);
  });

  test('BILLING-F14: «Keep the plan» on the Store card undoes it', async ({ page }) => {
    const errors = watchPageErrors(page);
    await downgradeToStarter(bakery);
    const until = periodEnd(bakery, 'en');
    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    const standard = page.getByTestId('plan-standard');

    await standard.getByTestId('plan-keep').click();

    await expect(toast(page, `Standard is kept: it renews on ${until}`)).toBeVisible();
    await expect(standard.getByTestId('plan-note')).toHaveCount(0);
    await expect(standard.getByTestId('plan-keep')).toHaveCount(0);
    await expect(page.getByTestId('plan-starter').getByTestId('plan-change')).toBeVisible();
    expect(held(bakery)).toEqual({ plan: 'standard', waiting: null });
    expect(errors).toEqual([]);
  });

  test('BILLING-F11 and BILLING-F14: Subscriptions says the change, and «Keep the plan» on its row undoes it', async ({ page }) => {
    const errors = watchPageErrors(page);
    await downgradeToStarter(bakery);
    const until = periodEnd(bakery, 'en');
    await page.goto('/dashboard/billing/subscriptions');
    const row = rowOf(page, bakery);
    const lead = page.getByTestId(`subscriptions-row-${bakery}-lead`);
    await atEverySize(page, 'subscriptions-waiting', async () => {
      await expect(row.getByTestId('subscription-scheduled')).toHaveText(`Changes to Starter on ${until}`);
      await expect(lead).toHaveText('Keep the plan');
    });

    await lead.click();

    await expect(toast(page, `${BAKERY} stays on Standard`)).toBeVisible();
    await expect(row.getByTestId('subscription-scheduled')).toHaveCount(0);
    await expect(lead).toHaveText('Change plan');
    expect(held(bakery)).toEqual({ plan: 'standard', waiting: null });
    expect(errors).toEqual([]);
  });

  test('BILLING-F11, HUBS-F32 and HUBS-F34: at the end of the period Starter arrives, on the open page and at the Hub', async ({ page }) => {
    const errors = watchPageErrors(page);
    await downgradeToStarter(bakery);
    await page.goto('/dashboard/billing/subscriptions');
    const row = rowOf(page, bakery);
    await expect(row.getByTestId('subscription-scheduled')).toBeVisible();
    await expect(row).toContainText('Standard');

    const arrived = await stripePlayed('arrive', bakery);

    expect(arrived.status, JSON.stringify(arrived.body)).toBe(200);
    await atEverySize(page, 'subscriptions-arrived', async () => {
      await expect(row.getByTestId('subscription-scheduled')).toHaveCount(0);
      await expect(row).toContainText('Starter');
      await expect(row).not.toContainText('Standard');
    });
    expect(held(bakery)).toEqual({ plan: 'starter', waiting: null });

    const photos = hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${bakery}/state`);
    expect(photos.length, 'the Hub takes the new plan').toBeGreaterThan(0);
    const photo = photos.at(-1);
    expect(photo?.signed).toBe(true);
    expect(photo?.body.plan).toMatchObject({ slug: 'starter', max_apps: 40, max_storage_bytes: 5 * GIB });

    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    await atEverySize(page, 'store-arrived', async () => {
      await expect(page.getByTestId('plan-starter').getByTestId('plan-current')).toBeVisible();
      await expect(page.getByTestId('plan-standard').getByTestId('plan-change')).toBeVisible();
      await expect(page.getByTestId('plan-standard').getByTestId('plan-note')).toHaveCount(0);
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-F11 in Spanish: the dialog, the notice, the Store and the row say it in the language of the account', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard');
    expect((await apiPost(page.request, '/api/accounts/preferences', { language: 'es' })).status()).toBe(200);
    const until = periodEnd(bakery, 'es');
    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    const standard = page.getByTestId('plan-standard');
    const starter = page.getByTestId('plan-starter');

    await starter.getByTestId('plan-change').click();
    const dialog = page.getByTestId('proration-modal');
    await expect(dialog.getByTestId('proration-trial')).toContainText(`Hoy no se cobra nada: se cobra desde el ${until}`);
    await page.screenshot({ path: shot('BILLING-DOWNGRADE-es-dialog-1440') });
    await page.getByTestId('proration-modal-submit').click();

    await expect(toast(page, `${BAKERY} pasa a Starter el ${until}`)).toBeVisible();
    await expect(dialog).toBeHidden();
    await atEverySize(page, 'es-store-waiting', async () => {
      await expect(standard.getByTestId('plan-note')).toHaveText(`Bajada programada: Standard hasta el ${until} y después Starter.`);
      await expect(standard.getByTestId('plan-keep')).toHaveText('Mantener el plan');
      await expect(starter.getByTestId('plan-note')).toHaveText(`El negocio pasa a Starter el ${until}.`);
    });

    await page.goto('/dashboard/billing/subscriptions');
    const row = rowOf(page, bakery);
    await atEverySize(page, 'es-subscriptions-waiting', async () => {
      await expect(row.getByTestId('subscription-scheduled')).toHaveText(`Cambia a Starter el ${until}`);
      await expect(page.getByTestId(`subscriptions-row-${bakery}-lead`)).toHaveText('Mantener el plan');
    });
    expect(errors).toEqual([]);
  });
});
