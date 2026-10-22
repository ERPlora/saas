// @vitest-environment node
// The e2e's stack (stack.ts): where its servers listen and which database they open. The shared one is
// today's (:8011, :8012, :8013, :8019 and the `saas` of `.env`); a second run at once moves the four ports
// together with E2E_SAAS_PORT and gets a database of its own, `saas_e2e_<port>`, created and migrated at
// the start (database.ts). Two runs on the one `saas`, or on a Hub's database whose `DB_NAME` a shell
// still exports (`relation "django_site" does not exist`), are refused before the first server starts.
// Node's environment: it loads the Playwright config (vite.config.test.ts, «the tests that load Playwright»).
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { panelMailDir, panelServers } from './panel/project';
import { publicServer, runId } from './playwright.config';
import { isE2eDatabase, stackFrom } from './stack';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHARED = stackFrom({});
const OWN = stackFrom({ E2E_SAAS_PORT: '8030' });

describe('stackFrom', () => {
  it("is today's stack when nothing is exported: :8011, :8012, :8013, :8019 and the database of `.env`", () => {
    expect(SHARED).toEqual({
      base: 8010,
      shared: true,
      publicPort: 8011,
      panelPort: 8012,
      panelMfaPort: 8013,
      hubDoublePort: 8019,
      database: undefined,
    });
  });

  it('moves the four ports together with E2E_SAAS_PORT, onto a database of its own', () => {
    expect(OWN).toEqual({
      base: 8030,
      shared: false,
      publicPort: 8031,
      panelPort: 8032,
      panelMfaPort: 8033,
      hubDoublePort: 8039,
      database: 'saas_e2e_8030',
    });
  });

  it('takes the e2e database the run exports, whatever its ports', () => {
    expect(stackFrom({ E2E_SAAS_PORT: '8030', DB_NAME: 'saas_fix_e2e_a' }).database).toBe('saas_fix_e2e_a');
    expect(stackFrom({ DB_NAME: 'saas_e2e_8010' }).database).toBe('saas_e2e_8010');
  });

  it('keeps the shared `saas` on the shared ports, exported or not', () => {
    expect(stackFrom({ DB_NAME: 'saas' }).database).toBeUndefined();
    expect(stackFrom({ E2E_SAAS_PORT: '8010' })).toEqual(SHARED);
    expect(stackFrom({ E2E_SAAS_PORT: '' })).toEqual(SHARED);
  });

  it.each(['0', '65527', '70000', '-1', '8030x', '80 30'])('refuses E2E_SAAS_PORT=%j, whose ports are no TCP ports', (port) => {
    expect(() => stackFrom({ E2E_SAAS_PORT: port })).toThrow(/^E2E_SAAS_PORT must be a TCP port/);
  });

  it('refuses the shared `saas` beside the shared stack: the other run writes into it', () => {
    expect(() => stackFrom({ E2E_SAAS_PORT: '8030', DB_NAME: 'saas' })).toThrow(
      'A stack beside the shared one (E2E_SAAS_PORT=8030) runs on its own e2e database, not on DB_NAME=saas: ' +
        'another run would write into it. Unset DB_NAME (`env -u DB_NAME`) for saas_e2e_8030, or export an e2e ' +
        'database (`saas_…` with `e2e` as one of its words) (tests/e2e/README.md, «Dos e2e del SaaS a la vez»).',
    );
  });

  it.each([
    ['beside the shared stack', { E2E_SAAS_PORT: '8030' }],
    ['on the shared ports', {}],
  ])("refuses a Hub's database that a shell still exports, %s", (_where, env) => {
    expect(() => stackFrom({ ...env, DB_NAME: 'hub_e2e_8030' })).toThrow(/not on DB_NAME=hub_e2e_8030|DB_NAME=hub_e2e_8030 is no database of the SaaS/);
  });

  it("names the way out of a Hub's database on the shared ports", () => {
    expect(() => stackFrom({ DB_NAME: 'hub' })).toThrow(
      'DB_NAME=hub is no database of the SaaS: the e2e runs on the shared `saas` (unset DB_NAME, `env -u DB_NAME`, ' +
        'and the one of `.env` is used) or on an e2e database (`saas_…` with `e2e` as one of its words).',
    );
  });

  it.each(['saas;drop', 'Saas_e2e', 'saas e2e'])('refuses DB_NAME=%j, which goes into a shell command as is', (name) => {
    expect(() => stackFrom({ DB_NAME: name })).toThrow(/^DB_NAME must be a plain database name/);
  });
});

describe('isE2eDatabase', () => {
  it.each(['saas_e2e_8030', 'saas_e2e', 'saas_fix_e2e_a'])('%s is one', (name) => {
    expect(isE2eDatabase(name)).toBe(true);
  });

  it.each(['saas', 'hub_e2e_8030', 'hub', 'test_saas_next_e2epar', 'saas_e2ex', 'saas_template'])('%s is not', (name) => {
    expect(isE2eDatabase(name)).toBe(false);
  });
});

