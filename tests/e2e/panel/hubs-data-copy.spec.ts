// «Download the data» of a business (HUBS-F18, HUBS-F20; PLAN-DB round 2026-10-30, proposals (a), (k), (l)) in a real
// browser, at the three sizes of the migration (390×844, 834×1112, 1440×900), in English and in Spanish: the page of a
// deleted business, where its deletion mail leads, lists the copies the Hub keeps of its data (when, which, how big) and
// each «Download» asks the Hub for a fresh link and the browser downloads the file. Without a copy yet it says so and
// that we will tell; a live business without copies has no card.
//
// The spec plays the Hub on this stack's Hub port (`HUB_DOUBLE_PORT`, where the panel's Django calls it): it answers
// `GET /internal/hubs/{id}/dumps` with the copies the test sets, each with a link to itself that serves the file as an
// attachment, and 503 to the rest. Accounts of this spec: `e2e-copy-…@example.com`.
import { createServer, type Server } from 'node:http';

import { type Page } from '@playwright/test';

import { djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const PREFIX = 'e2e-copy-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const DUMPS = /^\/internal\/hubs\/([0-9a-f-]{36})\/dumps$/;
const FILES = /^\/files\/([^?]+)/;

/** The copies the double keeps of each business (by id), as the Hub lists them without their link. */
const copies = new Map<string, Array<Record<string, unknown>>>();
/** The paths the panel's Django asked the double for. */
const asked: string[] = [];
let links = 0;
let hub: Server;

function startHub(): Promise<Server> {
  const server = createServer((request, response) => {
    const path = request.url ?? '';
    asked.push(`${request.method} ${path}`);
    const listed = DUMPS.exec(path);
    if (request.method === 'GET' && listed) {
      const origin = `http://127.0.0.1:${HUB_DOUBLE_PORT}`;
      const dumps = (copies.get(listed[1]) ?? []).map((copy) => ({
        ...copy,
        url: `${origin}/files/${encodeURIComponent(String(copy.id))}?X-Amz-Expires=900&n=${++links}`,
      }));
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ dumps }));
      return;
    }
    const file = FILES.exec(path);
    if (request.method === 'GET' && file) {
      const name = decodeURIComponent(file[1]).split('/').at(-1) ?? 'copy.dump';
      response.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Disposition': `attachment; filename="${name}"` });
      response.end('PGDMP e2e copy');
      return;
    }
    response.writeHead(503, { 'Content-Type': 'application/json' });
    response.end('{"error":{"code":"hub_away"}}');
  });
  return new Promise((listening, failed) => {
    server.once('error', failed);
    server.listen(HUB_DOUBLE_PORT, '127.0.0.1', () => listening(server));
  });
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

/** A fresh owner (address proven) of a business called `name` in `status`; its email and the business's id. */
function ownerOf(name: string, status: 'deleting' | 'active'): { email: string; id: string } {
  const email = `${PREFIX}${status}-${Date.now()}@example.com`;
  const id = djangoPrint(
    [
      'from datetime import timedelta',
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from django.utils import timezone',
      'from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="en")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
      'now = timezone.now()',
      'profile = BillingProfile.objects.create(owner=user, billing_email=user.email, billing_country="ES")',
      `hub = Hub.objects.create(slug="${PREFIX}${status}-${Date.now()}", name="${name}", country="ES", timezone="Europe/Madrid",`,
      `    language="es", billing_profile=profile, status="${status}", ready_at=now - timedelta(days=90),`,
      `    deletion_requested_at=${status === 'deleting' ? 'now - timedelta(days=2)' : 'None'})`,
      'Subscription.objects.create(hub=hub, plan=Plan.objects.get(slug="free"), status="active", current_period_start=now)',
      'HubMember.objects.create(hub=hub, user=user, role="hub_owner", joined_at=now, accepted_at=now)',
      'print(hub.id)',
    ].join('\n'),
  )
    .split('\n')
    .at(-1) as string;
  return { email, id };
}

