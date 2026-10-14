// The Vite config is a contract with Django (`packages/live/live/spa.py` and `LIVE["spa"]` in
// `config/settings.py`): the dev server URLs and the manifest Django reads come from here.
import { existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, type Plugin, type PluginOption } from 'vite';
import { describe, expect, it } from 'vitest';

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

  it("runs the dev server on localhost:5174 only (hub-next's owns 5173), with absolute asset URLs and HMR there", () => {
    // live/spa.py points DEBUG pages at http://localhost:5174/static/spa/{@vite/client,frontend/main.ts}.
    expect(config.server).toMatchObject({
      host: 'localhost',
      port: 5174,
      strictPort: true,
      origin: 'http://localhost:5174',
      hmr: { host: 'localhost', port: 5174 },
    });
  });

  it('lists the apps with a frontend: accounts, hubs and billing (round 16: no marketplace; apps and public have none)', () => {
    expect(FRONTEND_APPS).toEqual(['accounts', 'hubs', 'billing']);
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
      ]),
    );
    expect(config.test?.include?.filter((glob) => glob.startsWith('apps/'))).toEqual([]);
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
