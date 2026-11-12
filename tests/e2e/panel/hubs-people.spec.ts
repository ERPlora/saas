// The flows of «the people of a business» (hubs/WORKBOOK.md) on their screens, at the three
// sizes (390×844, 834×1112, 1440×900). Each test names its flow by its registry key; in
// hubs/WORKBOOK.md: G78=F24 (invite), G79=F25 (accept), G80=F26 (change the role), G81 and G64=F27 (remove, and the
// end of their sessions in the Hub), G82=F28 (hand the business over), G83=F29 (the people of a business), G03=F30
// (the accesses in the admin).
//
// The spec plays the Hub (`startHubDouble`, as panel/members.spec.ts): it sees the snapshot of each change and the
// end of a person's sessions in the business; the jump into a business is answered here (no Hub runs). Stripe does not
// run either (no keys in the e2e stack): what calls it runs in the server's own code with Stripe at its boundary
// (`withStripe`, the double of the Python tests), and the page plays Stripe.js and the one call that opens a payment
// (`playStripe` of fixtures.ts). Each test has
// its own accounts (`e2e-hubs3-…@example.com`, their address proven) and its own business, created through the API as
// the panel creates it; the people join it through the operations (invite, then accept), never written by hand.
import { type Browser, type Page } from '@playwright/test';

import { horizontalOverflow } from '../horizontal-overflow';
import {
  apiPost,
  captureAtEverySize,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  freezeFrontend,
  type HubCall,
  type HubDouble,
  MAIL_LOGO_URL,
  mailPartsOf,
  onlyTheMailLogo,
  payInStripe,
  playStripe,
  settled,
  shot,
  signIn,
  signInAs,
  startHubDouble,
  test,
  VIEWPORTS,
  waitForMail,
  watchPageErrors,
} from './fixtures';
import { PANEL_URL } from './project';

const atEverySize = captureAtEverySize('APP-HUBS-3');

const PREFIX = 'e2e-hubs3-';
const PASSWORD = 'Masa-madre-y-centeno-26';
/** The panel's origin as a pattern: the mails link to the server that sent them, the run's (stack.ts). */
const PANEL = PANEL_URL.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

interface Account {
  email: string;
  name: string;
}

interface MemberRow {
  id: string;
  user_id: string;
  email: string;
  role: string;
  status: string;
  actions: string[];
}

/** A fresh account of this spec, its address proven, called `first last`, in English (written by the warm Django). */
async function account(who: string, first: string, last: string): Promise<Account> {
  const email = `${PREFIX}${who}-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { firstName: first, lastName: last, language: 'en' });
  return { email, name: `${first} ${last}` };
}

/**
 * `owner` signed in on `page`, with a business called `name`, ready as the Hub leaves it: its registry taken (the
 * double only plays the snapshot and the end of sessions) and its callback received. From here each change of its
 * people pushes the snapshot.
 */
async function businessOf(page: Page, owner: Account, name: string): Promise<string> {
  await signIn(page.request, { email: owner.email, password: PASSWORD });
  const created = await apiPost(page.request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), 'POST /api/hubs/businesses').toBe(201);
  const { id } = (await created.json()) as { id: string };
  await djangoPrintWarm(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub',
      `Hub.objects.filter(pk="${id}").update(status="active", ready_at=timezone.now(), pending_hub_call="")`,
    ].join('\n'),
  );
  return id;
}

/** `person`'s own browser, signed in, in English. */
async function browserOf(browser: Browser, person: Account) {
  const context = await browser.newContext({ baseURL: PANEL_URL, locale: 'en-US', viewport: { width: 1440, height: 900 } });
  await freezeFrontend(context);
  const page = await context.newPage();
  const errors = watchPageErrors(page);
  await signIn(page.request, { email: person.email, password: PASSWORD });
  return { context, page, errors };
}

/** `person` joins business `id` as `role`: the owner on `page` invites them and they accept, through the API. */
async function joins(page: Page, browser: Browser, id: string, person: Account, role: string): Promise<void> {
  const invited = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: person.email, role, message: '' });
  expect(invited.status(), await invited.text()).toBe(200);
  const { context, page: theirs } = await browserOf(browser, person);
  const accepted = await apiPost(theirs.request, '/api/hubs/invitations/accept', { id: ((await invited.json()) as MemberRow).id });
  expect(accepted.status(), await accepted.text()).toBe(200);
  await context.close();
}

/** `hubs.member.list` as `page`'s account reads it. */
async function membersOf(page: Page, id: string): Promise<MemberRow[]> {
  const response = await page.request.get(`/api/hubs/members?hub_id=${id}&limit=50&offset=0`);
  expect(response.status(), 'GET /api/hubs/members').toBe(200);
  return ((await response.json()) as { rows: MemberRow[] }).rows;
}

async function rowOf(page: Page, id: string, email: string): Promise<MemberRow> {
  const row = (await membersOf(page, id)).find((one) => one.email === email);
  if (!row) throw new Error(`${email} is not in hubs.member.list`);
  return row;
}

/**
 * The HTML part of the newest mail to `to` since `since` whose subject has `subject`, read from the panel's mail folder
 * as a mail client reads it (as panel/accounts-mails.spec.ts), painted at every size: text and HTML, the logo, every
 * line of the text, nothing fetched but the logo, no sideways scroll, and its capture.
 */
async function paintMail(browser: Browser, key: string, to: string, since: number, subject: string, language: string): Promise<void> {
  const mail = await mailPartsOf(to, since, subject);
  expect(mail.parts, `${key} is text and HTML`).toEqual(['text/plain', 'text/html']);
  const page = await browser.newPage();
  const fetched = await onlyTheMailLogo(page);
  for (const size of VIEWPORTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.setContent(mail.html, { waitUntil: 'load' });
    await settled(page);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    await expect(page.locator('img[alt="ERPlora"]')).toBeVisible();
    const shownText = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
    for (const line of mail.text.split('\n')) {
      const words = line.replace(/\s+/g, ' ').trim();
      if (words) expect(shownText, `${key} at ${size.width} shows «${words}»`).toContain(words);
    }
    expect(await horizontalOverflow(page), `${key} scrolls sideways at ${size.width}`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`APP-HUBS-3-${key}-${size.width}`), fullPage: true });
  }
  expect([...new Set(fetched)], `${key} fetches only the logo`).toEqual([MAIL_LOGO_URL]);
  await page.close();
}

/** The page Ionic shows (it keeps the pages it left in the DOM, hidden). */
const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** The snapshots the Hub received for `id`, in the order they were pushed. */
const snapshots = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${id}/state`);

