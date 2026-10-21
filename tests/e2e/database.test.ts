// @vitest-environment node
// The e2e database of a stack beside the shared one (database.ts): the e2e's first server runs
// `node tests/e2e/database.ts`, which creates it when missing and migrates it, and `--drop` deletes it once the
// run is over. Two runs on the one local `saas` wrote into each other's data, and only one SaaS e2e could run
// at a time; each stack now runs on its own e2e database, and these commands never touch any other (`saas`, a
// Hub's, the test databases…), the same rules as the Hub's (hub tests/e2e/database.ts).
// flow: ninguno — FIX accounts (aislar los datos de cada ejecución e2e del SaaS)
import { describe, expect, it } from 'vitest';

import { adminSql, dropDatabase, prepareDatabase, runCli, type AdminSql } from './database';
import type { CommandResult, ManagePy } from './global-setup';
import { stackFrom } from './stack';

const OK = (stdout = ''): CommandResult => ({ status: 0, stdout, stderr: '' });
const FAILED = (stderr: string): CommandResult => ({ status: 1, stdout: '', stderr });

/** A Postgres double: which databases exist, every statement it got, and an optional failure per statement. */
function fakePostgres(existing: string[], fail: Record<string, string> = {}): { sql: AdminSql; statements: string[] } {
  const statements: string[] = [];
  const databases = new Set(existing);
  return {
    statements,
    sql: (statement) => {
      statements.push(statement);
      const failure = Object.entries(fail).find(([prefix]) => statement.startsWith(prefix));
      if (failure) return FAILED(failure[1]);
      const asked = /^select 1 from pg_database where datname = '([a-z0-9_]+)'$/.exec(statement);
      if (asked) return OK(databases.has(asked[1]) ? '1\n' : '');
      const created = /^create database "([a-z0-9_]+)"$/.exec(statement);
      if (created) databases.add(created[1]);
      const dropped = /^drop database if exists "([a-z0-9_]+)"$/.exec(statement);
      if (dropped) databases.delete(dropped[1]);
      return OK();
    },
  };
}

/** A `manage.py` double: records every call and answers `answers[command]` (success by default). */
function fakeManage(answers: Record<string, CommandResult> = {}): { manage: ManagePy; calls: string[][] } {
  const calls: string[][] = [];
  return { calls, manage: (args) => (calls.push(args), answers[args[0]] ?? OK()) };
}

const NOT_E2E = ['saas', 'hub', 'hub_e2e_8030', 'postgres', 'test_saas_next_e2epar'];

describe('prepareDatabase', () => {
  it('creates a missing e2e database and migrates it', () => {
    const postgres = fakePostgres([]);
    const { manage, calls } = fakeManage();

    expect(prepareDatabase('saas_e2e_8030', { sql: postgres.sql, manage })).toEqual({ created: true });
    expect(postgres.statements).toEqual([
      "select 1 from pg_database where datname = 'saas_e2e_8030'",
      'create database "saas_e2e_8030"',
    ]);
    expect(calls).toEqual([['migrate', '--no-input']]);
  });

  it('only migrates one that exists: it is idempotent and keeps its rows', () => {
    const postgres = fakePostgres(['saas_e2e_8030']);
    const { manage, calls } = fakeManage();

    expect(prepareDatabase('saas_e2e_8030', { sql: postgres.sql, manage })).toEqual({ created: false });
    expect(postgres.statements).toEqual(["select 1 from pg_database where datname = 'saas_e2e_8030'"]);
    expect(calls).toEqual([['migrate', '--no-input']]);
  });

  it.each(NOT_E2E)('refuses %s, no e2e database, touching nothing', (name) => {
    const postgres = fakePostgres([name]);
    const { manage, calls } = fakeManage();

    expect(() => prepareDatabase(name, { sql: postgres.sql, manage })).toThrow(`DB_NAME=${name} is no e2e database`);
    expect(postgres.statements).toEqual([]);
    expect(calls).toEqual([]);
  });

  it('stops at the failed step, naming it and saying what the server said', () => {
    const unreachable = fakePostgres([], { select: 'connection to server on socket failed: No such file or directory' });
    expect(() => prepareDatabase('saas_e2e_8030', { sql: unreachable.sql, ...fakeManage() })).toThrow(
      /^Could not read Postgres's databases[^\n]*\nconnection to server on socket failed/,
    );

    const refused = fakePostgres([], { create: 'ERROR:  permission denied to create database' });
    const notMigrated = fakeManage();
    expect(() => prepareDatabase('saas_e2e_8030', { sql: refused.sql, manage: notMigrated.manage })).toThrow(
      /^Could not create the e2e database saas_e2e_8030[^\n]*\nERROR: {2}permission denied to create database/,
    );
    expect(notMigrated.calls).toEqual([]);

    const broken = fakeManage({ migrate: { status: 1, stdout: 'Operations to perform:', stderr: 'django.db.utils.ProgrammingError: boom' } });
    expect(() => prepareDatabase('saas_e2e_8030', { sql: fakePostgres([]).sql, manage: broken.manage })).toThrow(
      /^Could not migrate the e2e database saas_e2e_8030: `manage\.py migrate --no-input` exited with 1:\nOperations to perform:\ndjango\.db\.utils\.ProgrammingError: boom$/,
    );

    const killed = fakeManage({ migrate: { status: null, stdout: '', stderr: 'killed' } });
    expect(() => prepareDatabase('saas_e2e_8030', { sql: fakePostgres([]).sql, manage: killed.manage })).toThrow(
      '`manage.py migrate --no-input` exited with no status:\nkilled',
    );
  });
});

