// Members (`/businesses/<id>/members`, mockups `business.html` «members», round 17 §2.7–2.8) in Ioan's
// Chrome, the «Hecho L1» flow of docs/plans/2026-10-13-panel-saas-unificado.md: the owner of Panadería
// López invites an address with no account through «Invite»; the row is a pending invitation with
// the actions the server allows; the invited person, in a browser of their own, follows the links of
// the mails (set a password, then the invitation) and accepts; the owner changes their role and
// removes them. The spec plays the Hub (`startHubDouble`): it sees the snapshot of each change and,
// on the removal, the end of that person's sessions in the business. On Free, inviting past the
// places of the plan is refused, in the dialog and by the server.
import { type Browser, type Page } from '@playwright/test';

import {
  apiPost,
  businessIdOf,
  djangoPrint,
  expect,
  freezeFrontend,
  type HubCall,
  type HubDouble,
  panelAccount,
  seedPanel,
  signIn,
  signInThroughPage,
  startHubDouble,
  test,
  waitForMail,
  watchPageErrors,
} from './fixtures';
import { PANEL_URL } from './project';

/** An address with no account: the invitation creates one, without a password. */
const NEWCOMER = 'e2e-newcomer@example.com';
/** The password the newcomer chooses (allauth's validators: long, not common, not like the email). */
const NEWCOMER_PASSWORD = 'Pan-de-centeno-2026';

interface MemberRow {
  id: string;
  user_id: string;
  email: string;
  role: string;
  status: string;
  actions: string[];
}

interface MemberList {
  rows: MemberRow[];
  seats: { used: number; limit: number | null };
}

/** `hubs.member.list` as `page`'s account reads it (`GET /api/hubs/members`). */
async function membersOf(page: Page, hubId: string): Promise<MemberList> {
  const response = await page.request.get(`/api/hubs/members?hub_id=${hubId}&limit=50&offset=0`);
  expect(response.status(), 'GET /api/hubs/members').toBe(200);
  return (await response.json()) as MemberList;
}

/** The newcomer's row in the server's list (fails when it is not there). */
async function newcomerRow(page: Page, hubId: string): Promise<MemberRow> {
  const row = (await membersOf(page, hubId)).rows.find((one) => one.email === NEWCOMER);
  if (!row) throw new Error(`${NEWCOMER} is not in hubs.member.list`);
  return row;
}

/** The actions that only live in a row's «⋮» (DataTable `menuOnly`: delicate, and confirmed). */
const MENU_ONLY = ['transfer'];

/**
 * A row offers exactly the actions the server computed for it, in its order: a button each, except
 * «Transfer ownership», which only «⋮» offers (opened here, checked and closed). No «⋮» without it.
 */
async function expectActions(page: Page, row: MemberRow): Promise<void> {
  const hook = (action: string) => `members-row-${row.id}-${action}`;
  const inline = row.actions.filter((action) => !MENU_ONLY.includes(action));
  const menu = row.actions.filter((action) => MENU_ONLY.includes(action));
  const buttons = page.getByTestId('members-row').filter({ hasText: row.email }).locator(`[data-testid^="members-row-${row.id}-"]`);
  const expected = [...inline, ...(menu.length ? ['menu'] : [])].map(hook);
  await expect(buttons).toHaveCount(expected.length);
  for (const [index, testid] of expected.entries()) {
    await expect(buttons.nth(index)).toHaveAttribute('data-testid', testid);
  }
  if (!menu.length) return;
  const popover = page.locator('ion-popover.data-table__row-menu');
  await page.getByTestId(hook('menu')).click();
  const items = popover.locator(`[data-testid^="members-row-${row.id}-"]`);
  await expect(items).toHaveCount(menu.length);
  for (const [index, action] of menu.entries()) {
    await expect(items.nth(index)).toHaveAttribute('data-testid', hook(action));
    await expect(items.nth(index)).toBeVisible();
  }
  await page.keyboard.press('Escape');
  await expect(popover).toBeHidden();
}