/** `email`'s role in the last snapshot of `id` (`undefined` when it does not list them). */
function roleInLastSnapshot(hub: HubDouble, id: string, email: string): string | undefined {
  const members = (snapshots(hub, id).at(-1)?.body.members ?? []) as Array<{ email: string; role: string }>;
  return members.find((member) => member.email === email)?.role;
}

/** The ends of sessions the Hub received for `id`. */
const revocations = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'POST' && call.path === '/internal/sessions/revoke' && call.body.hub_id === id);

/**
 * `code` run in the server's own code with Stripe at its boundary: `double` (billing/tests/stripe_double.py, as the Python
 * tests) answers what Stripe would; the operations of hubs and billing are the real ones, on this run's database. The
 * warm Django runs it, and it outlives the snippet: Stripe's keys and client are put back as they were when it ends.
 */
async function withStripe(code: string[]): Promise<string> {
  return djangoPrintWarm(
    [
      'from unittest import mock',
      'from django.test import override_settings',
      'from billing import stripe_service',
      'from billing.tests.stripe_double import StripeDouble, item, subscription',
      'double = StripeDouble()',
      'with override_settings(STRIPE_SECRET_KEY="rk_test_double", STRIPE_PUBLISHABLE_KEY="pk_test_double"), mock.patch.object(stripe_service, "client", lambda: double):',
      ...code.map((line) => `    ${line}`),
    ].join('\n'),
  );
}

/** What this spec leaves behind, written by the warm Django (its first call, in `beforeAll`, starts it). */
async function removeOwnRows(): Promise<void> {
  await djangoPrintWarm(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import Hub, SessionRevocation',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `users = get_user_model().objects.filter(email__startswith="${PREFIX}")`,
      'SessionRevocation.objects.filter(user_id__in=list(users.values_list("pk", flat=True))).delete()',
      'users.delete()',
    ].join('\n'),
  );
}

let hub: HubDouble;

test.beforeAll(async () => {
  await removeOwnRows();
  hub = await startHubDouble();
});
test.afterAll(async () => {
  await hub?.close();
  await removeOwnRows();
});