describe("the stack's servers", () => {
  const panel = (stack = SHARED) => Object.fromEntries(panelServers(SAAS_DIR, 5443, stack).map((server) => [server.name, server]));

  it("start today's public server on the shared stack, on its database", () => {
    const server = publicServer(SAAS_DIR, SHARED);
    expect(server.command).toBe('uv run python manage.py runserver 127.0.0.1:8011 --novite --insecure --noreload');
    expect(server.url).toBe('http://127.0.0.1:8011/robots.txt');
    expect(server.env).not.toHaveProperty('DB_NAME');
  });

  it('create and migrate an own stack\'s database before its first server, which listens on its port', () => {
    const server = publicServer(SAAS_DIR, OWN);
    expect(server.command).toBe(
      'node tests/e2e/database.ts && uv run python manage.py runserver 127.0.0.1:8031 --novite --insecure --noreload',
    );
    expect(server.url).toBe('http://127.0.0.1:8031/robots.txt');
    expect(server.env).toMatchObject({ DEBUG: 'False', DB_NAME: 'saas_e2e_8030' });
  });

  it('send the public mails (the contact form, PUBLIC-G39) to a folder of the stack, never through SMTP', () => {
    expect(publicServer(SAAS_DIR, SHARED).env).toMatchObject({
      EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
      EMAIL_FILE_PATH: join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'public', 'mail'),
    });
    expect(publicServer(SAAS_DIR, OWN).env).toMatchObject({
      EMAIL_FILE_PATH: join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'public', 'mail-8030'),
    });
  });

  it("start today's panel on the shared stack: :8012, the Hub at :8019, its mail folder and a reused Vite", () => {
    const { 'panel-django': django, 'panel-vite': vite } = panel();
    expect(django.command).toBe('uv run python manage.py runserver 127.0.0.1:8012 --novite --noreload');
    expect(django.url).toBe('http://127.0.0.1:8012/healthz');
    expect(django.env).toMatchObject({
      HUB_INTERNAL_URL: 'http://127.0.0.1:8019',
      EMAIL_FILE_PATH: join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'panel', 'mail'),
    });
    expect(django.env).not.toHaveProperty('DB_NAME');
    expect(vite.reuseExistingServer).toBe(true);
  });

  it("start an own stack's panel on its ports, its database and a mail folder of its own", () => {
    const { 'panel-django': django } = panel(OWN);
    expect(django.command).toBe('uv run python manage.py runserver 127.0.0.1:8032 --novite --noreload');
    expect(django.url).toBe('http://127.0.0.1:8032/healthz');
    expect(django.env).toMatchObject({
      HUB_INTERNAL_URL: 'http://127.0.0.1:8039',
      EMAIL_FILE_PATH: join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'panel', 'mail-8030'),
      DB_NAME: 'saas_e2e_8030',
    });
  });

  // Two runs from one checkout on the same VITE_DEV_PORT: the second would reuse the first's Vite and lose it
  // when the first ends. An own stack starts and stops all of its servers, so the second is refused at once.
  it("never reuse a running Vite for an own stack", () => {
    expect(panel(OWN)['panel-vite'].reuseExistingServer).toBe(false);
  });

  // Two runs started in the same millisecond (two workers' e2e at once) wrote into one `test-results/<id>/`, and
  // the first to finish deleted the other's traces mid-spec (ENOENT on its `.playwright-artifacts-0`).
  it("keep each run's output folder apart: an own stack's run id carries its port", () => {
    const now = new Date('2026-10-21T00:48:45.810Z');
    expect(runId(SHARED, now)).toBe('2026-10-21T00-48-45-810Z');
    expect(runId(OWN, now)).toBe('2026-10-21T00-48-45-810Z-8030');
    expect(runId(stackFrom({ E2E_SAAS_PORT: '8040' }), now)).not.toBe(runId(OWN, now));
  });

  // The second factor is off by default (ACCOUNTS_MFA_ENABLED, phase 1): the panel the specs play on is production's.
  // Its flows (accounts/WORKBOOK.md, APP-ACCOUNTS-2) play on a twin with it on, a port above, on the same database,
  // Vite, mail folder and Hub double, so a spec signs in on either with the same helpers.
  it('start a twin of the panel with the second factor on, a port above, sharing the rest', () => {
    for (const stack of [SHARED, OWN]) {
      const { 'panel-django': django, 'panel-mfa-django': mfa } = panel(stack);
      expect(mfa.command).toBe(`uv run python manage.py runserver 127.0.0.1:${stack.panelMfaPort} --novite --noreload`);
      expect(mfa.url).toBe(`http://127.0.0.1:${stack.panelMfaPort}/healthz`);
      expect(mfa.reuseExistingServer).toBe(false);
      expect(mfa.env).toEqual({ ...django.env, ACCOUNTS_MFA_ENABLED: 'True' });
    }
  });

  it("leave the panel itself with the second factor as production has it (off)", () => {
    expect(panel()['panel-django'].env).not.toHaveProperty('ACCOUNTS_MFA_ENABLED');
    expect(panel(OWN)['panel-django'].env).not.toHaveProperty('ACCOUNTS_MFA_ENABLED');
  });

  it('read the mails of each stack where its Django writes them', () => {
    expect(panelMailDir(SHARED)).toBe(panel()['panel-django'].env?.EMAIL_FILE_PATH);
    expect(panelMailDir(OWN)).toBe(panel(OWN)['panel-django'].env?.EMAIL_FILE_PATH);
  });
});
