// The door of a demo being prepared (public/demo.py, `preparing`; frontend/demo-wait.ts) in a real browser, under the
// public web's CSP with no violation reported: the Hub answers «Try the demo» with 202 «requested» and prepares the demo
// afterwards, so the door says «Preparing your demo…» while its page asks /demo/status/ every second, and goes into the
// demo once the Hub says it is ready; a demo the Hub could not prepare lands on «Your demo is not ready yet» with «Try
// again», in English and in Spanish, at the three widths (390, 834, 1440; captures in `.artifacts/demo/`).
//
// The spec plays the Hub on the stack's port for it (`publicHubDoublePort`, the public server's HUB_INTERNAL_URL;
// stack.ts): `POST /internal/demos` makes a demo `requested`, `GET /internal/hubs/{id}` says its status as the test
// sets it, and the demo's host is caught at its door (`page.route`), where the browser lands.
import { mkdirSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { expect, test } from './public-test';
import { STACK } from './stack';

const ARTIFACTS = join(dirname(fileURLToPath(import.meta.url)), '.artifacts', 'demo');
const WIDTHS = [390, 834, 1440];
const STATUS = /^\/internal\/hubs\/([0-9a-f-]{36})$/;

interface Demo {
  id: string;
  slug: string;
  /** What `GET /internal/hubs/{id}` says, each ask (the last one repeats). */
  statuses: string[];
  asked: number;
}

/** The demos the double made, by id; the next one is born with `next` as its statuses. */
const demos = new Map<string, Demo>();
let next: string[] = ['requested'];
let hub: Server;

function startHub(): Promise<Server> {
  const server = createServer((request, response) => {
    const path = request.url ?? '';
    const answer = (status: number, body: unknown) => {
      response.writeHead(status, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    request.resume();
    request.on('end', () => {
      if (request.method === 'POST' && path === '/internal/demos') {
        const hex = Math.random().toString(16).slice(2, 10).padEnd(8, '0');
        const demo: Demo = { id: `0193a0c4-0000-7000-8000-0000${hex}`, slug: `demo-${hex}`, statuses: next, asked: 0 };
        demos.set(demo.id, demo);
        const expires = new Date(Date.now() + 60 * 60 * 1000).toISOString();
        answer(202, { id: demo.id, slug: demo.slug, status: 'requested', expires_at: expires, created: true });
        return;
      }
      const asked = STATUS.exec(path);
      const demo = asked ? demos.get(asked[1]) : undefined;
      if (request.method === 'GET' && demo) {
        answer(200, { status: demo.statuses[Math.min(demo.asked++, demo.statuses.length - 1)] });
        return;
      }
      answer(404, { error: { code: 'not_found', message: 'Unknown.' } });
    });
  });
  return new Promise((listening, failed) => {
    server.once('error', failed);
    server.listen(STACK.publicHubDoublePort, '127.0.0.1', () => listening(server));
  });
}

/** Every CSP violation the browser reports on any page of the test (the console survives the navigations). */
function watchCsp(page: Page): () => string[] {
  const reported: string[] = [];
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) reported.push(message.text());
  });
  return () => reported;
}

/** The demo's host, caught at its door: every request to it is answered here and remembered. */
async function demoDoor(page: Page): Promise<string[]> {
  const visits: string[] = [];
  await page.route(/^http:\/\/demo-[0-9a-f]{8}\.localhost(:\d+)?\//, async (route) => {
    visits.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Demo</h1>' });
  });
  return visits;
}

test.beforeAll(async () => {
  hub = await startHub();
});
test.afterAll(async () => {
  await new Promise<void>((closed) => {
    hub.closeAllConnections();
    hub.close(() => closed());
  });
});

test.describe('in English', () => {
  test.use({ locale: 'en-GB' });

  test('the door waits while the Hub prepares the demo, then goes into it', async ({ page }) => {
    next = ['requested', 'creating', 'migrating', 'seeding', 'ready'];
    const violations = watchCsp(page);
    const visits = await demoDoor(page);
    await page.goto('/demo/');

    await page.getByTestId('demo-start').click();

    await expect(page.getByTestId('demo-state-preparing')).toBeVisible();
    await expect(page.getByTestId('demo-state-preparing').getByRole('status')).toContainText('Preparing your demo…');
    await page.waitForURL(/^http:\/\/demo-[0-9a-f]{8}\.localhost(:\d+)?\/auth\/login\?next=\/$/, { timeout: 15_000 });
    expect(visits).toHaveLength(1);
    const [demo] = [...demos.values()].slice(-1);
    expect(demo.asked).toBe(5);
    expect(violations()).toEqual([]);
  });

  test('a demo the Hub could not prepare says it is not ready yet, and «Try again» waits for it again', async ({ page }) => {
    next = ['failed'];
    const violations = watchCsp(page);
    await page.goto('/demo/');

    await page.getByTestId('demo-start').click();

    await expect(page).toHaveURL(/\/demo\/\?state=not_ready$/);
    mkdirSync(ARTIFACTS, { recursive: true });
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      await expect(page.getByText('Your demo is not ready yet. Try again in a moment.')).toBeVisible();
      await page.screenshot({ path: join(ARTIFACTS, `demo-not-ready-en-${width}.png`), fullPage: true });
    }
    const [demo] = [...demos.values()].slice(-1);
    demo.statuses = ['ready'];
    demo.asked = 0;
    await demoDoor(page);
    await page.getByTestId('demo-retry').click();
    await page.waitForURL(new RegExp(`^http://${demo.slug}\\.localhost(:\\d+)?/auth/login`), { timeout: 15_000 });
    expect(violations()).toEqual([]);
  });
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('the waiting door and the one not ready yet speak Spanish', async ({ page }) => {
    next = ['requested'];
    const violations = watchCsp(page);
    await page.goto('/demo/');

    await page.getByTestId('demo-start').click();

    await expect(page.getByTestId('demo-state-preparing').getByRole('status')).toContainText('Preparando tu demo…');
    mkdirSync(ARTIFACTS, { recursive: true });
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      await expect(page.getByTestId('demo-state-preparing')).toBeVisible();
      await page.screenshot({ path: join(ARTIFACTS, `demo-preparing-es-${width}.png`), fullPage: true });
    }
    await page.goto('/demo/?state=not_ready');
    await expect(page.getByText('Tu demo aún no está lista. Vuelve a intentarlo en un momento.')).toBeVisible();
    await expect(page.getByTestId('demo-retry')).toContainText('Volver a intentarlo');
    expect(violations()).toEqual([]);
  });
});
