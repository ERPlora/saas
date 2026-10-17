// @vitest-environment node
// The Vite config is a contract with Django (`packages/live/live/spa.py` and `LIVE["spa"]` in
// `config/settings.py`): the dev server URLs and the manifest Django reads come from here. Node's
// environment: it loads the e2e's Playwright config (see «the tests that load Playwright» below).
import { existsSync, globSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, type Plugin, type PluginOption } from 'vite';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { VITE_ROOT_HEADER } from './tests/e2e/panel/project';
import e2eConfig, { browserWindow } from './tests/e2e/playwright.config';
import config, { FRONTEND_APPS } from './vite.config';

const SAAS_DIR = dirname(fileURLToPath(import.meta.url));
/** The shell stylesheet `erplora:tailwind-sources` appends the project's frontends to. */
const SHELL_GLOBAL_CSS = join(SAAS_DIR, 'packages', 'ui', 'src', 'shell', 'theme', 'global.css');

function plugins(options: PluginOption[] | undefined): Plugin[] {
  return ((options ?? []).flat(Infinity as 1) as unknown[]).filter(Boolean) as Plugin[];
}

function pluginNames(options: PluginOption[] | undefined): string[] {
  return plugins(options).flatMap((p) => ('name' in p ? [p.name] : []));
}

/** The apps of saas-next with a frontend: root directories next to `base/` holding a `frontend/` (no `apps/`, PLAN §20.2). */
function rootAppsWithFrontend(): string[] {
  return readdirSync(SAAS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'node_modules' && !entry.name.startsWith('.'))
    .filter((entry) => existsSync(join(SAAS_DIR, entry.name, 'frontend')))
    .map((entry) => entry.name);
}

/** The globs Tailwind reads class names from, relative to this directory (`not ` for an exclusion). */
function tailwindSources(): string[] {
  const sources = plugins(config.plugins).find((p) => p.name === 'erplora:tailwind-sources');
  if (!sources) throw new Error('plugin erplora:tailwind-sources not found');
  (sources.configResolved as unknown as (resolved: { root: string }) => void)({ root: SAAS_DIR });
  const transform = sources.transform as unknown as (code: string, id: string) => { code: string };
  const base = relative(dirname(SHELL_GLOBAL_CSS), SAAS_DIR);
  return [...transform('', SHELL_GLOBAL_CSS).code.matchAll(/^@source (not )?"([^"]+)";$/gm)].map(
    ([, not, glob]) => `${not ?? ''}${glob.slice(base.length + 1)}`,
  );
}