test('HUBS-G78: an address the schema refuses says why on its field, and on top to look at it until it is corrected, in the language of the account', async ({ page }) => {
  const errors = watchPageErrors(page);
  const id = await businessOf(page, await account('invite-refused', 'Olga', 'Ruiz'), 'Bar Refused');
  for (const { language, notice, reason } of [
    { language: 'en', notice: 'Check the highlighted details.', reason: 'Enter a valid email address.' },
    { language: 'es', notice: 'Revisa los datos marcados.', reason: 'Introduce un correo válido.' },
  ]) {
    expect((await apiPost(page.request, '/api/accounts/preferences', { language })).status()).toBe(200);
    await page.goto(`/dashboard/businesses/${id}/members`);
    await shown(page).getByTestId('members-add').click();
    const modal = page.getByTestId('invite-modal');
    // The shape of an address, so the button lets it go; too long for the server.
    await page.getByTestId('invite-email').locator('input').fill(`${'a'.repeat(250)}@example.com`);
    await page.getByTestId('invite-modal-submit').click();
    await expect(modal.getByTestId('invite-modal-error')).toHaveText(notice);
    await expect(page.getByTestId('invite-email')).toContainText(reason);
    await page.getByTestId('invite-email').locator('input').fill(`${PREFIX}corrected-${Date.now()}@example.com`);
    await expect(modal.getByTestId('invite-modal-error')).toBeHidden();
  }
  expect(errors).toEqual([]);
});

test('HUBS-G78: the owner invites a person from «Team»; the invitation waits with «Resend» and «Cancel invitation»', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('invite-owner', 'Olga', 'Ruiz');
  const id = await businessOf(page, owner, 'Bar Manolo');
  const invitee = `${PREFIX}invitee-${Date.now()}@example.com`;
  await page.goto(`/dashboard/businesses/${id}/members`);
  const rows = shown(page).getByTestId('members-row');
  await expect(rows).toHaveCount(1);

  await shown(page).getByTestId('members-add').click();
  const modal = page.getByTestId('invite-modal');
  await atEverySize(page, 'HUBS-G78', async () => {
    await expect(modal).toContainText('Invite to Bar Manolo');
    await expect(page.getByTestId('invite-seats')).toHaveText('1 of 3 places on the plan');
  });
  // Employee by default; the owner hands out admin too.
  await expect(page.getByTestId('invite-role')).toHaveJSProperty('value', 'hub_employee');
  await page.getByTestId('invite-email').locator('input').fill(invitee);
  const since = Date.now();
  await page.getByTestId('invite-modal-submit').click();
  await expect(page.getByText(`Invitation sent to ${invitee}`)).toBeVisible();
  await expect(modal).toBeHidden();

  const row = rows.filter({ hasText: invitee });
  await expect(row).toContainText('Pending');
  expect((await rowOf(page, id, invitee)).actions).toEqual(['change_role', 'resend', 'cancel']);
  // Who invites where, the invitation's link and, for an address without an account, how to get in.
  await waitForMail(invitee, since, new RegExp(`${PANEL}/invitation\\b`));
  await waitForMail(invitee, since, new RegExp(`${PANEL}/password/reset(?=\\s|$)`, 'm'));
  // The invitation as the person gets it: branded, text and HTML (ACCOUNTS-F46).
  await paintMail(browser, 'HUBS-G78-mail', invitee, since, 'invited you to Bar Manolo', 'en');
  // An invitation reaches the Hub only once answered.
  expect(roleInLastSnapshot(hub, id, invitee)).toBeUndefined();

  // Inviting the same address again is refused by the server, with its code.
  const again = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: invitee, role: 'hub_employee', message: '' });
  expect(again.status()).toBe(409);
  expect(((await again.json()) as { error: { code: string } }).error.code).toBe('hubs.already_invited');
  expect(errors).toEqual([]);
});

