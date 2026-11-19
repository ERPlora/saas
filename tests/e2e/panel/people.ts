// What the specs of «the people of a business» share (hubs-people.spec.ts, hubs-people-ownership.spec.ts): their
// accounts and businesses, the people joining through the operations, the team as hubs.member.list reads it, their
// mails painted at every size and what the Hub double hears.
import { type Browser, type Page } from '@playwright/test';

import { horizontalOverflow } from '../horizontal-overflow';
import { createAccountWarm } from './accounts';
import { djangoPrintWarm } from './django';
import { expect, freezeFrontend } from './fixtures';
import { type HubCall, type HubDouble } from './hub';
import { MAIL_LOGO_URL, mailPartsOf, onlyTheMailLogo } from './mail';
import { watchPageErrors } from './page-events';
import { PANEL_URL } from './project';
import { settled, shot, VIEWPORTS } from './screen';
import { apiPost, signIn } from './session';

export const PREFIX = 'e2e-hubs3-';
export const PASSWORD = 'Masa-madre-y-centeno-26';
/** The panel's origin as a pattern: the mails link to the server that sent them, the run's (stack.ts). */
export const PANEL = PANEL_URL.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

interface Account {
  email: string;
  name: string;
}

export interface MemberRow {
  id: string;
  user_id: string;
  email: string;
  role: string;
  status: string;
  actions: string[];
}

/** A fresh account of this spec, its address proven, called `first last`, in English (written by the warm Django). */
export async function account(who: string, first: string, last: string): Promise<Account> {
  const email = `${PREFIX}${who}-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { firstName: first, lastName: last, language: 'en' });
  return { email, name: `${first} ${last}` };
}

/**
 * `owner` signed in on `page`, with a business called `name`, ready as the Hub leaves it: its registry taken (the
 * double only plays the snapshot and the end of sessions) and its callback received. From here each change of its
 * people pushes the snapshot.
 */
export async function businessOf(page: Page, owner: Account, name: string): Promise<string> {
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
export async function browserOf(browser: Browser, person: Account) {
  const context = await browser.newContext({ baseURL: PANEL_URL, locale: 'en-US', viewport: { width: 1440, height: 900 } });
  await freezeFrontend(context);
  const page = await context.newPage();
  const errors = watchPageErrors(page);
  await signIn(page.request, { email: person.email, password: PASSWORD });
  return { context, page, errors };
}

/** `person` joins business `id` as `role`: the owner on `page` invites them and they accept, through the API. */
export async function joins(page: Page, browser: Browser, id: string, person: Account, role: string): Promise<void> {
  const invited = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: person.email, role, message: '' });
  expect(invited.status(), await invited.text()).toBe(200);
  const { context, page: theirs } = await browserOf(browser, person);
  const accepted = await apiPost(theirs.request, '/api/hubs/invitations/accept', { id: ((await invited.json()) as MemberRow).id });
  expect(accepted.status(), await accepted.text()).toBe(200);
  await context.close();
}

/** `hubs.member.list` as `page`'s account reads it. */
export async function membersOf(page: Page, id: string): Promise<MemberRow[]> {
  const response = await page.request.get(`/api/hubs/members?hub_id=${id}&limit=50&offset=0`);
  expect(response.status(), 'GET /api/hubs/members').toBe(200);
  return ((await response.json()) as { rows: MemberRow[] }).rows;
}

export async function rowOf(page: Page, id: string, email: string): Promise<MemberRow> {
  const row = (await membersOf(page, id)).find((one) => one.email === email);
  if (!row) throw new Error(`${email} is not in hubs.member.list`);
  return row;
}

/**
 * The HTML part of the newest mail to `to` since `since` whose subject has `subject`, read from the panel's mail folder
 * as a mail client reads it (as panel/accounts-mails.spec.ts), painted at every size: text and HTML, the logo, every
 * line of the text, nothing fetched but the logo, no sideways scroll, and its capture.
 */
export async function paintMail(browser: Browser, key: string, to: string, since: number, subject: string, language: string): Promise<void> {
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
export const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** The snapshots the Hub received for `id`, in the order they were pushed. */
export const snapshots = (hub: HubDouble, id: string): HubCall[] =>
  hub.calls.filter((call) => call.method === 'PUT' && call.path === `/internal/hubs/${id}/state`);

/** `email`'s role in the last snapshot of `id` (`undefined` when it does not list them). */
export function roleInLastSnapshot(hub: HubDouble, id: string, email: string): string | undefined {
  const members = (snapshots(hub, id).at(-1)?.body.members ?? []) as Array<{ email: string; role: string }>;
  return members.find((member) => member.email === email)?.role;
}

/** What these specs leave behind, written by the warm Django (its first call, in `beforeAll`, starts it). */
export async function removeOwnRows(): Promise<void> {
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
