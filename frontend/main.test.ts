// The SaaS SPA entry (mirror of hub-next's): app routes → shell, live client from spa-config,
// session from the `session-me` JSON Django embeds (or GET /api/me), mount only once the router is
// ready. The SaaS has a login of its own: the auth gate sends to the SPA route `/login`.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({ client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } } }));

vi.mock('@erplora/ui/shell', () => ({ createShell: vi.fn() }));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => sdk.client),
  provideLiveClient: vi.fn(),
}));

import { createShell } from '@erplora/ui/shell';
import { ApiError, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';

import { OPERATION_ROUTES } from './generated/operation-routes';

type Main = typeof import('./main');

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..');

/** The apps of saas-next with a frontend: root directories next to `base/` holding a `frontend/` (no `apps/`, PLAN §20.2). */
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
const ME = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'es' };
const page = { template: '<div />' };

function fakeShell(isReady: () => Promise<void> = () => Promise.resolve()) {
  const app = { mount: vi.fn() };
  const router = { isReady: vi.fn(isReady) };
  vi.mocked(createShell).mockResolvedValue({ app, router } as never);
  return { app, router };
}

function shellOptions() {
  return vi.mocked(createShell).mock.calls.at(-1)![0];
}

function renderShellHtml(session: object | null = ME) {
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">{"csrfCookieName": "csrftoken", "lang": "es", "googleEnabled": true}</script>
    ${session ? `<script id="session-me" type="application/json">${JSON.stringify(session)}</script>` : ''}
    <div id="app"></div>`;
}

let main: Main;
let importBoot: ReturnType<typeof shellOptions>;

beforeAll(async () => {
  sdk.client.api.call = vi.fn();
  renderShellHtml();
  fakeShell();
  main = await import('./main');
  importBoot = shellOptions();
});

beforeEach(() => {
  vi.clearAllMocks();
  sdk.client.api.call = vi.fn();
  renderShellHtml();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  it('boots on import with the routes Vite globs from <app>/frontend/routes.ts (the login page among them)', () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    expect(routes.find((r) => r.path === '/login')?.meta?.auth).toBe(false);
  });

  it('collects the routes of every app, in path order, behind a session by default', async () => {
    fakeShell();
    await main.boot({
      '../zeta/frontend/routes.ts': { default: [{ path: '/zeta', component: page }] },
      '../alpha/frontend/routes.ts': {
        default: [
          { path: '/alpha', component: page },
          { path: '/alpha/public', component: page, meta: { auth: false } },
        ],
      },
    });
    const routes = shellOptions().routes as RouteRecordRaw[];
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/alpha', true],
      ['/alpha/public', false],
      ['/zeta', true],
    ]);
  });

  it('feeds the shell every app catalogue, merged per language from <app>/frontend/locale/<lang>.json', async () => {
    fakeShell();
    await main.boot(
      {},
      {
        '../accounts/frontend/locale/en.json': { accounts: { title: 'Sign In' } },
        '../accounts/frontend/locale/es.json': { accounts: { title: 'Iniciar Sesión' } },
        '../zeta/frontend/locale/en.json': { zeta: { title: 'Zeta' } },
      },
    );
    expect(shellOptions().messages).toEqual({
      en: { accounts: { title: 'Sign In' }, zeta: { title: 'Zeta' } },
      es: { accounts: { title: 'Iniciar Sesión' } },
    });
  });

  it('on import, globs the real app catalogues (the login page would show raw keys otherwise)', () => {
    const messages = importBoot.messages as Record<string, { accounts: { login: { title: string } } }>;
    expect([messages.en.accounts.login.title, messages.es.accounts.login.title]).toEqual(['Sign In', 'Iniciar Sesión']);
  });

  it('builds the live client from spa-config with the generated op → route map and provides it to the app', async () => {
    const { app } = fakeShell();
    await main.boot({});
    expect(createLiveClient).toHaveBeenCalledWith(
      expect.objectContaining({ csrfCookieName: 'csrftoken', lang: 'es', googleEnabled: true }),
      { routes: OPERATION_ROUTES },
    );
    expect(provideLiveClient).toHaveBeenCalledWith(sdk.client, app);
  });

  it('feeds the shell the session Django embedded, live at once and without a request', async () => {
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    expect(session.value).toEqual(ME);
    expect(status.value).toBe('live');
    expect(sdk.client.api.call).not.toHaveBeenCalled();
  });

  it("sends a visitor without a session to the SaaS's own login page, /login of this SPA", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().loginPath).toBe('/login');
  });

  it('without an embedded session, asks GET /api/me (base.session.me) and goes live with its answer', async () => {
    renderShellHtml(null);
    let answer!: (me: object) => void;
    vi.mocked(sdk.client.api.call).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    fakeShell();
    await main.boot({});
    expect(sdk.client.api.call).toHaveBeenCalledExactlyOnceWith('base.session.me', {});
    const { session, status } = shellOptions();
    expect([session.value, status.value]).toEqual([undefined, 'loading']);
    answer(ME);
    await vi.waitFor(() => expect(status.value).toBe('live'));
    expect(session.value).toEqual(ME);
  });

  it('marks the session as errored when /api/me fails, so the gate stops waiting and sends to the login', async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    await vi.waitFor(() => expect(status.value).toBe('error'));
    expect(session.value).toBeUndefined();
    expect(logged).toHaveBeenCalledWith('saas: base.session.me failed', expect.any(ApiError));
    logged.mockRestore();
  });

  it('mounts #app only after the router is ready, and after providing the live client', async () => {
    let ready!: () => void;
    const { app } = fakeShell(() => new Promise<void>((resolve) => (ready = resolve)));
    const booted = main.boot({});
    await vi.waitFor(() => expect(createShell).toHaveBeenCalled());
    await Promise.resolve();
    expect(app.mount).not.toHaveBeenCalled();
    ready();
    await booted;
    expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app');
    expect(vi.mocked(provideLiveClient).mock.invocationCallOrder[0]).toBeLessThan(app.mount.mock.invocationCallOrder[0]);
  });

  it('does not mount when the auth gate cancels the first navigation (the page is going to the login)', async () => {
    const gate = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] });
    gate.beforeEach(() => false);
    const cancelled = (await gate.push('/')) as NavigationFailure;
    const { app } = fakeShell(() => Promise.reject(cancelled));
    await expect(main.boot({})).resolves.toBeUndefined();
    expect(app.mount).not.toHaveBeenCalled();
  });

  it('lets any other boot failure surface', async () => {
    fakeShell(() => Promise.reject(new Error('boom')));
    await expect(main.boot({})).rejects.toThrow('boom');
  });
});

describe('import order guards (hub#1060)', () => {
  it('imports the shell before anything that loads @ionic/vue (the SDK, the generated routes)', () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const runtimeImports = [...source.matchAll(/^import\s+(?!type\b)[^;]*?from\s+'([^']+)';/gms)].map((m) => m[1]);
    expect(runtimeImports[0]).toBe('@erplora/ui/shell');
  });

  it("loads the SaaS's typeface after the shell's theme, so it wins the cascade (fonts.css)", () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const fonts = source.indexOf("import './fonts.css';");
    expect(fonts).toBeGreaterThan(-1);
    expect(fonts).toBeGreaterThan(source.indexOf("from '@erplora/ui/shell';"));
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

describe('root app guards (saas-next has no apps/: its apps live next to base/, PLAN §20.2)', () => {
  it('globs the routes and the catalogues of the same apps', () => {
    const globs = globbedApps();
    expect(globs.map(([rest]) => rest)).toEqual(['routes.ts', 'locale/*.json']);
    expect(globs[1][1]).toEqual(globs[0][1]);
  });

  it('globs every root app with a frontend/: one left out would lose its pages and texts silently', () => {
    const apps = rootAppsWithFrontend();
    expect(apps).toContain('accounts');
    const [[, globbed]] = globbedApps();
    expect(apps.filter((app) => !globbed.includes(app))).toEqual([]);
  });

  it('typechecks the frontend of every app main.ts globs (tsconfig.json)', () => {
    const tsconfig = JSON.parse(readFileSync(join(SAAS_DIR, 'tsconfig.json'), 'utf8')) as { include: string[] };
    const [[, globbed]] = globbedApps();
    expect(tsconfig.include).toEqual(expect.arrayContaining(globbed.map((app) => `${app}/frontend/**/*`)));
    expect(tsconfig.include.filter((glob) => glob.startsWith('apps/'))).toEqual([]);
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