test('HUBS-G79: the invited person accepts in «You have been invited» and goes into the business', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('accept-owner', 'Olga', 'Ruiz');
  const ana = await account('accept-ana', 'Ana', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  const invited = await apiPost(page.request, '/api/hubs/members/invite', {
    hub_id: id,
    email: ana.email,
    role: 'hub_manager',
    message: '',
  });
  expect(invited.status(), await invited.text()).toBe(200);

  const { context, page: guest, errors: guestErrors } = await browserOf(browser, ana);
  const visits: string[] = [];
  await guest.route(/^http:\/\/[\w-]+\.localhost:8000\//, async (route) => {
    visits.push(`${route.request().method()} ${route.request().url()}`);
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
  });
  await guest.goto('/invitation');
  const card = guest.locator('.invite-card').filter({ hasText: 'Bar Manolo' });
  await atEverySize(guest, 'HUBS-G79', async () => {
    await expect(card).toContainText('Olga Ruiz invites you · Manager');
    await expect(guest.getByTestId('invitation-foot')).toHaveText('The owner or an admin of the business can take this access away.');
  });
  await card.getByTestId('invitation-accept').click();
  await expect.poll(() => visits).toEqual([expect.stringMatching(/^GET http:\/\/bar-manolo[\w-]*\.localhost:8000\/auth\/login\?next=\/$/)]);
  // Inside: Active for the owner, and the Hub's snapshot lists them as Manager.
  expect((await rowOf(page, id, ana.email)).status).toBe('active');
  await expect.poll(() => roleInLastSnapshot(hub, id, ana.email)).toBe('hub_manager');
  // A second «Accept» of the same invitation grants nothing more: there is no invitation left to answer.
  const replay = await apiPost(guest.request, '/api/hubs/invitations/accept', { id: ((await invited.json()) as MemberRow).id });
  expect(replay.status()).toBe(404);
  await context.close();
  expect(guestErrors).toEqual([]);
  expect(errors).toEqual([]);
});

test('HUBS-G80: the owner changes the role of a person; the Hub hears it and ends their session there', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('role-owner', 'Olga', 'Ruiz');
  const ana = await account('role-ana', 'Ana', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, ana, 'hub_employee');
  const member = await rowOf(page, id, ana.email);
  expect(member.actions).toEqual(['change_role', 'remove', 'transfer']);

  await page.goto(`/dashboard/businesses/${id}/members`);
  await shown(page).getByTestId(`members-row-${member.id}-change_role`).click();
  const modal = page.getByTestId('role-modal');
  await atEverySize(page, 'HUBS-G80', async () => {
    await expect(modal).toContainText('Change the role of Ana Gil');
  });
  const revokedBefore = revocations(hub, id).length;
  await page.getByTestId('role-select').click();
  await page.locator('ion-popover ion-radio', { hasText: 'Admin' }).click();
  await page.getByTestId('role-modal-submit').click();
  await expect(page.getByText('Ana Gil is now Admin')).toBeVisible();
  await expect(modal).toBeHidden();
  await expect(shown(page).getByTestId('members-row').filter({ hasText: ana.email })).toContainText('Admin');
  await expect.poll(() => roleInLastSnapshot(hub, id, ana.email)).toBe('hub_admin');
  // The role travels in the Hub's session: the SaaS asks the Hub to end it, in this business only.
  await expect
    .poll(() => revocations(hub, id).slice(revokedBefore).map((call) => call.body))
    .toEqual([{ user_id: member.user_id, hub_id: id }]);

  // As admin, Ana cannot hand out admin nor touch the owner: the server refuses it.
  const { context, page: theirs } = await browserOf(browser, ana);
  const ownerRow = await rowOf(theirs, id, owner.email);
  expect(ownerRow.actions).toEqual([]);
  const refused = await apiPost(theirs.request, '/api/hubs/members/change_role', { id: ownerRow.id, role: 'hub_employee' });
  expect(refused.status()).toBe(403);
  await context.close();
  expect(errors).toEqual([]);
});

test('HUBS-G81 + HUBS-G64: the owner removes a person; the Hub gets a snapshot without them and the end of their sessions', async ({
  page,
  browser,
}) => {
  const errors = watchPageErrors(page);
  const owner = await account('remove-owner', 'Olga', 'Ruiz');
  const ana = await account('remove-ana', 'Ana', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, ana, 'hub_employee');
  const member = await rowOf(page, id, ana.email);
  await expect.poll(() => roleInLastSnapshot(hub, id, ana.email)).toBe('hub_employee');

  await page.goto(`/dashboard/businesses/${id}/members`);
  await shown(page).getByTestId(`members-row-${member.id}-remove`).click();
  const dialog = page.getByTestId('remove-dialog');
  await atEverySize(page, 'HUBS-G81', async () => {
    await expect(dialog).toContainText('Ana Gil loses access to Bar Manolo at once. Their account and their other businesses stay.');
  });
  const revokedBefore = revocations(hub, id).length;
  await page.getByTestId('remove-dialog-submit').click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText('Ana Gil was removed from the business')).toBeVisible();
  await expect(shown(page).getByTestId('members-row').filter({ hasText: ana.email })).toHaveCount(0);

  // HUBS-G64: the next snapshot no longer lists them, and the Hub is asked to end their sessions in this business.
  await expect.poll(() => snapshots(hub, id).length > 0 && roleInLastSnapshot(hub, id, ana.email) === undefined).toBe(true);
  await expect
    .poll(() => revocations(hub, id).slice(revokedBefore).map((call) => ({ body: call.body, signed: call.signed })))
    .toEqual([{ body: { user_id: member.user_id, hub_id: id }, signed: true }]);
  const owed = await djangoPrintWarm(
    `from hubs.models import SessionRevocation;print(SessionRevocation.objects.filter(user_id="${member.user_id}", hub_id="${id}", delivered_at__isnull=True).count())`,
  );
  expect(owed).toBe('0');

  // Their account stays, without this business.
  const { context, page: theirs } = await browserOf(browser, ana);
  const list = await theirs.request.get('/api/hubs/businesses?limit=50&offset=0');
  expect(((await list.json()) as { rows: Array<{ id: string }> }).rows.map((one) => one.id)).not.toContain(id);
  await context.close();
  // Nobody removes themselves: the owner's own row offers nothing, and the server refuses it.
  const own = await rowOf(page, id, owner.email);
  expect(own.actions).toEqual([]);
  const self = await apiPost(page.request, '/api/hubs/members/remove', { id: own.id });
  expect(self.status()).toBe(403);
  expect(errors).toEqual([]);
});

