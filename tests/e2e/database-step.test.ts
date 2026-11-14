// @vitest-environment node
// A stack's database step as Playwright runs it (playwright.config.ts, `databaseStep`): the real `webServer` list of
// the e2e, under the real Playwright, with `uv`, `docker` and `pnpm` played by scripts, so that a slow migration needs
// no loaded machine and the check needs neither Python nor Postgres (the CI's frontend job has neither). Migrating
// inside the first server's command competed with that server's two minutes: on a busy machine Playwright killed the
// migration half way and the run ended without a spec. The timeouts are scaled down: a server's two minutes are
// SERVER_TIMEOUT_MS here, and the migration lasts a little longer than that.
// flow: ninguno — test tooling, nothing anyone sees changes
import { spawn } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer as createHttpServer } from 'node:http';
import { createServer } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
const PLAYWRIGHT = join(SAAS_DIR, 'node_modules', '.bin', 'playwright');

/** What the servers of the real config wait for, two minutes: the timeouts up to it are the servers', the scaled ones. */
const REAL_SERVER_TIMEOUT_MS = 120_000;
const SERVER_TIMEOUT_MS = 15_000;
/** Longer than a server's timeout: the migration of a stack's first run on a busy machine (170 s measured with a load of 22). */
const SLOW_MIGRATION_SECONDS = 17;
/** Far below the database step's own timeout: a run that gets here was waiting for it. */
const RUN_LIMIT_MS = 75_000;
const TEST_LIMIT_MS = 100_000;

const FAKE_UV = `#!/bin/sh
case "$*" in
  *"manage.py migrate"*)
    echo "migrate:start $DB_NAME" >> "$FAKE_LOG"
    sleep "\${FAKE_MIGRATE_SECONDS:-0}"
    if [ -n "$FAKE_MIGRATE_FAILS" ]; then echo "$FAKE_MIGRATE_FAILS" >&2; exit 1; fi
    echo "migrate:end" >> "$FAKE_LOG"
    ;;
  *"manage.py runserver"*)
    echo "runserver $DB_NAME" >> "$FAKE_LOG"
    for argument; do case "$argument" in 127.0.0.1:*) port="\${argument#127.0.0.1:}" ;; esac; done
    exec node "$FAKE_SERVER" "$port"
    ;;
  *) echo "unexpected uv $*" >&2; exit 64 ;;
esac
`;

const FAKE_DOCKER = `#!/bin/sh
for statement; do :; done
echo "psql $statement" >> "$FAKE_LOG"
case "$statement" in
  "select 1 from pg_database"*) if [ -n "$FAKE_DATABASE_EXISTS" ]; then echo 1; fi ;;
esac
`;

// With FAKE_TAKE_VITE_PORT_ONCE, the first Vite finds its port taken by another process after Playwright saw it free:
// the window in which another session on the machine took a port of the block.
const FAKE_PNPM = `#!/bin/sh
echo "vite" >> "$FAKE_LOG"
if [ -n "$FAKE_TAKE_VITE_PORT_ONCE" ] && mkdir "$FAKE_TAKE_VITE_PORT_ONCE" 2>/dev/null; then
  node "$FAKE_SQUATTER" "$VITE_DEV_PORT" "$FAKE_TAKE_VITE_PORT_ONCE/pid" </dev/null >/dev/null 2>&1 &
  while [ ! -s "$FAKE_TAKE_VITE_PORT_ONCE/pid" ]; do sleep 0.1; done
fi
exec node "$FAKE_SERVER" "$VITE_DEV_PORT"
`;

const FAKE_SERVER = `require('node:http').createServer((_, response) => response.end('ok')).listen(Number(process.argv[2]));\n`;

/** Holds a port without ever answering, so that Playwright keeps waiting for the server that could not open it. */
const FAKE_SQUATTER = `const { writeFileSync } = require('node:fs');
const [port, pidFile] = process.argv.slice(2);
const server = require('node:net').createServer((socket) => socket.destroy());
server.once('error', (error) => { writeFileSync(pidFile, 'error ' + error.code); process.exit(1); });
server.listen(Number(port), () => writeFileSync(pidFile, String(process.pid)));
setTimeout(() => process.exit(0), 60_000);
`;

const SPEC = `import { test } from '@playwright/test';\ntest('the run got to its specs', () => {});\n`;

