// @vitest-environment node
// The environment of every Django process the e2e starts (django-env.ts): Django reads DEBUG as a
// boolean (config/settings.py) and Playwright the same variable as the namespaces of its logs, so
// `DEBUG=pw:webserver` reached `manage.py` and stopped the run before the first spec. Node's
// environment: it loads the Playwright config (vite.config.test.ts, «the tests that load Playwright»).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { djangoEnv } from './django-env';
import e2eConfig from './playwright.config';

describe('djangoEnv', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("sets DEBUG on or off over Playwright's namespaces", () => {
    expect(djangoEnv(true, { DEBUG: 'pw:webserver' }).DEBUG).toBe('True');
    expect(djangoEnv(false, { DEBUG: 'pw:*' }).DEBUG).toBe('False');
  });

  it('sets it when the environment has none', () => {
    expect(djangoEnv(true, {})).toEqual({ DEBUG: 'True' });
    expect(djangoEnv(false, {})).toEqual({ DEBUG: 'False' });
  });

  it('keeps the rest of the environment (uv, the database of `.env`)', () => {
    expect(djangoEnv(true, { DEBUG: 'pw:webserver', PATH: '/usr/bin', DB_NAME: 'saas' })).toEqual({
      DEBUG: 'True',
      PATH: '/usr/bin',
      DB_NAME: 'saas',
    });
  });

  it('leaves out the variables that are not set', () => {
    expect(djangoEnv(true, { UNSET: undefined })).not.toHaveProperty('UNSET');
  });

  it("does not change the environment it reads (Playwright's own logs still read DEBUG)", () => {
    const env = { DEBUG: 'pw:webserver' };

    djangoEnv(true, env);

    expect(env).toEqual({ DEBUG: 'pw:webserver' });
  });

  it("reads this process's environment by default", () => {
    vi.stubEnv('DEBUG', 'pw:webserver');

    expect(djangoEnv(true)).toMatchObject({ DEBUG: 'True', PATH: process.env.PATH });
    expect(process.env.DEBUG).toBe('pw:webserver');
  });
});

// Playwright starts its servers with its own environment under each one's `env`, DEBUG included: a Django
// server that does not say its DEBUG would get Playwright's.
describe("the e2e's Django servers", () => {
  /** `variable` in the environment of each Django server, by the address it runs on. */
  function byServer(variable: string): Record<string, string | undefined> {
    const servers = [e2eConfig.webServer ?? []].flat().filter((server) => server.command.includes('manage.py'));
    return Object.fromEntries(servers.map((server) => [/runserver (\S+)/.exec(server.command)?.[1], server.env?.[variable]]));
  }

  it('each says its DEBUG: the public one (:8011) off, the panel\'s (:8012) on', () => {
    expect(byServer('DEBUG')).toEqual({
      '127.0.0.1:8011': 'False',
      '127.0.0.1:8012': 'True',
    });
  });

  // Every spec of the panel signs in from 127.0.0.1, and allauth allows 30 sign-ins a minute per address:
  // one spec repeated (`--repeat-each=6`) got 429 at the sign-in. Only that server raises the limit
  // (config/settings.py, E2E_RELAX_LOGIN_RATE_LIMIT); the public one signs nobody in, and production
  // refuses to start with it.
  it("only the panel's (:8012) raises allauth's sign-in limit", () => {
    expect(byServer('E2E_RELAX_LOGIN_RATE_LIMIT')).toEqual({
      '127.0.0.1:8011': undefined,
      '127.0.0.1:8012': 'True',
    });
  });
});