test('HUBS-G82: the owner offers the business to a member, who accepts it on Businesses from the mail’s link', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('hand-owner', 'Olga', 'Ruiz');
  const carlos = await account('hand-carlos', 'Carlos', 'Mora');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, carlos, 'hub_admin');
  const member = await rowOf(page, id, carlos.email);

  await page.goto(`/dashboard/businesses/${id}/members`);
  await shown(page).getByTestId(`members-row-${member.id}-menu`).click();
  await page.locator('ion-popover.data-table__row-menu').getByTestId(`members-row-${member.id}-transfer`).click();
  const dialog = page.getByTestId('transfer-dialog');
  await atEverySize(page, 'HUBS-G82', async () => {
    await expect(dialog).toContainText('Transfer Bar Manolo');
    await expect(dialog).toContainText('A paid plan stays until the end of the period already paid; then the new owner pays it with their card, and the current one is not charged again.');
  });
  await expect(dialog.getByTestId('transfer-dialog-submit')).toHaveAttribute('aria-disabled', 'true');
  await page.getByTestId('transfer-dialog-input').locator('input').fill('Bar Manolo');
  const offeredAt = Date.now();
  await dialog.getByTestId('transfer-dialog-submit').click();
  await expect(page.getByText(`Offer sent to ${carlos.email}: they have 7 days to accept it`)).toBeVisible();
  await expect(shown(page).getByTestId('members-transfer')).toContainText(`Ownership offered to ${carlos.email}`);
  // A second offer while this one waits is refused.
  const again = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(again.status()).toBe(409);

  // Carlos follows the mail's link: Businesses, with the offer on top.
  const link = await waitForMail(carlos.email, offeredAt, new RegExp(`${PANEL}/dashboard/businesses(?=\\s|$)`, 'm'));
  const { context, page: theirs, errors: theirErrors } = await browserOf(browser, carlos);
  await theirs.goto(link);
  const offer = shown(theirs).locator('[data-testid^="businesses-offer-"]');
  await atEverySize(theirs, 'HUBS-G82-accept', async () => {
    await expect(offer).toContainText(`${owner.email} offers you Bar Manolo`);
  });
  const acceptedAt = Date.now();
  await offer.getByTestId('offer-accept').click();
  await expect(theirs.getByText('You are now the owner of Bar Manolo')).toBeVisible();

  // The two roles swap: Carlos owns it, Olga stays as admin; the Hub hears it, and the outgoing owner is told
  // where to see what they still pay.
  const roles = Object.fromEntries((await membersOf(theirs, id)).map((one) => [one.email, one.role]));
  expect(roles).toEqual({ [owner.email]: 'hub_admin', [carlos.email]: 'hub_owner' });
  await expect.poll(() => roleInLastSnapshot(hub, id, carlos.email)).toBe('hub_owner');
  await waitForMail(owner.email, acceptedAt, new RegExp(`${PANEL}/dashboard/businesses/${id}(?=\\s|$)`, 'm'));
  await context.close();
  expect(theirErrors).toEqual([]);
  expect(errors).toEqual([]);
});

