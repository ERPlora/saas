// The e2e's start (global-setup.ts) refuses a local database with unapplied migrations: the specs read
// what the migrations seed (hubs.0013's plans), and a database left behind by another branch made
// audit2.spec.ts fail on correct code. The check never applies anything: the database is shared.
import { describe, expect, it } from 'vitest';

import { assertMigrationsApplied, prepareDatabase, prepareRun, type CommandResult } from './global-setup';

const APPLIED: CommandResult = {
  status: 0,
  stdout: 'Planned operations:\n  No planned migration operations.\n',
  stderr: '',
};

const PENDING: CommandResult = {
  status: 1,
  stdout: 'Planned operations:\nhubs.0013_plans_in_the_database\n    Raw Python operation\n',
  stderr: '',
};

const UNREACHABLE: CommandResult = {
  status: 1,
  stdout: '',
  stderr: 'django.db.utils.OperationalError: connection to server at "127.0.0.1", port 5432 failed: Connection refused\n',
};

/** A `manage.py` double that answers `result` and records every call's arguments. */
function managePy(result: CommandResult): { calls: string[][]; run: (args: string[]) => CommandResult } {
  const calls: string[][] = [];
  return {
    calls,
    run: (args) => {
      calls.push(args);
      return result;
    },
  };
}

describe('assertMigrationsApplied', () => {
  it('passes when the local database has every migration applied', () => {
    const manage = managePy(APPLIED);

    expect(() => assertMigrationsApplied(manage.run)).not.toThrow();
    expect(manage.calls).toHaveLength(1);
  });

  it('stops the run with the pending migrations and how to apply them', () => {
    const manage = managePy(PENDING);

    expect(() => assertMigrationsApplied(manage.run)).toThrow(
      /^The local saas database has unapplied migrations \(hubs\.0013_plans_in_the_database\)\. Run `uv run python manage\.py migrate` from a checkout of main and retry\./,
    );
  });

  it("includes the command's output in the error", () => {
    const manage = managePy(PENDING);

    expect(() => assertMigrationsApplied(manage.run)).toThrow(PENDING.stdout.trim());
  });

  it('lists every pending migration, whatever the app', () => {
    const manage = managePy({
      status: 1,
      stdout:
        'Planned operations:\nbilling.0009_vat_rates\n    Add field rate to vatrate\nhubs.0013_plans_in_the_database\n    Raw Python operation\n',
      stderr: '',
    });

    expect(() => assertMigrationsApplied(manage.run)).toThrow(
      'unapplied migrations (billing.0009_vat_rates, hubs.0013_plans_in_the_database)',
    );
  });

  it('only ever runs migrate with --check, so nothing is applied', () => {
    for (const result of [APPLIED, PENDING, UNREACHABLE]) {
      const manage = managePy(result);

      try {
        assertMigrationsApplied(manage.run);
      } catch {
        // The failures are covered above; here only the commands matter.
      }

      expect(manage.calls.length).toBeGreaterThan(0);
      for (const args of manage.calls) {
        expect(args[0]).toBe('migrate');
        expect(args).toContain('--check');
      }
    }
  });

  it('does not blame migrations when the check itself cannot run', () => {
    const manage = managePy(UNREACHABLE);

    expect(() => assertMigrationsApplied(manage.run)).toThrow(
      /^Could not check the migrations of the local saas database \(`manage\.py migrate --check` exited with 1\)/,
    );
    expect(() => assertMigrationsApplied(manage.run)).toThrow('Connection refused');
    expect(() => assertMigrationsApplied(manage.run)).not.toThrow('unapplied migrations');
  });

  it('reports a check that never started (uv missing, killed)', () => {
    const manage = managePy({ status: null, stdout: '', stderr: 'spawnSync uv ENOENT' });

    expect(() => assertMigrationsApplied(manage.run)).toThrow(
      /^Could not check the migrations of the local saas database \(`manage\.py migrate --check` exited with no status\)[\s\S]*spawnSync uv ENOENT/,
    );
  });
});

describe('prepareDatabase', () => {
  it('seeds nothing when migrations are pending', () => {
    const seeded: string[] = [];

    expect(() => prepareDatabase(managePy(PENDING).run, (action) => seeded.push(action))).toThrow(
      'unapplied migrations',
    );
    expect(seeded).toEqual([]);
  });

  it('checks the migrations, then seeds, and clears the seed at the end', () => {
    const steps: string[] = [];
    const manage = managePy(APPLIED);

    const teardown = prepareDatabase(
      (args) => {
        steps.push(args[0]);
        return manage.run(args);
      },
      (action) => steps.push(action),
    );
    expect(steps).toEqual(['migrate', 'seed']);

    teardown();
    expect(steps).toEqual(['migrate', 'seed', 'clear']);
  });
});

// The run first checks that the panel's Vite (started or reused by Playwright before globalSetup) serves this
// checkout (panel/project.ts, assertViteOfThisTree): another tree's would have the specs test its frontend.
describe('prepareRun', () => {
  it("touches nothing in the database when the Vite is another checkout's", async () => {
    const manage = managePy(APPLIED);
    const seeded: string[] = [];

    await expect(
      prepareRun(
        () => Promise.reject(new Error('The Vite on :5174 serves /elsewhere/saas, not this checkout')),
        manage.run,
        (action) => seeded.push(action),
      ),
    ).rejects.toThrow('The Vite on :5174 serves /elsewhere/saas, not this checkout');
    expect(manage.calls).toEqual([]);
    expect(seeded).toEqual([]);
  });

  it("checks the Vite, then the migrations, then seeds", async () => {
    const steps: string[] = [];
    const manage = managePy(APPLIED);

    const teardown = await prepareRun(
      async () => {
        steps.push('vite');
      },
      (args) => {
        steps.push(args[0]);
        return manage.run(args);
      },
      (action) => steps.push(action),
    );
    expect(steps).toEqual(['vite', 'migrate', 'seed']);

    teardown();
    expect(steps).toEqual(['vite', 'migrate', 'seed', 'clear']);
  });
});