describe('vite.config', () => {
  it('runs every test file in a happy-dom with the browser behaviour Ionic relies on (vitest.setup.ts)', () => {
    expect(config.test?.setupFiles).toEqual(['./vitest.setup.ts']);
  });

  it('serves from the saas-next directory under /static/spa/ (dev and build alike)', () => {
    expect(config.root).toBe(SAAS_DIR);
    expect(config.base).toBe('/static/spa/');
  });

  it('uses the shared ERPlora plugins (Vue, Tailwind, defines)', () => {
    expect(pluginNames(config.plugins)).toEqual(expect.arrayContaining(['vite:vue', 'erplora:defines']));
  });

  it('builds the SPA and the public web into frontend/dist with the manifest Django reads', () => {
    const build = config.build ?? {};
    expect(build.outDir).toBe('frontend/dist');
    expect(build.emptyOutDir).toBe(true);
    // settings.LIVE["spa"]["manifest"] = SPA_DIST / ".vite" / "manifest.json"
    expect(build.manifest).toBe('.vite/manifest.json');
    expect(build.target).toBe('es2022');
    // The manifest keys of the two entries: settings.LIVE["spa"]["entry"] (the SPA) and
    // public.templatetags.public_assets.PUBLIC_ENTRY (the public web's Django templates, spec §8.4).
    expect(build.rollupOptions?.input).toEqual(['frontend/main.ts', 'frontend/public.ts']);
  });

  it("never copies a public directory into the build: `public/` is the public web's Django app", async () => {
    // Vite's default publicDir is `<root>/public`, which here is Python code and tests: they would end
    // up in frontend/dist and be served under /static/spa/. A real build proves the setting holds.
    expect(config.publicDir).toBe(false);
    const work = mkdtempSync(join(tmpdir(), 'saas-public-dir-'));
    writeFileSync(join(work, 'entry.ts'), 'export const entry = 1;\n');
    await build({
      configFile: false,
      logLevel: 'silent',
      root: SAAS_DIR,
      publicDir: config.publicDir,
      build: { outDir: join(work, 'dist'), emptyOutDir: true, rollupOptions: { input: join(work, 'entry.ts') } },
    });
    const files = readdirSync(join(work, 'dist'), { recursive: true }).map(String);
    expect(files).not.toContain('apps.py');
    expect(files.filter((file) => file.startsWith('tests'))).toEqual([]);
    expect(files.filter((file) => file.endsWith('.js')).length).toBeGreaterThan(0);
  });

  describe('VITE_DEV_PORT (a second checkout beside another one whose Vite owns 5174, as the e2e of a branch)', () => {
    afterEach(() => {
      vi.unstubAllEnvs();
      vi.resetModules();
    });

    /** vite.config.ts as a process with `port` in VITE_DEV_PORT (`undefined`: not exported) loads it. */
    async function configWith(port: string | undefined) {
      vi.stubEnv('VITE_DEV_PORT', port);
      vi.resetModules();
      return (await import('./vite.config')).default;
    }

    it("runs the dev server on localhost:5174 only (hub-next's owns 5173), with absolute asset URLs and HMR there", async () => {
      // live/spa.py points DEBUG pages at http://localhost:5174/static/spa/{@vite/client,frontend/main.ts}.
      expect((await configWith(undefined)).server).toMatchObject({
        host: 'localhost',
        port: 5174,
        strictPort: true,
        origin: 'http://localhost:5174',
        hmr: { host: 'localhost', port: 5174 },
      });
    });

    it('moves the dev server, its asset URLs and HMR to that port, the one Django reads too', async () => {
      expect((await configWith('5224')).server).toMatchObject({
        host: 'localhost',
        port: 5224,
        strictPort: true,
        origin: 'http://localhost:5224',
        hmr: { host: 'localhost', port: 5224 },
      });
    });

    it.each(['0', '65536', '70000', '-1', '5174x', ''])('refuses %j, which is no TCP port', async (port) => {
      await expect(configWith(port)).rejects.toThrow(/^VITE_DEV_PORT must be a TCP port/);
    });
  });

  it('says on every dev response which checkout it serves, so the e2e never tests another tree (tests/e2e/panel/project.ts)', () => {
    expect(config.server?.headers).toEqual({ [VITE_ROOT_HEADER]: encodeURIComponent(SAAS_DIR) });
  });

  it('lists the apps with a frontend: accounts, hubs, billing and fiscal (round 16: no marketplace; apps and public have none)', () => {
    expect(FRONTEND_APPS).toEqual(['accounts', 'hubs', 'billing', 'fiscal']);
  });

  it('knows every root app with a frontend/ (saas-next has no apps/, PLAN §20.2)', () => {
    expect(FRONTEND_APPS).toContain('accounts');
    expect(rootAppsWithFrontend().filter((app) => !FRONTEND_APPS.includes(app))).toEqual([]);
  });

  it("has Tailwind read the entry's and every app's frontend, never apps/ (gone) nor tests", () => {
    expect(tailwindSources()).toEqual([
      'frontend/**/*.{vue,ts}',
      ...FRONTEND_APPS.map((app) => `${app}/frontend/**/*.{vue,ts}`),
      'not **/*.test.ts',
    ]);
  });

  it('tests the shell entry and every app frontend in happy-dom', () => {
    expect(config.test?.environment).toBe('happy-dom');
    expect(config.test?.include).toEqual(
      expect.arrayContaining([
        'frontend/**/*.test.ts',
        ...FRONTEND_APPS.map((app) => `${app}/frontend/**/*.test.ts`),
        'vite.config.test.ts',
        'eslint.config.test.ts',
        'tsconfig.test.ts',
        // The e2e's helpers (global-setup.test.ts); its Playwright specs (`*.spec.ts`) stay out.
        'tests/e2e/*.test.ts',
      ]),
    );
    expect(config.test?.include?.filter((glob) => glob.startsWith('apps/'))).toEqual([]);
    expect(config.test?.include?.filter((glob) => glob.includes('spec'))).toEqual([]);
    // Vitest's default `exclude` drops every `vite.config.*`, this test included.
    expect(config.test?.exclude).toEqual(['**/node_modules/**', '**/dist/**']);
  });
});