test('HUBS-G82 (F28): a business handed over on a paid plan: the new owner keeps it with their card, nothing charged today', async ({
  page,
  browser,
}) => {
  const errors = watchPageErrors(page);
  const owner = await account('paid-owner', 'Olga', 'Ruiz');
  const carlos = await account('paid-carlos', 'Carlos', 'Mora');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, carlos, 'hub_admin');
  const member = await rowOf(page, id, carlos.email);
  const stamp = Date.now();
  const [oldSub, oldCustomer, newSub, newCustomer] = [`sub_e2e_old_${stamp}`, `cus_e2e_olga_${stamp}`, `sub_e2e_new_${stamp}`, `cus_e2e_carlos_${stamp}`];
  // Olga pays Starter with her card, as the webhook of her checkout leaves it.
  await djangoPrintWarm(
    [
      'from datetime import timedelta',
      'from django.utils import timezone',
      'from hubs import services',
      'from hubs.schemas import SubscriptionApplyIn',
      'now = timezone.now()',
      `services.subscription_apply(services.system_ctx_for("${id}"), SubscriptionApplyIn(hub_id="${id}", plan="starter", billing_interval="month", status="active", stripe_customer_id="${oldCustomer}", stripe_subscription_id="${oldSub}", current_period_start=now - timedelta(days=10), current_period_end=now + timedelta(days=20), cancel_at_period_end=False))`,
    ].join('\n'),
  );
  // She offers it to Carlos; he accepts (`hubs.ownership.accept`, which stops her renewal in Stripe).
  const offered = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(offered.status(), await offered.text()).toBe(200);
  const transfer = ((await offered.json()) as { id: string }).id;
  await withStripe([
    'from django.contrib.auth import get_user_model',
    'from hubs import services',
    'from hubs.schemas import ByIdIn',
    'from hubs.tests.conftest import ctx_for',
    `double.answer("subscriptions.update", subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True))`,
    `services.ownership_accept(ctx_for(get_user_model().objects.get(email="${carlos.email}")), ByIdIn(id="${transfer}"))`,
    'assert [call.params for call in double.calls_to("subscriptions.update")] == [{"cancel_at_period_end": True}], double.paths()',
  ]);

  // Carlos, now its owner, sees in Billing that the plan is on another account's card until its period ends.
  const { context, page: theirs, errors: theirErrors } = await browserOf(browser, carlos);
  await playStripe(theirs);
  const opened: unknown[] = [];
  await theirs.route('**/api/billing/plan/take-over', async (route) => {
    opened.push(route.request().postDataJSON());
    await route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e_keep', client_secret: 'cs_test_e2e_keep_secret', publishable_key: 'pk_test_e2e', preview: null } });
  });
  await theirs.goto('/dashboard/billing/subscriptions');
  const lead = shown(theirs).getByTestId(`subscriptions-row-${id}-lead`);
  await atEverySize(theirs, 'HUBS-G82-keep-plan', async () => {
    await expect(lead).toHaveText('Keep it with my card');
    await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveText('Paid with another account’s card');
  });

  // «Keep it with my card»: his details first (the payer is still Olga's), then the secure payment, nothing charged today.
  await lead.click();
  const modal = theirs.getByTestId('checkout-modal');
  await expect(modal).toContainText('Keep Starter with your card');
  await expect(modal.getByTestId('checkout-another-account')).toBeVisible();
  // «Use the business's data»: its name and country; the postal code is his.
  await theirs.getByTestId('details-same').click();
  await theirs.getByTestId('details-postal-code').locator('input').fill('28002');
  await modal.getByTestId('checkout-modal-submit').click();
  await expect(modal.getByTestId('stripe-double')).toBeVisible();
  await atEverySize(theirs, 'HUBS-G82-keep-plan-pay', async () => {
    await expect(modal.getByTestId('checkout-for')).toContainText('Bar Manolo · nothing is charged today: your card pays it from');
    await expect(modal.getByTestId('stripe-double')).toBeVisible();
  });
  expect(opened).toEqual([{ hub_id: id }]);
  await payInStripe(theirs);
  await expect(theirs.locator('ion-toast').filter({ hasText: /^Bar Manolo keeps Starter: your card pays it from / })).toBeVisible();
  await expect(theirs).toHaveURL(new RegExp(`/dashboard/businesses/${id}/summary`));

  // Stripe tells the checkout completed (the webhook): the business moves to his card, Olga's subscription ends now.
  await withStripe([
    'from billing import services',
    `held = {"${newSub}": subscription("${newSub}", customer="${newCustomer}", items=[item("si_e2e_new", "price_e2e_starter_month")]), "${oldSub}": subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True)}`,
    'double.answer("subscriptions.retrieve", lambda call: held[call.args[0]])',
    'double.answer("subscriptions.cancel", lambda call: {**held[call.args[0]], "status": "canceled"})',
    `assert services.checkout_completed({"id": "cs_test_e2e_keep", "mode": "subscription", "payment_status": "no_payment_required", "status": "complete", "subscription": "${newSub}", "customer": "${newCustomer}", "metadata": {"kind": "plan_takeover", "hub_id": "${id}", "replaces": "${oldSub}"}}) == "completed"`,
    `assert [call.args for call in double.calls_to("subscriptions.cancel")] == [("${oldSub}",)], double.paths()`,
  ]);
  await theirs.goto('/dashboard/billing/subscriptions');
  await expect(lead).toHaveText('Change plan');
  await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveCount(0);
  await atEverySize(theirs, 'HUBS-G82-kept', async () => {
    await expect(lead).toHaveText('Change plan');
  });

  expect(theirErrors).toEqual([]);
  await context.close();
  expect(errors).toEqual([]);
});

