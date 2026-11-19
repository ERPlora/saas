import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
vi.mock('@erplora/ui/components', async (original) => (await import('./__tests__/main-doubles')).componentsDouble(original));
vi.mock('@erplora/ui/sdk', async (original) => (await import('./__tests__/main-doubles')).sdkDouble(original));

import { fakeShell, main, setUpMain } from './__tests__/main-boot';
import entryEn from './locale/en.json';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..');

/** The apps with a frontend: root directories next to `base/` holding a `frontend/` (there is no `apps/` folder). */
function rootAppsWithFrontend(): string[] {
  return readdirSync(SAAS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'node_modules' && !entry.name.startsWith('.'))
    .filter((entry) => existsSync(join(SAAS_DIR, entry.name, 'frontend')))
    .map((entry) => entry.name)
    .sort();
}

/** `import.meta.glob('../{a,b}/frontend/<rest>')` of main.ts → `[rest, [a, b]]`, one per glob. */
function globbedApps(): Array<[string, string[]]> {
  const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
  return [...source.matchAll(/import\.meta\.glob<\w+>\(\s*'([^']*)'/g)].map(([, glob]) => {
    const match = /^\.\.\/\{([^}]+)\}\/frontend\/(.+)$/.exec(glob);
    if (!match) throw new Error(`main.ts globs ${glob}, not ../{<app>,…}/frontend/…`);
    return [match[2], match[1].split(',')];
  });
}

setUpMain();

describe('import order guards', () => {
  it('imports the shell before anything that loads @ionic/vue (the SDK, the generated routes)', () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const runtimeImports = [...source.matchAll(/^import\s+(?!type\b)[^;]*?from\s+'([^']+)';/gms)].map((m) => m[1]);
    expect(runtimeImports[0]).toBe('@erplora/ui/shell');
  });

  it('puts «Skip to content» first in the page, in the language of the page', async () => {
    fakeShell();
    document.documentElement.lang = 'es';
    await main.boot({});
    const nav = document.body.firstElementChild as HTMLElement;
    const link = nav.querySelector('a') as HTMLAnchorElement;
    expect(link.id).toBe('skip-to-content');
    expect(link.textContent).toBe('Saltar al contenido');
    expect(nav.getAttribute('aria-label')).toBe('Atajos');
    expect(entryEn.saas.skipLink).toBe('Skip to content');
    expect(entryEn.saas.skipNav).toBe('Shortcuts');
  });

  it("loads the panel's chrome (skip link, touch targets, topbar) after the shell's theme (panel-chrome.css)", () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const chrome = source.indexOf("import './panel-chrome.css';");
    expect(chrome).toBeGreaterThan(-1);
    expect(chrome).toBeGreaterThan(source.indexOf("import './fonts.css';"));
  });

  it("loads the SaaS's typeface after the shell's theme, so it wins the cascade (fonts.css)", () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const fonts = source.indexOf("import './fonts.css';");
    expect(fonts).toBeGreaterThan(-1);
    expect(fonts).toBeGreaterThan(source.indexOf("from '@erplora/ui/shell';"));
  });

  it("takes the panel's fill layout from the shell's theme, with no sheet of its own (the `.panel-fill` chain)", () => {
    // The `.panel-fill` height chain lives in @erplora/ui (polish.css, loaded by createShell; guarded there by
    // AppPage.test.ts): the SaaS keeps no copy that could drift from it.
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    expect(source).not.toContain('panel-fill.css');
    expect(existsSync(join(HERE, 'panel-fill.css'))).toBe(false);
    const polish = readFileSync(join(SAAS_DIR, 'packages', 'ui', 'src', 'shell', 'theme', 'polish.css'), 'utf8');
    expect(polish).toMatch(/\.panel-fill\s*\{/);
  });

  it('keeps every <app>/frontend/routes.ts free of runtime imports: Vite hoists eager globs above the shell', () => {
    const files = rootAppsWithFrontend()
      .map((app) => join(SAAS_DIR, app, 'frontend', 'routes.ts'))
      .filter((file) => existsSync(file));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const staticImports = [...source.matchAll(/^import\s+(?!type\b).*$/gm)].map((m) => m[0]);
      expect(staticImports, `${file}: pages load with () => import('./pages/…')`).toEqual([]);
    }
  });
});

describe('root app guards (the SaaS has no apps/ folder: its apps live next to base/)', () => {
  it('globs the routes and the catalogues of the same apps', () => {
    const globs = globbedApps();
    expect(globs.map(([rest]) => rest)).toEqual(['routes.ts', 'locale/*.json']);
    expect(globs[1][1]).toEqual(globs[0][1]);
  });

  it("globs the apps with a frontend: accounts, hubs, billing, fiscal and the panel's assistant (no marketplace; apps and public have none)", () => {
    const [[, globbed]] = globbedApps();
    expect(globbed).toEqual(['accounts', 'hubs', 'billing', 'fiscal', 'assistant']);
  });

  it('globs every root app with a frontend/: one left out would lose its pages and texts silently', () => {
    const apps = rootAppsWithFrontend();
    expect(apps).toContain('accounts');
    const [[, globbed]] = globbedApps();
    expect(apps.filter((app) => !globbed.includes(app))).toEqual([]);
  });

  it("typechecks the frontend of every app main.ts globs (the SPA's project, tsconfig.app.json)", () => {
    const tsconfig = JSON.parse(readFileSync(join(SAAS_DIR, 'tsconfig.app.json'), 'utf8')) as { include: string[] };
    const [[, globbed]] = globbedApps();
    expect(tsconfig.include).toEqual(expect.arrayContaining(globbed.map((app) => `${app}/frontend/**/*`)));
    expect(tsconfig.include.filter((glob) => glob.startsWith('apps/'))).toEqual([]);
    expect(tsconfig.include.filter((glob) => glob.endsWith('/frontend/**/*'))).toEqual(
      globbed.map((app) => `${app}/frontend/**/*`),
    );
  });
});

describe('app catalogue guards', () => {
  it('keeps every <app>/frontend/locale/<lang>.json under its own <app>, so merging apps never collides', () => {
    const catalogues = rootAppsWithFrontend()
      .filter((app) => existsSync(join(SAAS_DIR, app, 'frontend', 'locale')))
      .flatMap((app) => {
        const dir = join(SAAS_DIR, app, 'frontend', 'locale');
        return readdirSync(dir)
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app, file: join(dir, name) }));
      });
    expect(catalogues.length).toBeGreaterThan(0);
    for (const { app, file } of catalogues) {
      expect(Object.keys(JSON.parse(readFileSync(file, 'utf8')) as object), file).toEqual([app]);
    }
  });
});