describe('dropDatabase', () => {
  it('drops an e2e database, and a missing one is no error', () => {
    const postgres = fakePostgres(['saas_e2e_8030']);

    dropDatabase('saas_e2e_8030', { sql: postgres.sql });
    dropDatabase('saas_e2e_8030', { sql: postgres.sql });

    expect(postgres.statements).toEqual(['drop database if exists "saas_e2e_8030"', 'drop database if exists "saas_e2e_8030"']);
  });

  it.each(NOT_E2E)('refuses %s, no e2e database', (name) => {
    const postgres = fakePostgres([name]);
    expect(() => dropDatabase(name, { sql: postgres.sql })).toThrow(`DB_NAME=${name} is no e2e database`);
    expect(postgres.statements).toEqual([]);
  });

  it('never forces it: with a runserver still connected it fails saying to stop it first', () => {
    const postgres = fakePostgres(['saas_e2e_8030'], {
      drop: 'ERROR:  database "saas_e2e_8030" is being accessed by other users\nDETAIL:  There is 1 other session using the database.',
    });

    expect(() => dropDatabase('saas_e2e_8030', { sql: postgres.sql })).toThrow(
      /^The e2e database saas_e2e_8030 is still in use \(its runserver\?\): stop it and retry\.\nERROR: {2}database "saas_e2e_8030" is being accessed by other users/,
    );
    expect(postgres.statements[0]).not.toMatch(/force/i);
  });
});

describe('adminSql', () => {
  it("runs one statement with compose's psql, as its superuser, on `postgres`, stopping at the first error", () => {
    const runs: { file: string; args: string[]; cwd?: string; env?: NodeJS.ProcessEnv }[] = [];
    const sql = adminSql(
      (file, args, options) => {
        runs.push({ file, args, cwd: options.cwd, env: options.env });
        return { status: 0, stdout: '1\n', stderr: '' };
      },
      { COMPOSE_FILE: '/somewhere/compose.yaml' },
    );

    expect(sql('select 1')).toEqual({ status: 0, stdout: '1\n', stderr: '' });
    expect(runs).toEqual([
      {
        file: 'docker',
        args: ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At', '-c', 'select 1'],
        cwd: expect.stringMatching(/[^/]$/),
        env: { COMPOSE_FILE: '/somewhere/compose.yaml' },
      },
    ]);
  });

  it('says why docker could not run at all', () => {
    const sql = adminSql(() => ({ status: null, stdout: null, stderr: null, error: new Error('spawn docker ENOENT') }), {});

    expect(sql('select 1')).toEqual({ status: null, stdout: '', stderr: 'spawn docker ENOENT' });
  });
});

describe('runCli', () => {
  function io() {
    const out: string[] = [];
    const err: string[] = [];
    return { out, err, print: (line: string) => out.push(line), fail: (line: string) => err.push(line) };
  }

  it("prepares the own stack's database and says so", () => {
    const lines = io();
    const { manage } = fakeManage();

    expect(runCli([], { stack: stackFrom({ E2E_SAAS_PORT: '8030' }), sql: fakePostgres([]).sql, manage, ...lines })).toBe(0);
    expect(lines.out).toEqual(['database.ts: saas_e2e_8030 created and migrated.']);
    expect(lines.err).toEqual([]);
  });

  it('drops it with --drop', () => {
    const lines = io();
    const postgres = fakePostgres(['saas_e2e_8030']);

    expect(runCli(['--drop'], { stack: stackFrom({ E2E_SAAS_PORT: '8030' }), sql: postgres.sql, ...fakeManage(), ...lines })).toBe(0);
    expect(postgres.statements).toEqual(['drop database if exists "saas_e2e_8030"']);
    expect(lines.out).toEqual(['database.ts: saas_e2e_8030 dropped.']);
  });

  it("touches nothing on the shared stack, whose database is `.env`'s `saas`", () => {
    for (const args of [[], ['--drop']]) {
      const lines = io();
      const postgres = fakePostgres(['saas']);
      const { manage, calls } = fakeManage();

      expect(runCli(args, { stack: stackFrom({}), sql: postgres.sql, manage, ...lines })).toBe(1);
      expect(lines.err).toEqual([
        'database.ts: the shared stack runs on the `saas` of `.env`, which this command never creates, migrates or ' +
          'drops: export E2E_SAAS_PORT=<another port> for a stack of its own (tests/e2e/README.md, «Dos e2e del SaaS a la vez»).',
      ]);
      expect(postgres.statements).toEqual([]);
      expect(calls).toEqual([]);
    }
  });

  it('fails with what went wrong, and 2 with an unknown argument', () => {
    const lines = io();
    const refused = fakePostgres([], { create: 'ERROR:  permission denied to create database' });
    expect(runCli([], { stack: stackFrom({ E2E_SAAS_PORT: '8030' }), sql: refused.sql, ...fakeManage(), ...lines })).toBe(1);
    expect(lines.err[0]).toMatch(/^database\.ts: Could not create the e2e database saas_e2e_8030/);

    const usage = io();
    expect(runCli(['--force'], { stack: stackFrom({ E2E_SAAS_PORT: '8030' }), sql: fakePostgres([]).sql, ...fakeManage(), ...usage })).toBe(2);
    expect(usage.err).toEqual(['database.ts: unknown argument --force. Usage: node tests/e2e/database.ts [--drop]']);
  });
});