function speak(email: string, language: 'en' | 'es'): void {
  djangoPrint(`from django.contrib.auth import get_user_model;get_user_model().objects.filter(email="${email}").update(language="${language}")`);
}

function copyOf(id: string, kind: 'offboarding' | 'reset', when: string, bytes: number): Record<string, unknown> {
  const stamp = when.replace(/[-:]/g, '').replace(/\.\d+/, '').replace('+0000', 'Z');
  return { id: `${id.replaceAll('-', '')}/${stamp}-${kind}.dump`, kind, created_at: when, bytes };
}

/** `ready` at each size: no sideways scroll and a capture `HUBS-F18-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`HUBS-F18-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.beforeAll(async () => {
  removeOwnRows();
  hub = await startHub();
});
test.afterAll(async () => {
  await new Promise<void>((closed) => {
    hub.closeAllConnections();
    hub.close(() => closed());
  });
  removeOwnRows();
});

test('HUBS-F18: the owner of a deleted business downloads the copy of its data, in English and in Spanish', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { email, id } = ownerOf('Bar Antiguo', 'deleting');
  copies.set(id, [copyOf(id, 'reset', '2026-10-20T08:00:00Z', 1_536), copyOf(id, 'offboarding', '2026-10-28T10:15:00Z', 48_213_504)]);
  await signIn(page.request, { email, password: PASSWORD });

  await page.goto(`/dashboard/businesses/${id}`);
  const card = page.getByTestId('data-copy-card');
  await atEverySize(page, 'en', async () => {
    await expect(card.getByText('Download the data')).toBeVisible();
  });
  const rows = card.getByTestId('data-copy-row');
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText('When it was deleted');
  await expect(rows.first()).toContainText('46 MB');
  await expect(rows.last()).toContainText('Before its data was reset');

  const before = asked.filter((call) => call.endsWith('/dumps')).length;
  const download = page.waitForEvent('download');
  await rows.first().getByTestId('data-copy-download').click();
  expect((await download).suggestedFilename()).toBe('20261028T101500Z-offboarding.dump');
  // The link was asked on the click (a second list of the Hub), never kept from the page's.
  expect(asked.filter((call) => call.endsWith('/dumps')).length).toBe(before + 1);

  speak(email, 'es');
  await page.goto(`/dashboard/businesses/${id}`);
  await atEverySize(page, 'es', async () => {
    await expect(card.getByText('Descargar los datos')).toBeVisible();
  });
  await expect(card.getByTestId('data-copy-row').first()).toContainText('Al eliminarlo');
  await expect(card.getByTestId('data-copy-row').last()).toContainText('Antes de restablecer sus datos');
  expect(errors).toEqual([]);
});

test('HUBS-F18: without its copy yet, the page says it is not ready and that we will tell', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { email, id } = ownerOf('Café Viejo', 'deleting');
  copies.set(id, []);
  await signIn(page.request, { email, password: PASSWORD });

  await page.goto(`/dashboard/businesses/${id}`);
  await atEverySize(page, 'not-ready', async () => {
    await expect(page.getByTestId('data-copy-not-ready')).toContainText(
      'The copy is not ready yet. We will let you know by email when it is.',
    );
  });
  expect(errors).toEqual([]);
});

test('a live business without copies has no «Download the data»', async ({ page }) => {
  const errors = watchPageErrors(page);
  const { email, id } = ownerOf('Panadería Nueva', 'active');
  copies.set(id, []);
  await signIn(page.request, { email, password: PASSWORD });

  await page.goto(`/dashboard/businesses/${id}`);
  await expect(page.getByTestId('business-header')).toBeVisible();
  await expect.poll(() => asked.some((call) => call === `GET /internal/hubs/${id}/dumps`)).toBe(true);
  await settled(page);
  await expect(page.getByTestId('data-copy-card')).toHaveCount(0);
  expect(errors).toEqual([]);
});
