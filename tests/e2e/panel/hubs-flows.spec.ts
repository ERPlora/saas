// The flows of «create the business, wait until it is ready, the list, the panel's home, enter and the other devices»
// (hubs/WORKBOOK.md) on their screens, at the three sizes (390×844,
// 834×1112, 1440×900). Each test names its flow of hubs/WORKBOOK.md in its title; F07, F08 and F14 have no screen.
//
// Two parts:
// - against the panel's own Django (project.ts), whose calls to the Hub go nowhere: the jump into a business is
//   caught at the Hub's door (`page.route`), so the spec reads where the window was sent;
// - «the real Hub» (`E2E_REAL_HUB=1`): a Hub runserver listening on this stack's Hub port, so the sign-up reaches it,
//   it reports the business ready and the window really goes in (README «El Hub real de la e2e»). Without the
//   variable those tests are skipped, and say so; with it, HUBS-F01 and HUBS-F02 are (they need the business to
//   stay «Preparing», and the real Hub makes it ready at once). So the spec runs twice: once without, once with.
// Accounts of this spec: `e2e-hubs1-…@example.com` (panel_seed.py's `clear` removes every `e2e-…@example.com`).
import { type Page } from '@playwright/test';

import {
  businessIdOf,
  captureAtEverySize,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  panelAccount,
  realHubPrint,
  removeAccountsWarm,
  runSeedWarm,
  signIn,
  test,
  waitForMail,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const atEverySize = captureAtEverySize('APP-HUBS-1');

const PREFIX = 'e2e-hubs1-';
const PASSWORD = 'Masa-madre-y-centeno-26';

/** The page Ionic shows (it keeps the pages it left in the DOM, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** A fresh account of this spec, its address proven, signed in on `page`. */
async function freshAccount(page: Page, name: string): Promise<string> {
  const email = `${PREFIX}${name}-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { language: 'en' });
  await signIn(page.request, { email, password: PASSWORD });
  return email;
}

/** The Hub's door, caught: every request to a business's host is answered here and remembered. */
async function hubDoor(page: Page): Promise<string[]> {
  const visits: string[] = [];
  await page.route(/^http:\/\/[\w-]+\.localhost:\d+\//, async (route) => {
    visits.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
  });
  return visits;
}

/**
 * What the SaaS keeps of the business called `name` among those of `page`'s account, through the panel's API:
 * `status plan owner-email` (its owner, from its people: `hubs.member.list`).
 */
async function businessRow(page: Page, name: string): Promise<string> {
  const id = await businessIdOf(page.request, name);
  const detail = await page.request.get(`/api/hubs/businesses/detail?id=${id}`);
  expect(detail.status(), await detail.text()).toBe(200);
  const { status, plan } = (await detail.json()) as { status: string; plan: { slug: string } | null };
  const people = await page.request.get(`/api/hubs/members?hub_id=${id}&limit=50&offset=0`);
  expect(people.status(), await people.text()).toBe(200);
  const owners = ((await people.json()) as { rows: Array<{ email: string; role: string }> }).rows.filter((row) => row.role === 'hub_owner');
  return `${status} ${plan?.slug} ${owners.map((row) => row.email).join(',')}`;
}

/** The id of the plan Starter, for its admin page: no screen of the panel shows it, so Django says it once here. */
let starterId: string;

// Django's boots on no test's clock (saas#354): the warm Django, and what only Django knows, once here.
test.beforeAll(async () => {
  await removeAccountsWarm(PREFIX);
  await runSeedWarm('panel_seed.py', 'seed');
  starterId = await djangoPrintWarm('from hubs.models import Plan;print(Plan.objects.get(slug="starter").pk)');
});
test.afterAll(async () => {
  await removeAccountsWarm(PREFIX);
  await runSeedWarm('panel_seed.py', 'clear');
});

test('HUBS-F01: the free business with a single question, then «Preparing»', async ({ page }) => {
  test.skip(!!process.env.E2E_REAL_HUB, 'the real Hub makes the business ready at once; this needs it «Preparing»');
  const errors = watchPageErrors(page);
  const email = await freshAccount(page, 'first');
  await page.goto('/launch');
  await atEverySize(page, 'HUBS-G65', async () => {
    await expect(page.getByRole('heading', { name: 'Create your business' })).toBeVisible();
    await expect(page.getByTestId('create-name')).toBeVisible();
  });
  await expect(page.getByTestId('create-country')).toHaveJSProperty('value', 'ES');
  await page.getByTestId('create-name').locator('input').fill('Horno Hubs Uno E2E');
  await expect(page.getByTestId('create-address')).toContainText('Your address will be horno-hubs-uno-e2e');
  await page.getByTestId('create-submit').click();
  await expect(page.getByRole('heading', { name: 'Preparing Horno Hubs Uno E2E' })).toBeVisible();
  await atEverySize(page, 'HUBS-G65-preparing', async () => {
    await expect(page.getByText('It opens by itself when it finishes')).toBeVisible();
  });
  expect(await businessRow(page, 'Horno Hubs Uno E2E')).toBe(`preparing free ${email}`);
  expect(errors).toEqual([]);
});

test('HUBS-F02: from the installed app, its start /shell/ is the same sign-up', async ({ page }) => {
  test.skip(!!process.env.E2E_REAL_HUB, 'the real Hub makes the business ready at once; this needs it «Preparing»');
  const errors = watchPageErrors(page);
  await freshAccount(page, 'app');
  await page.goto('/shell/?surface=desktop');
  await expect(page.locator('html')).toHaveClass(/in-app-shell/);
  await atEverySize(page, 'HUBS-G66', async () => {
    await expect(page.getByRole('heading', { name: 'Create your business' })).toBeVisible();
  });
  await page.getByTestId('create-name').locator('input').fill('Taller Hubs App E2E');
  await page.getByTestId('create-submit').click();
  await expect(page.getByRole('heading', { name: 'Preparing Taller Hubs App E2E' })).toBeVisible();
  await expect(page).toHaveURL(/\/shell\/\?surface=desktop$/);
  expect((await businessRow(page, 'Taller Hubs App E2E')).split(' ').slice(0, 2)).toEqual(['preparing', 'free']);
  expect(errors).toEqual([]);
});

test('HUBS-F03: a paid business is born on Free and «Upgrade plan» opens the Store; a second one waits for a paid plan', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('one'));
  const id = await businessIdOf(page.request, 'Panadería López');
  await page.goto('/dashboard/businesses');
  await shown(page).getByTestId('businesses-add').click();
  await atEverySize(page, 'HUBS-G67', async () => {
    await expect(page.getByTestId('create-free-limit')).toContainText('You already have a free business');
  });
  await page.getByTestId('create-free-limit-store').click();
  await expect(page).toHaveURL(new RegExp(`/dashboard/store/plans\\?business=${id}$`));
  await page.goto(`/dashboard/businesses/${id}/summary`);
  await expect(shown(page).getByTestId('summary-plan-store')).toHaveText(/Upgrade plan/);
  await atEverySize(page, 'HUBS-G67-summary', async () => {
    await expect(shown(page).getByTestId('summary-plan')).toBeVisible();
  });
  await shown(page).getByTestId('summary-plan-store').click();
  await expect(page).toHaveURL(new RegExp(`/dashboard/store/plans\\?business=${id}$`));
  expect(errors).toEqual([]);
});

test('HUBS-F09: the list with each status, the deleted one with «Recover», and the old addresses lead to it', async ({ page }) => {
  const errors = watchPageErrors(page);
  // A business deleted 5 days ago: no screen makes one in the past.
  await djangoPrintWarm(
    [
      'from datetime import timedelta',
      'from django.contrib.auth import get_user_model',
      'from django.utils import timezone',
      'from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription',
      'user = get_user_model().objects.get(email="e2e-several@example.com")',
      'now = timezone.now()',
      'profile = BillingProfile.objects.create(owner=user, billing_email=user.email, billing_country="ES")',
      'hub = Hub.objects.create(slug="e2e-several-bar-antiguo", name="Bar Antiguo", country="ES", timezone="Europe/Madrid",',
      '    language="es", billing_profile=profile, status="deleting", ready_at=now - timedelta(days=90),',
      '    deletion_requested_at=now - timedelta(days=5))',
      'Subscription.objects.create(hub=hub, plan=Plan.objects.get(slug="free"), status="active", current_period_start=now)',
      'HubMember.objects.create(hub=hub, user=user, role="hub_owner", joined_at=now, accepted_at=now)',
    ].join('\n'),
  );
  await signIn(page.request, panelAccount('several'));
  for (const old of ['/dashboard/hubs/active/', '/dashboard/hubs/inactive/']) {
    await page.goto(old);
    await expect(page).toHaveURL(/\/dashboard\/businesses$/);
  }
  await atEverySize(page, 'HUBS-G69', async () => {
    await expect(shown(page).getByText('Bar Antiguo').first()).toBeVisible();
  });
  const rows = shown(page).getByTestId('businesses-row');
  await expect(rows.filter({ hasText: 'Panadería López' })).toContainText('Active');
  await expect(rows.filter({ hasText: 'Bar La Plaza' })).toContainText('Payment due');
  await expect(rows.filter({ hasText: 'Café Central' })).toContainText('Preparing');
  const deleted = rows.filter({ hasText: 'Bar Antiguo' });
  await expect(deleted).toContainText('You can recover it until');
  await expect(deleted.getByRole('button', { name: 'Recover Bar Antiguo' })).toBeVisible();
  await expect(deleted.getByRole('button', { name: /^Open/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('HUBS-F10: the panel’s home is Businesses, from «Go to the panel» and from the old overview', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('one'));
  await page.goto('/launch');
  await page.getByTestId('launch-panel').click();
  await expect(page).toHaveURL(/\/dashboard\/businesses$/);
  await page.goto('/dashboard/');
  await expect(page).toHaveURL(/\/dashboard\/businesses$/);
  await atEverySize(page, 'HUBS-G84', async () => {
    await expect(shown(page).getByTestId('businesses-row').or(shown(page).locator('.data-table__card')).first()).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test('HUBS-F11: «Open» from erplora.com sends the window to the business’s start of the jump, without the app’s mark', async ({ page }) => {
  const errors = watchPageErrors(page);
  const visits = await hubDoor(page);
  await signIn(page.request, panelAccount('one'));
  await page.goto('/launch');
  await atEverySize(page, 'HUBS-G70', async () => {
    await expect(page.getByTestId('launch-business')).toContainText('Panadería López');
  });
  await page.getByTestId('launch-open').click();
  await expect.poll(() => visits).toEqual([expect.stringMatching(/^http:\/\/e2e-one-panaderia\.localhost:\d+\/auth\/login\?next=\/$/)]);
  expect(errors).toEqual([]);
});

test('HUBS-F12: in the installed app the launcher chooses and «Open» carries shell=1; /shell/open/<id>/ too', async ({ page }) => {
  const errors = watchPageErrors(page);
  const visits = await hubDoor(page);
  await signIn(page.request, panelAccount('several'));
  const id = await businessIdOf(page.request, 'Panadería López');
  await page.goto('/shell/?surface=desktop');
  await atEverySize(page, 'HUBS-G71', async () => {
    await expect(page.getByRole('heading', { name: 'Where are you working today?' })).toBeVisible();
  });
  await page.getByTestId('launch-business').filter({ hasText: 'Panadería López' }).getByTestId('launch-open').click();
  await expect.poll(() => visits).toEqual([expect.stringMatching(/\/auth\/login\?next=\/&shell=1$/)]);
  // The door for a link: its 302 (Playwright does not route the redirect a navigation follows, so it is read here).
  const door = await page.request.get(`/shell/open/${id}/`, { maxRedirects: 0 });
  expect(door.status()).toBe(302);
  expect(door.headers().location).toMatch(/^http:\/\/e2e-[\w-]+\.localhost:\d+\/auth\/login\?next=\/&shell=1$/);
  const foreign = await page.request.get(`/shell/open/${await otherBusiness(page)}/`, { maxRedirects: 0 });
  expect(foreign.status()).toBe(404);
  expect(errors).toEqual([]);
});

/** A business «several» is no member of (Bar Norte invites it, unanswered): its invitation, as the panel lists it. */
async function otherBusiness(page: Page): Promise<string> {
  const listed = await page.request.get('/api/hubs/invitations');
  expect(listed.status(), await listed.text()).toBe(200);
  const { invitations } = (await listed.json()) as { invitations: Array<{ hub: { id: string; name: string } }> };
  const invited = invitations.find((invitation) => invitation.hub.name === 'Bar Norte');
  if (!invited) throw new Error('no invitation of Bar Norte for this account');
  return invited.hub.id;
}

test('HUBS-F13: «On your devices» shares the business’s address and the apps', async ({ page, context }) => {
  const errors = watchPageErrors(page);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await signIn(page.request, panelAccount('one'));
  const id = await businessIdOf(page.request, 'Panadería López');
  await page.goto(`/dashboard/hubs/${id}/qr/`);
  await expect(page).toHaveURL(new RegExp(`/dashboard/businesses/${id}/summary$`));
  const card = shown(page).getByTestId('device-access-card');
  await atEverySize(page, 'HUBS-G72', async () => {
    await expect(card).toContainText('On your devices');
  });
  await expect(card.getByTestId('copy-value')).toContainText('e2e-one-panaderia');
  await expect(card.getByTestId('device-windows')).toBeVisible();
  await card.getByTestId('copy-button').click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain('e2e-one-panaderia');
  expect(errors).toEqual([]);
});

test('HUBS-F05: the staff keep each plan’s texts in English and in Spanish in the admin', async ({ page }) => {
  const errors = watchPageErrors(page);
  const email = `${PREFIX}staff-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { role: 'superuser' });
  await signIn(page.request, { email, password: PASSWORD });
  await page.goto(`/admin/hubs/plan/${starterId}/change/`);
  await atEverySize(page, 'HUBS-G43', async () => {
    await expect(page.locator('#id_name_en')).toBeVisible();
  });
  for (const field of ['name', 'description', 'features', 'featured_label']) {
    await expect(page.locator(`#id_${field}_en`)).toBeAttached();
    await expect(page.locator(`#id_${field}_es`)).toBeAttached();
  }
  expect(errors).toEqual([]);
});