// The e2e's browser (tests/e2e/playwright.config.ts): Ioan asked for headless by default (2026-10-14). A visible,
// slowed-down Chrome only when a run asks for it with E2E_HEADED=1 (`pnpm e2e:headed`); CI never opens one.
describe('e2e browser window', () => {
  it('is headless and at full speed by default', () => {
    expect(browserWindow({})).toEqual({ headless: true, slowMo: 0 });
  });

  it('is a visible Chrome, slowed down to follow it, only with E2E_HEADED=1', () => {
    expect(browserWindow({ E2E_HEADED: '1' })).toEqual({ headless: false, slowMo: 150 });
    expect(browserWindow({ E2E_HEADED: '0' })).toEqual({ headless: true, slowMo: 0 });
  });

  it('stays headless in CI even when a run asks for a window', () => {
    expect(browserWindow({ CI: '1', E2E_HEADED: '1' })).toEqual({ headless: true, slowMo: 0 });
  });

  it('is what the config uses for every project', () => {
    const window = browserWindow(process.env);
    expect(e2eConfig.use?.headless).toBe(window.headless);
    expect(e2eConfig.use?.launchOptions?.slowMo).toBe(window.slowMo);
    for (const project of e2eConfig.projects ?? []) expect(project.use?.headless).toBeUndefined();
  });

  it('`pnpm e2e` runs headless, `e2e:headed` opens the window and `e2e:ci` is the CI run', () => {
    const scripts = (JSON.parse(readFileSync(join(SAAS_DIR, 'package.json'), 'utf8')) as { scripts: Record<string, string> }).scripts;
    expect(scripts.e2e).toBe('playwright test -c tests/e2e/playwright.config.ts');
    expect(scripts['e2e:headed']).toBe('E2E_HEADED=1 playwright test -c tests/e2e/playwright.config.ts');
    expect(scripts['e2e:ci']).toBe('CI=1 playwright test -c tests/e2e/playwright.config.ts');
  });
});

/** A value import of `@playwright/test` or of an e2e config, which loads Playwright (`import type` loads nothing). */
const LOADS_PLAYWRIGHT = /^import (?!type )[^;]*?['"](?:@playwright\/test|[^'"]*\/playwright\.config)['"]/m;

/** The environment Vitest gives a test file: its docblock's (read anywhere in the file, as Vitest does), else the config's. */
function environmentOf(code: string): string | undefined {
  return code.match(/@(?:vitest|jest)-environment\s+([\w-]+)\b/)?.[1] ?? config.test?.environment;
}

// Playwright's bundled source-map-support takes a global `window` with an `XMLHttpRequest` for a browser: loaded in
// happy-dom, it fetched its own files by synchronous XHR from happy-dom's http://localhost:3000, and every request
// crashed a Node child process (`ECONNREFUSED 127.0.0.1:3000`) behind a green run. So whatever loads Playwright runs
// in Node's environment, as the other Node-side tests (eslint.config.test.ts, tsconfig.test.ts…) already do.
describe('the tests that load Playwright', () => {
  it("run this file in Node's environment, with no browser for Playwright to fetch from", () => {
    expect(['window', 'XMLHttpRequest'].filter((name) => name in globalThis)).toEqual([]);
  });

  it("give every test file that loads Playwright Node's environment", () => {
    const files = globSync(config.test?.include ?? [], { cwd: SAAS_DIR }).filter(
      (file) => !file.split(sep).includes('node_modules'),
    );
    const sources = new Map(files.map((file) => [file, readFileSync(join(SAAS_DIR, file), 'utf8')]));
    const loading = files.filter((file) => LOADS_PLAYWRIGHT.test(sources.get(file) ?? ''));
    expect(loading).toEqual(expect.arrayContaining(['vite.config.test.ts', join('tests', 'e2e', 'django-env.test.ts')]));
    expect(loading.filter((file) => environmentOf(sources.get(file) ?? '') !== 'node')).toEqual([]);
  });
});
