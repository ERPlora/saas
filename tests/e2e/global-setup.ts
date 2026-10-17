// The e2e's start. It first refuses a Vite of another checkout on the panel's Vite port (Playwright starts
// or reuses its servers before globalSetup; panel/project.ts): the specs would test that tree's frontend.
// Then it refuses a local database with unapplied migrations: the specs read what the migrations seed
// (hubs.0013's plans), the run never migrates the database other sessions share, and one left behind
// by another branch failed specs on correct code (audit2.spec.ts, 2026-10-16). Then it
// seeds the app the store's specs open (store_docs_seed.py) and returns the teardown that removes it,
// so the local database is left as it was even when a spec fails.
import { execFileSync, spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { djangoEnv } from './django-env';
import { assertViteOfThisTree, VITE_PORT } from './panel/project';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');

/** What a `manage.py` command left: its exit status (`null` when it never ran or was killed) and output. */
export interface CommandResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

/** Runs `manage.py` with `args` against the local database of the e2e. */
export type ManagePy = (args: string[]) => CommandResult;

/** Lists what `migrate` would apply and exits 1 if anything (Django returns before applying a thing). */
const MIGRATE_CHECK = ['migrate', '--check', '--plan', '--no-color'];

/** The migrations of `migrate --plan`'s output: the unindented lines under its header. */
function plannedMigrations(output: string): string[] {
  const lines = output.split(/\r?\n/);
  const header = lines.findIndex((line) => line.trim() === 'Planned operations:');
  if (header < 0) return [];
  return lines.slice(header + 1).filter((line) => line.trim() !== '' && !/^\s/.test(line));
}

/** Throws, without touching the database, unless `manage` finds every migration applied. */
export function assertMigrationsApplied(manage: ManagePy): void {
  const check = manage(MIGRATE_CHECK);
  if (check.status === 0) return;
  const pending = check.status === 1 ? plannedMigrations(check.stdout) : [];
  if (pending.length > 0) {
    throw new Error(
      `The local saas database has unapplied migrations (${pending.join(', ')}). ` +
        'Run `uv run python manage.py migrate` from a checkout of main and retry.\n\n' +
        `manage.py ${MIGRATE_CHECK.join(' ')}:\n${check.stdout.trim()}`,
    );
  }
  const output = [check.stdout.trim(), check.stderr.trim()].filter(Boolean).join('\n');
  const exit = check.status === null ? 'no status' : String(check.status);
  throw new Error(
    `Could not check the migrations of the local saas database (\`manage.py migrate --check\` exited with ${exit}):\n${output}`,
  );
}

/** Checks the migrations, then seeds; returns the teardown that clears the seed. */
export function prepareDatabase(manage: ManagePy, seed: (action: 'seed' | 'clear') => void): () => void {
  assertMigrationsApplied(manage);
  seed('seed');
  return () => seed('clear');
}

/** Checks the panel's Vite (`checkVite`) before touching the database, then `prepareDatabase`. */
export async function prepareRun(
  checkVite: () => Promise<void>,
  manage: ManagePy,
  seed: (action: 'seed' | 'clear') => void,
): Promise<() => void> {
  await checkVite();
  return prepareDatabase(manage, seed);
}

/** `manage.py` from saas/, with DEBUG on like the seeds (`djangoEnv`; `.env` for the rest). */
function runManagePy(args: string[]): CommandResult {
  const result = spawnSync('uv', ['run', 'python', 'manage.py', ...args], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
  });
  return {
    status: result.status,
    stdout: result.stdout ?? '',
    stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
  };
}

function seedStoreDocs(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/store_docs_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'inherit',
  });
}

export default function globalSetup(): Promise<() => void> {
  return prepareRun(() => assertViteOfThisTree(SAAS_DIR, VITE_PORT), runManagePy, seedStoreDocs);
}
