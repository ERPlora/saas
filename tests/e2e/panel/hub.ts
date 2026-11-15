import { execFile } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
import { promisify } from 'node:util';

import { type APIRequestContext, expect } from '@playwright/test';

import { djangoPrintAsync, SAAS_DIR } from './django';
import { HUB_DOUBLE_PORT } from './project';

const execFileAsync = promisify(execFile);

let secretRead: Promise<string> | undefined;

/**
 * `INTERNAL_SHARED_SECRET` of the local SaaS (`.env`), to sign what the Hub would send: read once per worker, without
 * blocking this process. A spec that signs inside a test reads it first in a `beforeAll`, so that the Django boot of
 * the read is on no test's clock (saas#346).
 */
export function internalSecret(): Promise<string> {
  secretRead ??= djangoPrintAsync('from django.conf import settings;print(settings.INTERNAL_SHARED_SECRET)');
  return secretRead;
}

/** The Hub's callback (`POST /internal/hubs/{id}/ready`), as it sends it: the body names the hub of the path, signed. */
export async function reportBusinessReady(request: APIRequestContext, id: string): Promise<void> {
  const body = JSON.stringify({ id });
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', await internalSecret()).update(`${timestamp}.${body}`).digest('hex');
  const ready = await request.post(`/internal/hubs/${id}/ready`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': String(timestamp), 'X-Erplora-Signature': signature },
  });
  expect(ready.status(), await ready.text()).toBe(200);
}

// ── The Hub, played by a spec ─────────────────────────────────────────────────────────────────

/** A call the SaaS made to the Hub's `/internal`, as the double received it. */
export interface HubCall {
  method: string;
  path: string;
  body: Record<string, unknown>;
  /** Carries the timestamp and the signature every internal call is sent with. */
  signed: boolean;
}

export interface HubDouble {
  calls: HubCall[];
  setMaintenance(value: Record<string, unknown> | null): void;
  close(): Promise<void>;
}

/** What the double acknowledges as the Hub does; any other call finds the Hub away (503, stays owed). */
const PLAYED = [
  /^PUT \/internal\/hubs\/[0-9a-f-]+\/state$/,
  /^POST \/internal\/sessions\/revoke$/,
  // WhatsApp's doors 1 and 2 (whatsapp.spec.ts): a message or a status erplora.com hands the Hub.
  /^POST \/internal\/whatsapp\/(inbound|status)$/,
];

/**
 * Plays the Hub on `HUB_DOUBLE_PORT`, where the panel's Django sends its calls (project.ts), until
 * `close()`: it records every call and acknowledges the snapshot push, the session revocation and WhatsApp's doors.
 * Outside it nobody listens there and every call stays owed, as with the Hub away.
 */
export async function startHubDouble(): Promise<HubDouble> {
  const calls: HubCall[] = [];
  let maintenance: Record<string, unknown> | null | undefined;
  const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer) => chunks.push(chunk));
    request.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      const method = request.method ?? '';
      const path = request.url ?? '';
      calls.push({
        method,
        path,
        body: raw ? (JSON.parse(raw) as Record<string, unknown>) : {},
        signed: !!request.headers['x-erplora-timestamp'] && !!request.headers['x-erplora-signature'],
      });
      if (method === 'GET' && /^\/internal\/hubs\/[0-9a-f-]+$/.test(path) && maintenance !== undefined) {
        response.writeHead(200, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ status: 'requested', maintenance }));
        return;
      }
      const played = PLAYED.some((route) => route.test(`${method} ${path}`));
      response.writeHead(played ? 200 : 503, { 'Content-Type': 'application/json' });
      response.end(played ? '{}' : '{"error":{"code":"hub_away"}}');
    });
  });
  await new Promise<void>((listening, failed) => {
    server.once('error', failed);
    server.listen(HUB_DOUBLE_PORT, '127.0.0.1', () => listening());
  });
  return {
    calls,
    setMaintenance(value) {
      maintenance = value;
    },
    close: () =>
      new Promise<void>((closed) => {
        server.closeAllConnections();
        server.close(() => closed());
      }),
  };
}

// ── The real Hub's Django, asked by a spec (saas#354) ─────────────────────────────────────────

/**
 * What `code` prints in the real Hub's Django (`HUB_DIR`, its database `HUB_DB_NAME`; README «El Hub real de la e2e»), by
 * its `manage.py shell`: its last line. It never blocks this process, so a test's timeout still fires while it runs.
 */
export async function realHubPrint(code: string): Promise<string> {
  const { stdout } = await execFileAsync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], {
    cwd: process.env.HUB_DIR,
    // The Hub's database: never this run's DB_NAME, which the SaaS's stack.ts refuses.
    env: { ...process.env, DB_NAME: process.env.HUB_DB_NAME, DEBUG: 'True' },
    encoding: 'utf8',
  });
  return stdout.trim().split('\n').pop() ?? '';
}

// ── The Hub stack's databases, read by a spec (saas#370) ──────────────────────────────────────

/** A business of the Hub's stack, as `base_hub.slug` names it (`a`, `b`: its local hubs). */
const HUB_SLUG = /^[a-z0-9][a-z0-9-]*$/;
const HUB_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * The rows `query` reads in the Hub's stack on `port` (whatsapp-hub.spec.ts's header; the Postgres of the root's
 * compose.yaml), trimmed, by `psql` in that container without blocking this process: in its control database
 * (`hub_e2e_<port>`, the registry `base_hub`), or with `hub` in that business's own database (its `db_name` there),
 * where every app's tables live. A failing query rejects with what `psql` said.
 */
export async function hubStackSql(port: number, query: string, hub?: string): Promise<string> {
  let database = `hub_e2e_${port}`;
  if (hub !== undefined) {
    if (!HUB_SLUG.test(hub)) throw new Error(`hubStackSql: ${JSON.stringify(hub)} is no slug of a business`);
    database = await hubStackSql(port, `select db_name from base_hub where slug = '${hub}'`);
    expect(database, `the database of ${hub} in hub_e2e_${port}`).toMatch(new RegExp(`^hub_e2e_${port}_[0-9a-f]+$`));
  }
  const { stdout } = await execFileAsync(
    'docker',
    ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', database, '-At', '-c', query],
    { cwd: resolve(SAAS_DIR, '..'), encoding: 'utf8' },
  );
  return stdout.trim();
}

/** The Hub's own ids of its local hubs `a` and `b` in its stack on `port`: two UUIDs, or the call fails saying so. */
export async function hubStackIds(port: number): Promise<[string, string]> {
  const rows = await hubStackSql(port, "select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug");
  const ids = Object.fromEntries(rows.split('\n').map((row) => row.split('=')));
  const found: [string, string] = [ids.a, ids.b];
  expect(found, `the ids of a and b in hub_e2e_${port}`).toEqual([expect.stringMatching(HUB_ID), expect.stringMatching(HUB_ID)]);
  return found;
}