/** The run's config: the real `webServer` list, with its timeouts scaled down. */
function configSource(work: string, databaseTimeoutMs: number | undefined): string {
  return `import { defineConfig } from '@playwright/test';
import e2e from '../../playwright.config';

export default defineConfig({
  testDir: ${JSON.stringify(work)},
  outputDir: ${JSON.stringify(join(work, 'results'))},
  reporter: [['list']],
  webServer: [e2e.webServer ?? []].flat().map((server) => ({
    ...server,
    timeout: (server.timeout ?? 0) > ${REAL_SERVER_TIMEOUT_MS} ? (${databaseTimeoutMs ?? 'server.timeout'}) : ${SERVER_TIMEOUT_MS},
  })),
});
`;
}

function isFree(port: number): Promise<boolean> {
  return new Promise((answer) => {
    const server = createServer();
    server.once('error', () => answer(false));
    server.listen(port, () => server.close(() => answer(true)));
  });
}

/** A block of ten ports free when chosen: other sessions run their stacks and this same test on this machine. */
async function freeBase(): Promise<number> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const base = 30_000 + 10 * Math.floor(Math.random() * 3_000);
    const ports = Array.from({ length: 10 }, (_, offset) => base + offset);
    if ((await Promise.all(ports.map(isFree))).every(Boolean)) return base;
  }
  throw new Error('No block of ten free ports.');
}

/** What a run prints when another process took a port of its block after `freeBase` found it free: a server of its
 *  own could not open it, or Playwright found someone else's server already answering there. */
const PORT_TAKEN = /EADDRINUSE|is already used, make sure that nothing is running on the port/;
/** Blocks a run tries before it gives its last result as it is. */
const BLOCK_ATTEMPTS = 3;

interface Run {
  /** Playwright's exit status; `null` when it was still waiting at RUN_LIMIT_MS. */
  status: number | null;
  output: string;
  /** The blocks it ran on, in order: one more each time another process took a port of the block. */
  blocks: number[];
}