/** The snapshots the Hub received for `hubId`, in the order they were pushed. */
const snapshots = (hub: HubDouble, hubId: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${hubId}/state`);

/** The session revocations the Hub received, in order. */
const revocations = (hub: HubDouble): HubCall[] =>
  hub.calls.filter((call) => call.method === 'POST' && call.path === '/internal/sessions/revoke');

/** The newcomer as the last snapshot lists them (`undefined` when it does not). */
function newcomerInLastSnapshot(hub: HubDouble, hubId: string): { role: string } | undefined {
  const last = snapshots(hub, hubId).at(-1);
  const members = (last?.body.members ?? []) as Array<{ email: string; role: string }>;
  return members.find((member) => member.email === NEWCOMER);
}

/**
 * The newcomer's own browser: from the invitation mail, «set a password here» (allauth's reset: a
 * second mail with the key), then the invitation link, through the login. Returns the page on
 * `/invitation`, signed in.
 */
async function newcomerArrives(browser: Browser, invitationMail: { reset: string; accept: string }) {
  const context = await browser.newContext({ baseURL: PANEL_URL, locale: 'en-US', viewport: { width: 1280, height: 860 } });
  await freezeFrontend(context);
  const guest = await context.newPage();
  const errors = watchPageErrors(guest);

  await guest.goto(invitationMail.reset);
  const since = Date.now();
  await guest.locator('input[name="email"]').fill(NEWCOMER);
  await guest.locator('input[name="email"]').press('Enter');
  await expect(guest).toHaveURL(/\/accounts\/password\/reset\/done\/$/);
  const key = await waitForMail(NEWCOMER, since, /http:\/\/localhost:8012\/accounts\/password\/reset\/key\/\S+\//);

  await guest.goto(key);
  await guest.locator('input[name="password1"]').fill(NEWCOMER_PASSWORD);
  await guest.locator('input[name="password2"]').fill(NEWCOMER_PASSWORD);
  await guest.locator('input[name="password2"]').press('Enter');
  await expect(guest).toHaveURL(/\/accounts\/password\/reset\/key\/done\/$/);

  // The invitation's link: without a session the shell sends to the login, which comes back.
  await guest.goto(invitationMail.accept);
  await expect(guest).toHaveURL(/\/login\?next=%2Finvitation$/);
  await signInThroughPage(guest, { email: NEWCOMER, password: NEWCOMER_PASSWORD });
  await expect(guest).toHaveURL(/\/invitation$/);
  return { context, guest, errors };
}

test.describe('members', () => {
  let hub: HubDouble;

  test.beforeAll(async () => {
    seedPanel();
    hub = await startHubDouble();
  });
  test.afterAll(async () => {
    await hub?.close();
    seedPanel('clear');
  });

  test('invite a new address → it accepts in its own browser → change its role → remove it; the Hub hears of each', async ({
    page,
    browser,
  }) => {
    test.setTimeout(240_000);
    const errors = watchPageErrors(page);
    await signIn(page.request, panelAccount('several'));
    const id = await businessIdOf(page.request, 'Panadería López');
    await page.goto(`/businesses/${id}/members`);
    const rows = page.getByTestId('members-row');
    const count = page.locator('.data-table__pager-count');
    await expect(rows).toHaveCount(5);
    await expect(count).toHaveText('5');

    // «Invite»: a new address, as Employee (the default).
    await page.getByTestId('members-add').click();
    const modal = page.getByTestId('invite-modal');
    await expect(modal).toContainText('Invite to Panadería López');
    await expect(page.getByTestId('invite-role')).toHaveJSProperty('value', 'hub_employee');
    await page.getByTestId('invite-email').locator('input').fill(NEWCOMER);
    const invitedAt = Date.now();
    await page.getByTestId('invite-modal-submit').click();
    await expect(page.getByText(`Invitation sent to ${NEWCOMER}`)).toBeVisible();
    await expect(modal).toBeHidden();

    // A pending invitation, with the actions the server allows on it (resend and cancel, no remove).
    const row = rows.filter({ hasText: NEWCOMER });
    await expect(row).toContainText('Pending');
    await expect(row).toContainText('Employee');
    await expect(count).toHaveText('6');
    const pending = await newcomerRow(page, id);
    expect(pending.actions).toEqual(['change_role', 'resend', 'cancel']);
    await expectActions(page, pending);
    // An invitation reaches the Hub only once answered.
    expect(snapshots(hub, id)).toEqual([]);

    // The mail: who invites where, the invitation's link and, for a new account, how to get in.
    const reset = await waitForMail(NEWCOMER, invitedAt, /http:\/\/localhost:8012\/accounts\/password\/reset\//);
    const accept = await waitForMail(NEWCOMER, invitedAt, /http:\/\/localhost:8012\/invitation\b/);
    await waitForMail(NEWCOMER, invitedAt, /Panadería López/);

    // The newcomer, in a browser of their own: a password, the login, «Accept and enter».
    const { context, guest, errors: guestErrors } = await newcomerArrives(browser, { reset, accept });
    const visits: string[] = [];
    await guest.route(/^http:\/\/[\w-]+\.localhost:8000\//, async (route) => {
      visits.push(`${route.request().method()} ${route.request().url()}`);
      await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
    });
    await expect(guest.locator('.invite-card').filter({ hasText: 'Panadería López' })).toBeVisible();
    await guest.getByTestId('invitation-accept').click();
    await expect.poll(() => visits).toEqual(['GET http://e2e-panaderia-lopez.localhost:8000/auth/login?next=/']);
    // The Hub gets the snapshot with them in it, as Employee, signed.
    await expect.poll(() => newcomerInLastSnapshot(hub, id)?.role).toBe('hub_employee');
    expect(snapshots(hub, id).every((call) => call.signed)).toBe(true);

    // The owner's list: another account's write reaches it at the live safety re-run (300 s,
    // packages/live) or on reload (live scope = the account, PLAN-SAAS §6 and §3 of the plan): reload.
    await page.reload();
    await expect(row).toContainText('Active');
    const active = await newcomerRow(page, id);
    expect(active.actions).toEqual(['change_role', 'remove', 'transfer']);
    await expectActions(page, active);

    // «Change role» → Manager: the row says so at once (the owner's own write) and the Hub hears it.
    await page.getByTestId(`members-row-${active.id}-change_role`).click();
    const roleModal = page.getByTestId('role-modal');
    await expect(roleModal).toBeVisible();
    await page.getByTestId('role-select').click();
    await page.locator('ion-popover ion-radio', { hasText: 'Manager' }).click();
    await page.getByTestId('role-modal-submit').click();
    await expect(page.getByText('is now Manager')).toBeVisible();
    await expect(roleModal).toBeHidden();
    await expect(row).toContainText('Manager');
    await expect.poll(() => newcomerInLastSnapshot(hub, id)?.role).toBe('hub_manager');

    // «Remove», confirmed: the row goes, the count drops back.
    const pushedBefore = snapshots(hub, id).length;
    const revokedBefore = revocations(hub).length;
    await page.getByTestId(`members-row-${active.id}-remove`).click();
    const removeDialog = page.getByTestId('remove-dialog');
    await expect(removeDialog).toContainText('loses access to Panadería López at once');
    await page.getByTestId('remove-dialog-submit').click();
    await expect(removeDialog).toBeHidden();
    await expect(row).toHaveCount(0);
    await expect(count).toHaveText('5');

    // The Hub: a newer snapshot without them, and the end of their sessions in this business.
    await expect.poll(() => snapshots(hub, id).length).toBeGreaterThan(pushedBefore);
    expect(newcomerInLastSnapshot(hub, id)).toBeUndefined();
    const versions = snapshots(hub, id).map((call) => Number(call.body.version));
    expect(versions).toEqual([...versions].sort((a, b) => a - b));
    expect(new Set(versions).size).toBe(versions.length);
    await expect
      .poll(() => revocations(hub).slice(revokedBefore))
      .toEqual([{ method: 'POST', path: '/internal/sessions/revoke', body: { user_id: active.user_id, hub_id: id }, signed: true }]);

    // The SaaS: hubs.member.list no longer lists them, and their account no longer has the business.
    expect((await membersOf(page, id)).rows.map((one) => one.email)).not.toContain(NEWCOMER);
    const theirs = await guest.request.get('/api/hubs/businesses?limit=50&offset=0');
    expect(theirs.status()).toBe(200);
    expect(((await theirs.json()) as { rows: Array<{ id: string }> }).rows.map((one) => one.id)).not.toContain(id);

    // The revocations queued for them in this business (L1-A2's `SessionRevocation`, once it exists):
    // there, and all delivered, since the Hub took them.
    const queued = djangoPrint(
      [
        'import json',
        'from django.apps import apps',
        'model = next((m for m in apps.get_models() if m.__name__ == "SessionRevocation"), None)',
        `rows = model and model.objects.filter(user_id="${active.user_id}", hub_id="${id}")`,
        'print("absent" if model is None else json.dumps({"total": rows.count(), "pending": rows.filter(delivered_at__isnull=True).count()}))',
      ].join('\n'),
    );
    if (queued === 'absent') {
      test.info().annotations.push({ type: 'skipped assertion', description: 'SessionRevocation does not exist yet (L1-A2)' });
    } else {
      const { total, pending: owed } = JSON.parse(queued) as { total: number; pending: number };
      expect(total).toBeGreaterThanOrEqual(1);
      expect(owed).toBe(0);
    }

    expect(guestErrors).toEqual([]);
    await context.close();
    expect(errors).toEqual([]);
  });

  test('on Free, inviting past the places of the plan is refused in the dialog and by the server', async ({ page }) => {
    const errors = watchPageErrors(page);
    await signIn(page.request, panelAccount('free'));
    const id = await businessIdOf(page.request, 'Frutería Sol');
    const plans = (await (await page.request.get('/api/plans')).json()) as { plans: Array<{ slug: string; max_users: number }> };
    const limit = plans.plans.find((plan) => plan.slug === 'free')?.max_users ?? 0;
    expect(limit, 'Free caps the people of a business').toBeGreaterThan(1);

    // Every place but one taken (the owner holds one), through the API.
    for (let n = 1; n <= limit - 2; n += 1) {
      const invited = await apiPost(page.request, '/api/hubs/members/invite', {
        hub_id: id,
        email: `e2e-seat-${n}@example.com`,
        role: 'hub_employee',
        message: '',
      });
      expect(invited.status(), await invited.text()).toBe(200);
    }
    await page.goto(`/businesses/${id}/members`);
    const seats = page.getByTestId('members-seats');
    await expect(seats).toHaveText(`${limit - 1} of ${limit} places on the plan`);

    // The last place, through «Invite»: the counter follows.
    await page.getByTestId('members-add').click();
    await expect(page.getByTestId('invite-seats')).toHaveText(`${limit - 1} of ${limit} places on the plan`);
    await expect(page.getByTestId('invite-full')).toHaveCount(0);
    await page.getByTestId('invite-email').locator('input').fill('e2e-seat-last@example.com');
    await page.getByTestId('invite-modal-submit').click();
    await expect(page.getByTestId('invite-modal')).toBeHidden();
    await expect(seats).toHaveText(`${limit} of ${limit} places on the plan`);

    // Full: «Invite» says so and sends nothing.
    await page.getByTestId('members-add').click();
    await expect(page.getByTestId('invite-full')).toContainText('The plan has no free places left');
    await expect(page.getByTestId('invite-modal-submit')).toHaveAttribute('aria-disabled', 'true');
    await page.getByTestId('invite-modal-close').click();
    await expect(page.getByTestId('invite-modal')).toBeHidden();

    // The server refuses it too, with the numbers (the dialog is not the only guard).
    const refused = await apiPost(page.request, '/api/hubs/members/invite', {
      hub_id: id,
      email: 'e2e-seat-extra@example.com',
      role: 'hub_employee',
      message: '',
    });
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { error: Record<string, unknown> }).error).toMatchObject({ code: 'hubs.seat_limit', limit, used: limit });

    // Cancelling an invitation frees its place: the counter drops and «Invite» works again.
    const last = (await membersOf(page, id)).rows.find((one) => one.email === 'e2e-seat-last@example.com');
    if (!last) throw new Error('the last invitation is not in hubs.member.list');
    await page.getByTestId(`members-row-${last.id}-cancel`).click();
    await page.getByTestId('remove-dialog-submit').click();
    await expect(page.getByTestId('remove-dialog')).toBeHidden();
    await expect(seats).toHaveText(`${limit - 1} of ${limit} places on the plan`);
    await page.getByTestId('members-add').click();
    await expect(page.getByTestId('invite-full')).toHaveCount(0);
    // «Send invitation» waits for an address (audit 2 R-28), then works again.
    await expect(page.getByTestId('invite-modal-submit')).toHaveAttribute('aria-disabled', 'true');
    await page.getByTestId('invite-email').locator('input').fill('e2e-seat-again@example.com');
    await expect(page.getByTestId('invite-modal-submit')).not.toHaveAttribute('aria-disabled', 'true');
    expect(errors).toEqual([]);
  });
});
