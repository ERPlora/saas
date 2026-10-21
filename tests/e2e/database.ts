// The e2e database of a stack beside the shared one (`stack.ts`), so that two runs at once never write into each
// other's data: before, every run shared the local `saas`, and only one SaaS e2e could run at a time.
//
//   E2E_SAAS_PORT=8030 node tests/e2e/database.ts          creates saas_e2e_8030 when missing and migrates it
//   E2E_SAAS_PORT=8030 node tests/e2e/database.ts --drop   drops it once the run's servers are stopped
//
// The e2e runs the first itself, before its first server (playwright.config.ts, `publicServer`): it is idempotent
// and keeps the rows of a database that exists. The second is the run's to call at the end. Only e2e databases
// (`isE2eDatabase`): the shared stack's `saas`, the Hub's and every other one are refused untouched. A drop is never
// forced: with a connection open (a server still up) it fails and says so. Postgres is compose.yaml's
// (`COMPOSE_FILE` points at it from a checkout elsewhere), reached as its superuser `hub`, like the Hub's
// tests/e2e/database.ts. Run by Node itself, without Playwright's loader: its imports say their `.ts`.
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { djangoEnv } from './django-env.ts';
import type { CommandResult, ManagePy } from './global-setup.ts';
import { isE2eDatabase, type Stack, STACK } from './stack.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
/** Where compose.yaml lives: the root of erplora-next, above saas/ and every saas-wt-*. */
const REPO_DIR = resolve(SAAS_DIR, '..');
const USAGE = 'Usage: node tests/e2e/database.ts [--drop]';

/** Runs one SQL statement on Postgres's maintenance database `postgres`. */
export type AdminSql = (statement: string) => CommandResult;

/** What `spawnSync` returns, as far as these commands read it. */
interface Spawned {
  status: number | null;
  stdout: string | null;
  stderr: string | null;
  error?: Error;
}

/** `spawnSync`, or a double of it. */
export type Spawn = (file: string, args: string[], options: { cwd?: string; encoding: 'utf8'; env?: NodeJS.ProcessEnv }) => Spawned;

function resultOf(spawned: Spawned): CommandResult {
  return {
    status: spawned.status,
    stdout: spawned.stdout ?? '',
    stderr: [spawned.stderr, spawned.error?.message].filter(Boolean).join('\n'),
  };
}

/** `psql` in compose's Postgres, as `hub`, on `postgres`, stopping at the first error. */
export function adminSql(spawn: Spawn = spawnSync, env: NodeJS.ProcessEnv = process.env): AdminSql {
  return (statement) => {
    const args = ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At', '-c', statement];
    return resultOf(spawn('docker', args, { cwd: REPO_DIR, encoding: 'utf8', env }));
  };
}

/** `manage.py` from saas/ on `stack`'s database, with DEBUG on like the e2e's other Django processes. */
export function managePy(stack: Pick<Stack, 'database'>, spawn: Spawn = spawnSync): ManagePy {
  return (args) => resultOf(spawn('uv', ['run', 'python', 'manage.py', ...args], { cwd: SAAS_DIR, encoding: 'utf8', env: djangoEnv(true, process.env, stack) }));
}

function refuseUnlessE2e(name: string): void {
  if (!isE2eDatabase(name)) {
    throw new Error(
      `DB_NAME=${name} is no e2e database: database.ts only creates, migrates and drops a stack's own, ` +
        '`saas_…` with `e2e` as one of its words (`saas_e2e_8030`).',
    );
  }
}

/** What a failed command said, after the line that names it. */
function said(result: CommandResult): string {
  const exit = result.status === null ? 'no status' : String(result.status);
  const output = [result.stdout.trim(), result.stderr.trim()].filter(Boolean).join('\n');
  return `exited with ${exit}:\n${output}`;
}

const MIGRATE = ['migrate', '--no-input'];

/** Creates the e2e database `name` when missing and applies every migration (they seed what the specs read: the
 * plans of hubs.0013). */
export function prepareDatabase(name: string, { sql, manage }: { sql: AdminSql; manage: ManagePy }): { created: boolean } {
  refuseUnlessE2e(name);
  const found = sql(`select 1 from pg_database where datname = '${name}'`);
  if (found.status !== 0) throw new Error(`Could not read Postgres's databases: psql ${said(found)}`);
  const created = found.stdout.trim() !== '1';
  if (created) {
    const create = sql(`create database "${name}"`);
    if (create.status !== 0) throw new Error(`Could not create the e2e database ${name}: psql ${said(create)}`);
  }
  const migrate = manage(MIGRATE);
  if (migrate.status !== 0) {
    throw new Error(`Could not migrate the e2e database ${name}: \`manage.py ${MIGRATE.join(' ')}\` ${said(migrate)}`);
  }
  return { created };
}

/** Drops the e2e database `name` (a missing one is no error); never while a connection is open. */
export function dropDatabase(name: string, { sql }: { sql: AdminSql }): void {
  refuseUnlessE2e(name);
  const drop = sql(`drop database if exists "${name}"`);
  if (drop.status === 0) return;
  if (drop.stderr.includes('is being accessed by other users')) {
    throw new Error(`The e2e database ${name} is still in use (its runserver?): stop it and retry.\n${drop.stderr.trim()}`);
  }
  throw new Error(`Could not drop the e2e database ${name}: psql ${said(drop)}`);
}

/** The command line: prepares `stack`'s database, or drops it with `--drop`. Returns the exit status. */
export function runCli(
  args: string[],
  deps: {
    stack: Pick<Stack, 'database'>;
    sql: AdminSql;
    manage: ManagePy;
    print: (line: string) => void;
    fail: (line: string) => void;
  },
): number {
  const [flag, ...rest] = args;
  if ((flag !== undefined && flag !== '--drop') || rest.length > 0) {
    deps.fail(`database.ts: unknown argument ${flag !== '--drop' ? flag : rest[0]}. ${USAGE}`);
    return 2;
  }
  const name = deps.stack.database;
  if (name === undefined) {
    deps.fail(
      'database.ts: the shared stack runs on the `saas` of `.env`, which this command never creates, migrates or drops: ' +
        'export E2E_SAAS_PORT=<another port> for a stack of its own (tests/e2e/README.md, «Dos e2e del SaaS a la vez»).',
    );
    return 1;
  }
  try {
    if (flag === '--drop') {
      dropDatabase(name, deps);
      deps.print(`database.ts: ${name} dropped.`);
    } else {
      const { created } = prepareDatabase(name, deps);
      deps.print(`database.ts: ${name} ${created ? 'created and migrated' : 'migrated'}.`);
    }
    return 0;
  } catch (error) {
    deps.fail(`database.ts: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

// Run as a script (not imported by a test): the run's stack, which already refused a database that is not the
// SaaS's, or `saas` beside the shared stack, when stack.ts was loaded.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCli(process.argv.slice(2), {
    stack: STACK,
    sql: adminSql(),
    manage: managePy(STACK),
    print: (line) => console.log(line),
    fail: (line) => console.error(line),
  });
}