// ── The real Hub ──────────────────────────────────────────────────────────────────────────────────────────────
// A Hub runserver on HUB_DOUBLE_PORT, its `SAAS_URL` this stack's panel, the same INTERNAL_SHARED_SECRET, and this
// run's `HUB_CALLBACK_TEMPLATE` pointing at it (README «El Hub real de la e2e»). `HUB_DIR` is its checkout and
// `HUB_DB_NAME` its database (its `manage.py` puts a business back to «being prepared» for HUBS-F06).
test.describe('against the real Hub', () => {
  test.skip(!process.env.E2E_REAL_HUB, 'needs a real Hub on the stack’s Hub port (README «El Hub real de la e2e»)');

  const hubUrl = (slug: string, path = '/') => `http://${slug}.localhost:${HUB_DOUBLE_PORT}${path}`;


  test('HUBS-F04: created, the Hub reports it ready and the launcher goes into the business by itself; «is ready» arrives', async ({ page }) => {
    const errors = watchPageErrors(page);
    const since = Date.now();
    const email = await freshAccount(page, 'real');
    await page.goto('/launch');
    await page.getByTestId('create-name').locator('input').fill('Bodega Hub Real E2E');
    await page.getByTestId('create-submit').click();
    await expect(page.getByRole('heading', { name: 'Preparing Bodega Hub Real E2E' })).toBeVisible();
    await page.waitForURL(new RegExp(`^http://bodega-hub-real-e2e\\.localhost:${HUB_DOUBLE_PORT}/`), { timeout: 60_000 });
    await expect(page.getByTestId('shell-account').or(page.locator('ion-app')).first()).toBeVisible();
    await atEverySize(page, 'HUBS-G68', async () => {
      await expect(page).toHaveURL(/bodega-hub-real-e2e\.localhost/);
    });
    expect(await businessRow(page, 'Bodega Hub Real E2E')).toBe(`active free ${email}`);
    const link = await waitForMail(email, since, /http:\/\/bodega-hub-real-e2e\.localhost:\d+\/auth\/login\?next=\/\S*/);
    expect(link).toContain(`bodega-hub-real-e2e.localhost:${HUB_DOUBLE_PORT}`);
    expect(errors).toEqual([]);
  });

  test('HUBS-F11: «Open» in Businesses enters the business through the jump', async ({ page }) => {
    await freshAccount(page, 'open');
    await page.goto('/launch');
    await page.getByTestId('create-name').locator('input').fill('Granja Hub Real E2E');
    await page.getByTestId('create-submit').click();
    await page.waitForURL(/granja-hub-real-e2e\.localhost/, { timeout: 60_000 });
    await page.goto(`/dashboard/businesses`);
    await shown(page).getByTestId('businesses-row').filter({ hasText: 'Granja Hub Real E2E' }).getByRole('button', { name: 'Open Granja Hub Real E2E' }).click();
    await page.waitForURL(new RegExp(`^http://granja-hub-real-e2e\\.localhost:${HUB_DOUBLE_PORT}/(?!auth)`), { timeout: 30_000 });
  });

  test('HUBS-F12: from the app, the jump carries shell=1 and lands in the business', async ({ page }) => {
    await freshAccount(page, 'shell');
    await page.goto('/shell/?surface=desktop');
    await page.getByTestId('create-name').locator('input').fill('Lonja Hub Real E2E');
    const marked = page.waitForRequest(/lonja-hub-real-e2e\.localhost:\d+\/auth\/login\?next=\/&shell=1$/, { timeout: 60_000 });
    await page.getByTestId('create-submit').click();
    await marked;
    await page.waitForURL(new RegExp(`^http://lonja-hub-real-e2e\\.localhost:${HUB_DOUBLE_PORT}/(?!auth)`), { timeout: 30_000 });
  });

  test('HUBS-F06: the address of a business being prepared says so and refreshes by itself', async ({ page }) => {
    await freshAccount(page, 'prep');
    await page.goto('/launch');
    await page.getByTestId('create-name').locator('input').fill('Molino Hub Real E2E');
    await page.getByTestId('create-submit').click();
    await page.waitForURL(/molino-hub-real-e2e\.localhost/, { timeout: 60_000 });
    await realHubPrint('from base.models import Hub;Hub.objects.filter(slug="molino-hub-real-e2e").update(status="requested")');
    try {
      await page.goto(hubUrl('molino-hub-real-e2e'));
      await atEverySize(page, 'HUBS-G98', async () => {
        await expect(page.getByRole('heading', { name: 'Your business is being prepared' })).toBeVisible();
      });
      await expect(page.locator('meta[http-equiv="refresh"]')).toHaveAttribute('content', '10');
    } finally {
      await realHubPrint('from base.models import Hub;Hub.objects.filter(slug="molino-hub-real-e2e").update(status="ready")');
    }
    await expect(page.getByRole('heading', { name: 'Your business is being prepared' })).toHaveCount(0, { timeout: 20_000 });
  });
});
