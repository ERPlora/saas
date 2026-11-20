// The flows of «the people of a business» (hubs/WORKBOOK.md) on their screens, at the three
// sizes (390×844, 834×1112, 1440×900). Each test names its flow of hubs/WORKBOOK.md in its title: F24 (invite), F25
// (accept), F26 (change the role), F27 (remove, and the end of their sessions in the Hub), F29 (the people of a
// business), F30 (the accesses in the admin). F28 (hand the business over) is in hubs-people-ownership.spec.ts.
//
// The spec plays the Hub (`startHubDouble`, as panel/members.spec.ts): it sees the snapshot of each change and the
// end of a person's sessions in the business; the jump into a business is answered here (no Hub runs). Each test has
// its own accounts (`e2e-hubs3-…@example.com`, their address proven) and its own business, created through the API as
// the panel creates it; the people join it through the operations (invite, then accept), never written by hand.
import { createAccountWarm } from './accounts';
import { djangoPrintWarm } from './django';
import { expect, test } from './fixtures';
import { type HubCall, type HubDouble, startHubDouble } from './hub';
import { waitForMail } from './mail';
import { watchPageErrors } from './page-events';
import {
  account,
  browserOf,
  businessOf,
  joins,
  type MemberRow,
  PANEL,
  PASSWORD,
  paintMail,
  PREFIX,
  removeOwnRows,
  roleInLastSnapshot,
  rowOf,
  shown,
  snapshots,
} from './people';
import { captureAtEverySize } from './screen';
import { apiPost, signInAs } from './session';

const atEverySize = captureAtEverySize('APP-HUBS-3');

/** The ends of sessions the Hub received for `id`. */
const revocations = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'POST' && call.path === '/internal/sessions/revoke' && call.body.hub_id === id);

let hub: HubDouble;

test.beforeAll(async () => {
  await removeOwnRows();
  hub = await startHubDouble();
});
test.afterAll(async () => {
  await hub?.close();
  await removeOwnRows();
});

test('HUBS-F24: an address the schema refuses says why on its field, and on top to look at it until it is corrected, in the language of the account', async ({ page }) => {
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

test('HUBS-F24: the owner invites a person from «Team»; the invitation waits with «Resend» and «Cancel invitation»', async ({ page, browser }) => {
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

test('HUBS-F25: the invited person accepts in «You have been invited» and goes into the business', async ({ page, browser }) => {
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

test('HUBS-F26: the owner changes the role of a person; the Hub hears it and ends their session there', async ({ page, browser }) => {
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

test('HUBS-F27: the owner removes a person; the Hub gets a snapshot without them and the end of their sessions', async ({
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

  // The next snapshot no longer lists them, and the Hub is asked to end their sessions in this business.
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

test('HUBS-F29: «Team» lists the people of a business, with their role, status and places; a manager does not see it', async ({
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

test('HUBS-F30: the staff finds the accesses of a person in the admin, read only', async ({ page, browser }) => {
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