describe("a stack's database step, under Playwright", () => {
  let work: string;
  let base: number;

  const log = () => (existsSync(join(work, 'log')) ? readFileSync(join(work, 'log'), 'utf8').trim().split('\n') : []);

  /** A run of Playwright on `base`'s block; on a port another process took meanwhile, again on a new block. */
  async function run(env: Record<string, string>, databaseTimeoutMs?: number): Promise<Run> {
    writeFileSync(join(work, 'playwright.config.ts'), configSource(work, databaseTimeoutMs));
    const blocks = [base];
    for (;;) {
      const { status, output } = await runOnBlock(env);
      if (!PORT_TAKEN.test(output) || blocks.length === BLOCK_ATTEMPTS) return { status, output, blocks };
      rmSync(join(work, 'log'), { force: true });
      base = await freeBase();
      blocks.push(base);
    }
  }

  function runOnBlock(env: Record<string, string>): Promise<Omit<Run, 'blocks'>> {
    return new Promise((done) => {
      const child = spawn(PLAYWRIGHT, ['test', '-c', join(work, 'playwright.config.ts')], {
        cwd: SAAS_DIR,
        detached: true,
        env: {
          PATH: `${join(work, 'bin')}:${process.env.PATH ?? ''}`,
          HOME: process.env.HOME ?? '',
          E2E_SAAS_PORT: String(base),
          VITE_DEV_PORT: String(base + 5),
          FAKE_LOG: join(work, 'log'),
          FAKE_SERVER: join(work, 'server.cjs'),
          FAKE_SQUATTER: join(work, 'squatter.cjs'),
          ...env,
        },
      });
      let output = '';
      child.stdout.on('data', (chunk: Buffer) => (output += chunk.toString()));
      child.stderr.on('data', (chunk: Buffer) => (output += chunk.toString()));
      const limit = setTimeout(() => process.kill(-(child.pid as number), 'SIGKILL'), RUN_LIMIT_MS);
      child.on('close', (status) => {
        clearTimeout(limit);
        done({ status, output });
      });
    });
  }

  /** The run reached its specs on a second block, chosen after `chosen` lost a port. */
  function ranOnAnotherBlock({ status, output, blocks }: Run, chosen: number): void {
    expect(status, output).toBe(0);
    expect(output).toContain('1 passed');
    expect(blocks).toEqual([chosen, base]);
    expect(base).not.toBe(chosen);
  }

  beforeEach(async () => {
    base = await freeBase();
    mkdirSync(join(HERE, '.artifacts'), { recursive: true });
    work = mkdtempSync(join(HERE, '.artifacts', 'database-step-'));
    mkdirSync(join(work, 'bin'));
    for (const [name, script] of Object.entries({ uv: FAKE_UV, docker: FAKE_DOCKER, pnpm: FAKE_PNPM })) {
      writeFileSync(join(work, 'bin', name), script);
      chmodSync(join(work, 'bin', name), 0o755);
    }
    writeFileSync(join(work, 'server.cjs'), FAKE_SERVER);
    writeFileSync(join(work, 'squatter.cjs'), FAKE_SQUATTER);
    writeFileSync(join(work, 'ran.spec.ts'), SPEC);
  });

  afterEach(() => {
    const squatter = join(work, 'taken', 'pid');
    const pid = existsSync(squatter) ? Number(readFileSync(squatter, 'utf8')) : NaN;
    if (Number.isInteger(pid)) {
      try {
        process.kill(pid);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error;
      }
    }
    rmSync(work, { recursive: true, force: true });
  });

  it("is not cut by a server's timeout: a slow first migration ends and the run reaches its specs", async () => {
    const { status, output } = await run({ FAKE_MIGRATE_SECONDS: String(SLOW_MIGRATION_SECONDS) });

    expect(output).not.toContain('Timed out waiting');
    expect(status, output).toBe(0);
    expect(output).toContain('1 passed');
    expect(output).toContain(`database.ts: saas_e2e_${base} created and migrated.`);
    expect(log()).toContain(`psql create database "saas_e2e_${base}"`);
  }, TEST_LIMIT_MS);

  it('starts no server of Django before the migration ends, each on the database it left ready', async () => {
    const { status, output } = await run({ FAKE_MIGRATE_SECONDS: '2' });

    expect(status, output).toBe(0);
    const steps = log().filter((line) => !line.startsWith('psql'));
    expect(steps.slice(0, 2)).toEqual([`migrate:start saas_e2e_${base}`, 'migrate:end']);
    const servers = steps.slice(2).filter((line) => line.startsWith('runserver'));
    expect(servers).toEqual(Array.from({ length: 4 }, () => `runserver saas_e2e_${base}`));
  }, TEST_LIMIT_MS);

  it('says at once that a migration failed, why, and starts no server, without waiting for any timeout', async () => {
    const { status, output } = await run({ FAKE_MIGRATE_FAILS: 'django.db.utils.ProgrammingError: boom' });

    expect(status, output).toBe(1);
    expect(output).toContain(`Could not migrate the e2e database saas_e2e_${base}`);
    expect(output).toContain('django.db.utils.ProgrammingError: boom');
    expect(output).toContain('Process from config.webServer was not able to start. Exit code: 1');
    expect(output).not.toContain('Timed out waiting');
    expect(output).not.toContain('1 passed');
    expect(log().filter((line) => line.startsWith('runserver'))).toEqual([]);
  }, TEST_LIMIT_MS);

  it("reuses a worktree's database: it creates nothing, migrates what is pending and the run goes on", async () => {
    const { status, output } = await run({ FAKE_DATABASE_EXISTS: '1' });

    expect(status, output).toBe(0);
    expect(output).toContain('1 passed');
    expect(output).toContain(`database.ts: saas_e2e_${base} migrated.`);
    expect(log().filter((line) => line.startsWith('psql create'))).toEqual([]);
    expect(log()).toContain('migrate:end');
  }, TEST_LIMIT_MS);

  it('moves to another block when a server of its own cannot open a port another process took after the choice', async () => {
    const chosen = base;

    ranOnAnotherBlock(await run({ FAKE_TAKE_VITE_PORT_ONCE: join(work, 'taken') }), chosen);
    expect(log().filter((line) => line.startsWith('migrate:start'))).toEqual([`migrate:start saas_e2e_${base}`]);
    expect(log().filter((line) => line.startsWith('runserver'))).toEqual(Array.from({ length: 4 }, () => `runserver saas_e2e_${base}`));
  }, TEST_LIMIT_MS);

  it('moves to another block when Playwright finds another server already answering on a port of it', async () => {
    const chosen = base;
    const squatter = createHttpServer((_, response) => response.end('not this run'));
    await new Promise<void>((listening, failed) => {
      squatter.once('error', failed);
      squatter.listen(chosen + 1, '127.0.0.1', listening);
    });
    try {
      ranOnAnotherBlock(await run({}), chosen);
    } finally {
      await new Promise((closed) => squatter.close(closed));
    }
  }, TEST_LIMIT_MS);

  it('gives a stuck migration a timeout of its own, saying what it was doing, and starts no server', async () => {
    const { status, output } = await run({ FAKE_MIGRATE_SECONDS: '60' }, 4_000);

    expect(status, output).toBe(1);
    expect(output).toContain('Timed out waiting 4000ms');
    expect(output).toContain(`[database] database.ts: preparing saas_e2e_${base}`);
    expect(log().filter((line) => line.startsWith('runserver'))).toEqual([]);
  }, TEST_LIMIT_MS);
});
