// @vitest-environment node
// The panel's Vite (tests/e2e/panel/project.ts): its port comes from VITE_DEV_PORT, as Django's and
// vite.config.ts's do, and a running Vite is only reused when it serves this checkout. Another tree's
// (a worker's SaaS of main on 5174) would have the specs test that tree's frontend, not this branch's.
// Node's environment: the checks below talk HTTP to a real server, without happy-dom's fetch.
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import { assertViteOfThisTree, panelServers, VITE_ROOT_HEADER, viteHmrSocket, vitePort, WHATSAPP_E2E } from './panel/project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

describe('vitePort', () => {
  it("is 5174 when VITE_DEV_PORT is not exported: nothing changes for whoever doesn't use it", () => {
    expect(vitePort({})).toBe(5174);
  });

  it('is VITE_DEV_PORT when it is exported', () => {
    expect(vitePort({ VITE_DEV_PORT: '5225' })).toBe(5225);
  });

  it.each(['0', '65536', '70000', '-1', '5174x', ''])('refuses %j, which is no TCP port', (port) => {
    expect(() => vitePort({ VITE_DEV_PORT: port })).toThrow(/^VITE_DEV_PORT must be a TCP port/);
  });
});

describe('panelServers', () => {
  const servers = (port: number) => Object.fromEntries(panelServers(SAAS_DIR, port).map((server) => [server.name, server]));

  it("starts or reuses the Vite of VITE_DEV_PORT only, never 5174's", () => {
    const vite = servers(5225)['panel-vite'];
    expect(vite).toMatchObject({
      command: 'pnpm run dev',
      cwd: SAAS_DIR,
      url: 'http://localhost:5225/static/spa/@vite/client',
      reuseExistingServer: true,
      env: { VITE_DEV_PORT: '5225' },
    });
  });

  it("points the panel's Django at that same Vite (its dev shell and its CSP)", () => {
    expect(servers(5225)['panel-django'].env).toMatchObject({ DEBUG: 'True', VITE_DEV_PORT: '5225' });
  });

  it("gives the panel's Django Meta's made-up e2e app, so the WhatsApp specs can sign its webhook", () => {
    expect(servers(5225)['panel-django'].env).toMatchObject({
      WHATSAPP_APP_ID: WHATSAPP_E2E.appId,
      WHATSAPP_APP_SECRET: WHATSAPP_E2E.appSecret,
      WHATSAPP_VERIFY_TOKEN: WHATSAPP_E2E.verifyToken,
      WHATSAPP_CONFIG_ID: WHATSAPP_E2E.configId,
    });
  });

  it("names the e2e's own provider as the assistant's services provider, never a real one of the database", () => {
    expect(servers(5225)['panel-django'].env).toMatchObject({ ASSISTANT_SERVICE_PROVIDER: 'e2e-local' });
  });

  it("gives each account 2 messages a month with the panel's assistant, so a spec spends them (ASSISTANT-F26)", () => {
    // assistant-panel.spec.ts asks twice, then sees the month spent; the panel's twin with the second factor too.
    expect(servers(5225)['panel-django'].env).toMatchObject({ ASSISTANT_ACCOUNT_MESSAGES: '2' });
    expect(servers(5225)['panel-mfa-django'].env).toMatchObject({ ASSISTANT_ACCOUNT_MESSAGES: '2' });
  });

  it('keeps 5174 by default', () => {
    expect(panelServers(SAAS_DIR).find((server) => server.name === 'panel-vite')?.url).toBe(
      `http://localhost:${vitePort(process.env)}/static/spa/@vite/client`,
    );
    expect(servers(5174)['panel-vite'].url).toBe('http://localhost:5174/static/spa/@vite/client');
  });
});

describe('viteHmrSocket', () => {
  it("matches the hot-update socket of that port's Vite only (freezeFrontend, panel/fixtures.ts)", () => {
    expect(viteHmrSocket(5225).test('ws://localhost:5225/static/spa/?token=abc')).toBe(true);
    expect(viteHmrSocket(5225).test('ws://localhost:5174/static/spa/?token=abc')).toBe(false);
    expect(viteHmrSocket(5174).test('ws://localhost:5174/static/spa/?token=abc')).toBe(true);
  });
});

describe('assertViteOfThisTree', () => {
  let server: Server | undefined;

  afterEach(async () => {
    await new Promise<void>((done) => (server ? server.close(() => done()) : done()));
    server = undefined;
  });

  /** A server on a free port answering `/static/spa/@vite/client` with `status` and `headers`. */
  async function viteDouble(status: number, headers: Record<string, string>): Promise<number> {
    server = createServer((request, response) => {
      const known = request.url === '/static/spa/@vite/client';
      response.writeHead(known ? status : 404, known ? headers : {});
      response.end(known ? 'export {};' : 'not found');
    });
    await new Promise<void>((done) => server!.listen(0, '127.0.0.1', done));
    return (server.address() as AddressInfo).port;
  }

  it("passes when the Vite on that port serves this checkout's tree", async () => {
    const port = await viteDouble(200, { [VITE_ROOT_HEADER]: encodeURIComponent(SAAS_DIR) });

    await expect(assertViteOfThisTree(SAAS_DIR, port, '127.0.0.1')).resolves.toBeUndefined();
  });

  it('reads a tree whose path needs encoding in a header', async () => {
    const tree = '/Users/someone/código/saas wt';
    const port = await viteDouble(200, { [VITE_ROOT_HEADER]: encodeURIComponent(tree) });

    await expect(assertViteOfThisTree(tree, port, '127.0.0.1')).resolves.toBeUndefined();
  });

  it("stops the run, naming both trees and the way out, when the Vite serves another checkout", async () => {
    const other = '/Users/someone/erplora-next/saas';
    const port = await viteDouble(200, { [VITE_ROOT_HEADER]: encodeURIComponent(other) });

    await expect(assertViteOfThisTree(SAAS_DIR, port, '127.0.0.1')).rejects.toThrow(
      `The Vite on :${port} serves ${other}, not this checkout (${SAAS_DIR}): the panel's specs would test that tree's frontend. Export VITE_DEV_PORT=<a free port> and retry (README.md, «Dos SaaS a la vez»).`,
    );
  });

  it('stops the run when the Vite does not say which tree it serves (another checkout older than VITE_DEV_PORT)', async () => {
    const port = await viteDouble(200, {});

    await expect(assertViteOfThisTree(SAAS_DIR, port, '127.0.0.1')).rejects.toThrow(
      `The Vite on :${port} does not say which checkout it serves (another tree's, older than VITE_DEV_PORT): the panel's specs would test its frontend, not this checkout's (${SAAS_DIR}). Export VITE_DEV_PORT=<a free port> and retry (README.md, «Dos SaaS a la vez»).`,
    );
  });

  it("stops the run when what answers on that port is no Vite of this project", async () => {
    const port = await viteDouble(404, {});

    await expect(assertViteOfThisTree(SAAS_DIR, port, '127.0.0.1')).rejects.toThrow(
      `What answers on :${port} is not this checkout's Vite (GET http://127.0.0.1:${port}/static/spa/@vite/client: 404).`,
    );
  });

  it('stops the run when nothing answers on that port', async () => {
    const port = await viteDouble(200, {});
    await new Promise<void>((done) => server!.close(() => done()));
    server = undefined;

    await expect(assertViteOfThisTree(SAAS_DIR, port, '127.0.0.1')).rejects.toThrow(
      new RegExp(`^Nothing answers on Vite's port :${port} \\(GET http://127\\.0\\.0\\.1:${port}/static/spa/@vite/client: `),
    );
  });
});