test('HUBS-G82 (F28), in Spanish: «Mantenerlo con mi tarjeta» and the secure payment that charges nothing today', async ({ browser, page }) => {
  const errors = watchPageErrors(page);
  const owner = await account('paid-es-owner', 'Olga', 'Ruiz');
  const lucia = await account('paid-es-lucia', 'Lucía', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, lucia, 'hub_admin');
  const member = await rowOf(page, id, lucia.email);
  const stamp = Date.now();
  const [oldSub, oldCustomer] = [`sub_e2e_es_${stamp}`, `cus_e2e_es_${stamp}`];
  await djangoPrintWarm(
    [
      'from datetime import timedelta',
      'from django.contrib.auth import get_user_model',
      'from django.utils import timezone',
      'from hubs import services',
      'from hubs.schemas import SubscriptionApplyIn',
      'now = timezone.now()',
      `services.subscription_apply(services.system_ctx_for("${id}"), SubscriptionApplyIn(hub_id="${id}", plan="starter", billing_interval="month", status="active", stripe_customer_id="${oldCustomer}", stripe_subscription_id="${oldSub}", current_period_start=now - timedelta(days=10), current_period_end=now + timedelta(days=20), cancel_at_period_end=False))`,
      `get_user_model().objects.filter(email="${lucia.email}").update(language="es")`,
    ].join('\n'),
  );
  const offeredAt = Date.now();
  const offered = await apiPost(page.request, '/api/hubs/ownership/transfer', { hub_id: id, member_id: member.id });
  expect(offered.status(), await offered.text()).toBe(200);
  // The offer of a paid business says until when it is paid and where she keeps it: her mail, in Spanish.
  await waitForMail(lucia.email, offeredAt, new RegExp(`${PANEL}/dashboard/billing/subscriptions(?=\\s|$)`, 'm'));
  await paintMail(browser, 'HUBS-G82-offer-mail-es', lucia.email, offeredAt, 'quiere traspasarte Bar Manolo', 'es');
  await withStripe([
    'from django.contrib.auth import get_user_model',
    'from hubs import services',
    'from hubs.schemas import ByIdIn',
    'from hubs.tests.conftest import ctx_for',
    `double.answer("subscriptions.update", subscription("${oldSub}", customer="${oldCustomer}", items=[item("si_e2e_plan", "price_e2e_starter_month")], cancel_at_period_end=True))`,
    `services.ownership_accept(ctx_for(get_user_model().objects.get(email="${lucia.email}")), ByIdIn(id="${((await offered.json()) as { id: string }).id}"))`,
  ]);

  const context = await browser.newContext({ baseURL: PANEL_URL, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  await freezeFrontend(context);
  const theirs = await context.newPage();
  const theirErrors = watchPageErrors(theirs);
  await signIn(theirs.request, { email: lucia.email, password: PASSWORD });
  await playStripe(theirs);
  await theirs.route('**/api/billing/plan/take-over', (route) =>
    route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e_es', client_secret: 'cs_test_e2e_es_secret', publishable_key: 'pk_test_e2e', preview: null } }),
  );
  await theirs.goto('/dashboard/billing/subscriptions');
  const lead = shown(theirs).getByTestId(`subscriptions-row-${id}-lead`);
  await atEverySize(theirs, 'HUBS-G82-keep-plan-es', async () => {
    await expect(lead).toHaveText('Mantenerlo con mi tarjeta');
    await expect(shown(theirs).getByTestId('subscription-paid-by-another')).toHaveText('Se paga con la tarjeta de otra cuenta');
  });
  await lead.click();
  const modal = theirs.getByTestId('checkout-modal');
  await expect(modal).toContainText('Mantén Starter con tu tarjeta');
  // «Use the business's data»: its name and country; the postal code is his.
  await theirs.getByTestId('details-same').click();
  await theirs.getByTestId('details-postal-code').locator('input').fill('28002');
  await modal.getByTestId('checkout-modal-submit').click();
  await atEverySize(theirs, 'HUBS-G82-keep-plan-pay-es', async () => {
    await expect(modal.getByTestId('checkout-for')).toContainText('Bar Manolo · hoy no se cobra nada: tu tarjeta lo paga desde el');
    await expect(modal.getByTestId('stripe-double')).toBeVisible();
  });
  await context.close();
  expect(theirErrors).toEqual([]);
  expect(errors).toEqual([]);
});

test('HUBS-G83: «Team» lists the people of a business, with their role, status and places; a manager does not see it', async ({
  page,
  browser,
}) => {
  const errors = watchPageErrors(page);
  const owner = await account('list-owner', 'Olga', 'Ruiz');
  const marta = await account('list-marta', 'Marta', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, marta, 'hub_manager');
  const pending = `${PREFIX}list-pending-${Date.now()}@example.com`;
  const invited = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: pending, role: 'hub_employee', message: '' });
  expect(invited.status(), await invited.text()).toBe(200);

  await page.goto(`/dashboard/businesses/${id}/members`);
  const tab = shown(page);
  const rows = tab.getByTestId('members-row');
  await atEverySize(page, 'HUBS-G83', async () => {
    await expect(rows).toHaveCount(3);
    await expect(tab.getByTestId('members-seats')).toHaveText('3 of 3 places on the plan');
    await expect(tab.getByTestId('members-roles')).toContainText('What can each one do?');
  });
  // The owner first, marked as «You»; the invitation says Pending.
  await expect(rows.first()).toContainText('Olga Ruiz');
  await expect(tab.getByTestId('member-you')).toHaveCount(1);
  await expect(rows.filter({ hasText: pending })).toContainText('Pending');
  await expect(rows.filter({ hasText: marta.email })).toContainText('Manager');

  // Marta, a manager, is not shown the team: the page of the business says why, and the server refuses her the list.
  const { context, page: theirs, errors: theirErrors } = await browserOf(browser, marta);
  const refused = await theirs.request.get(`/api/hubs/members?hub_id=${id}&limit=50&offset=0`);
  expect(refused.status()).toBe(403);
  await theirs.goto(`/dashboard/businesses/${id}/members`);
  await expect(shown(theirs)).toContainText('You do not have permission to manage this business');
  await expect(shown(theirs).getByTestId('members-row')).toHaveCount(0);
  await context.close();
  expect(theirErrors).toEqual([]);
  // A stranger does not learn the business exists.
  const stranger = await account('list-stranger', 'Pepe', 'Sanz');
  const { context: other, page: outsider } = await browserOf(browser, stranger);
  expect((await outsider.request.get(`/api/hubs/members?hub_id=${id}&limit=50&offset=0`)).status()).toBe(404);
  await other.close();
  expect(errors).toEqual([]);
});

test('HUBS-G03: the staff finds the accesses of a person in the admin, read only', async ({ page, browser }) => {
  const errors = watchPageErrors(page);
  const owner = await account('admin-owner', 'Olga', 'Ruiz');
  const ana = await account('admin-ana', 'Ana', 'Gil');
  const id = await businessOf(page, owner, 'Bar Manolo');
  await joins(page, browser, id, ana, 'hub_manager');
  const staff = await createAccountWarm(`${PREFIX}staff-${Date.now()}@example.com`, PASSWORD, { role: 'superuser' });
  await signInAs(page, staff);
  await page.goto(`/admin/hubs/hubmember/?q=${encodeURIComponent(ana.email)}`);
  const results = page.locator('#result_list tbody tr');
  await atEverySize(page, 'HUBS-G03', async () => {
    await expect(results).toHaveCount(1);
    await expect(results.first()).toContainText('Bar Manolo');
    await expect(results.first()).toContainText('Manager');
  });
  // Read only: no «Add», and the change page has no «Save».
  await expect(page.locator('.object-tools a.addlink')).toHaveCount(0);
  await results.first().locator('th a').click();
  await expect(page.locator('input[name="_save"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
