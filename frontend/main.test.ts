// The SaaS SPA entry (mirror of hub-next's): app routes → shell, live client from spa-config,
// session from the `session-me` JSON Django embeds (or GET /api/me), mount only once the router is
// ready. The SaaS has a login of its own: the auth gate sends to the SPA route `/launch`. Round 17
// (PLAN-SAAS §3.6): the user menu (Account, Help, Sign out) and the surface the server keeps; what the
// account chose (theme mode, language) painted at boot, and the user menu's theme kept in the account.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({
  client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } },
  auth: { logout: (() => undefined) as (...args: unknown[]) => unknown },
}));

// The real theme (and i18n helpers) of the shell; only its boot and its toast are stand-ins.
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createShell: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => sdk.client),
  createAllauthClient: vi.fn(() => sdk.auth),
  provideLiveClient: vi.fn(),
}));

import { chooseThemeMode, createShell, setThemeMode, setThemePersister, themeMode, toastError } from '@erplora/ui/shell';
import { ApiError, createAllauthClient, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';

import { OPERATION_ROUTES } from './generated/operation-routes';
import entryEn from './locale/en.json';
import entryEs from './locale/es.json';

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
const ME = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [],
  menu: [],
  apps: [],
  language: 'es',
  preferences: { theme_mode: 'system' },
  account_language: 'es',
};
/** `base.session.me` without an account: no preferences, no language of its own. */
const ANONYMOUS = { ...ME, user: null, preferences: null, account_language: null };
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

function renderShellHtml(session: object | null = ME, config: object = {}) {
  const spaConfig = JSON.stringify({ csrfCookieName: 'csrftoken', lang: 'es', googleEnabled: true, ...config });
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">${spaConfig}</script>
    ${session ? `<script id="session-me" type="application/json">${JSON.stringify(session)}</script>` : ''}
    <div id="app"></div>`;
}

let main: Main;
let importBoot: ReturnType<typeof shellOptions>;

beforeAll(async () => {
  sdk.client.api.call = vi.fn();
  sdk.auth.logout = vi.fn();
  renderShellHtml();
  fakeShell();
  main = await import('./main');
  importBoot = shellOptions();
});

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  setThemePersister(undefined);
  setThemeMode('system');
  document.documentElement.lang = '';
  sdk.client.api.call = vi.fn();
  sdk.auth.logout = vi.fn();
  assign = vi.fn();
  vi.stubGlobal('location', { ...window.location, assign });
  renderShellHtml();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  it('boots on import with the routes Vite globs from <app>/frontend/routes.ts (the launcher, with the sign-in, among them)', () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    expect(routes.find((r) => r.path === '/launch')?.meta?.auth).toBe(false);
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
    // Plus the entry's own catalogue (frontend/locale), under `saas`.
    expect(shellOptions().messages).toEqual({
      en: { ...entryEn, accounts: { title: 'Sign In' }, zeta: { title: 'Zeta' } },
      es: { ...entryEs, accounts: { title: 'Iniciar Sesión' } },
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

  it("sends a visitor without a session to the SaaS's own sign-in, the launcher of this SPA", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().loginPath).toBe('/launch');
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

describe('the panel (round 17, PLAN-SAAS §3.6)', () => {
  /** The user menu's «Sign out», as the shell's App.vue calls it. */
  async function signOut(): Promise<void> {
    await shellOptions().userMenu!.logout!();
  }

  it('hands the shell the user menu: Account, Help at /help and Sign out', async () => {
    fakeShell();
    await main.boot({});
    const { userMenu } = shellOptions();
    expect(userMenu?.items).toEqual([
      { id: 'account', labelKey: 'saas.userMenu.account', icon: 'ion:person-outline', to: '/account' },
    ]);
    expect(userMenu?.helpPath).toBe('/help');
    expect(userMenu?.logout).toBeTypeOf('function');
  });

  it('signs out through allauth.headless (DELETE of the session), then loads the launcher, the sign-in', async () => {
    vi.mocked(sdk.auth.logout).mockResolvedValue({ authenticated: false, flows: [] });
    fakeShell();
    await main.boot({});
    expect(createAllauthClient).toHaveBeenCalledWith(expect.objectContaining({ csrfCookieName: 'csrftoken' }));
    await signOut();
    expect(sdk.auth.logout).toHaveBeenCalledOnce();
    // A full load: the next page embeds an empty session (and the server forgot the surface).
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('a sign out that fails rejects, so the shell shows its toast, and the page stays', async () => {
    vi.mocked(sdk.auth.logout).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    fakeShell();
    await main.boot({});
    await expect(signOut()).rejects.toThrow('Network error');
    expect(assign).not.toHaveBeenCalled();
  });

  it('a sign out the server did not honour (still signed in) rejects too', async () => {
    vi.mocked(sdk.auth.logout).mockResolvedValue({ authenticated: true, user: { id: 1, email: 'ana@example.com' } });
    fakeShell();
    await main.boot({});
    await expect(signOut()).rejects.toThrow('still signed in');
    expect(assign).not.toHaveBeenCalled();
  });

  it('trusts the script URLs of Stripe.js only (its loader sets its chunks as strings): one origin, exact', async () => {
    fakeShell();
    await main.boot({});
    // The `default` Trusted Types policy admits these origins' script URLs and no other; the CSP's
    // `script-src` still decides page by page (the account surface's names no Stripe).
    expect(shellOptions().trustedScriptOrigins).toEqual(['https://js.stripe.com']);
  });

  it('passes the shell the account surface the server keeps in the session (spa-config.surface)', async () => {
    renderShellHtml(ME, { surface: 'account' });
    fakeShell();
    await main.boot({});
    expect(shellOptions().surface).toBe('account');
  });

  it("otherwise leaves the surface to the shell's own detection (the Tauri bridge, the user agent, ?surface=)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().surface).toBeUndefined();
    renderShellHtml(ME, { surface: 'nonsense' });
    await main.boot({});
    expect(shellOptions().surface).toBeUndefined();
  });

  it("paints the AA contrast (audit 2 §5.1, option A: primary #0e78ad with white, dark text on the dark one) and has no Home of the shell (the SaaS's landing is its own)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().contrast).toBe('aa');
    expect(shellOptions().home).toBeUndefined();
  });

  it("translates the user menu's Account in en and es (the entry's own catalogue, frontend/locale)", () => {
    const messages = importBoot.messages as Record<string, { saas: { userMenu: { account: string } } }>;
    expect([messages.en.saas.userMenu.account, messages.es.saas.userMenu.account]).toEqual(['Account', 'Cuenta']);
  });

  it("keeps the entry's catalogue under `saas`, with the same keys in en and es; anything else only overrides the shell's own texts", () => {
    const read = (lang: string) => JSON.parse(readFileSync(join(HERE, 'locale', `${lang}.json`), 'utf8')) as object;
    const shell = JSON.parse(readFileSync(join(SAAS_DIR, 'packages', 'ui', 'src', 'shell', 'locales', 'en.json'), 'utf8')) as object;
    const keys = (value: unknown, prefix = ''): string[] =>
      typeof value === 'object' && value !== null
        ? Object.entries(value).flatMap(([key, child]) => keys(child, `${prefix}${key}.`))
        : [prefix.slice(0, -1)];
    expect(Object.keys(read('en'))).toEqual(['saas', 'notFound', 'notInApp']);
    expect(keys(read('es'))).toEqual(keys(read('en')));
    const overrides = keys(read('en')).filter((key) => !key.startsWith('saas.'));
    expect(overrides.filter((key) => !keys(shell).includes(key))).toEqual([]);
  });

  it("the panel's home is Businesses: the menu's brand, «not found» and «not in the app» lead there, never to the public `/` the SPA does not have (audit 2 R-18)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().homePath).toBe('/businesses');
  });

  it('a page that does not exist speaks of the panel, not of a hub (audit 2 R-18)', () => {
    const messages = importBoot.messages as Record<string, { notFound: { body: string; action: string }; notInApp: { action: string } }>;
    expect(messages.en.notFound.body).toBe(
      'The address you opened is not part of the panel. It may be an old or mistyped link: your businesses, billing and account are in the menu.',
    );
    expect(messages.es.notFound.body).toBe(
      'La dirección que has abierto no forma parte del panel. Puede ser un enlace antiguo o mal copiado: tus negocios, la facturación y tu cuenta están en el menú.',
    );
    expect([messages.en.notFound.action, messages.es.notFound.action]).toEqual(['Go to my businesses', 'Ir a mis negocios']);
    expect([messages.en.notInApp.action, messages.es.notInApp.action]).toEqual(['Go to my businesses', 'Ir a mis negocios']);
    for (const language of ['en', 'es']) expect(JSON.stringify(messages[language].notFound)).not.toMatch(/\bhub\b/);
  });
});

describe("what the account chose, painted at boot (Account → Preferences; base.session.me)", () => {
  const dark = () => document.documentElement.classList.contains('ion-palette-dark');

  it('paints the theme mode of the embedded session before the shell boots (no flash of the system one)', async () => {
    renderShellHtml({ ...ME, preferences: { theme_mode: 'dark' } });
    let modeAtShell: string | undefined;
    const { app, router } = fakeShell();
    vi.mocked(createShell).mockImplementation(async () => {
      modeAtShell = themeMode.value;
      return { app, router } as never;
    });
    await main.boot({});
    expect(modeAtShell).toBe('dark');
    expect([themeMode.value, dark()]).toEqual(['dark', true]);
  });

  it('or the one /api/me answers, before the session goes live (the gate mounts after that)', async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...ME, preferences: { theme_mode: 'dark' } });
    fakeShell();
    await main.boot({});
    const { status } = shellOptions();
    let modeWhenLive: string | undefined;
    await vi.waitFor(() => {
      expect(status.value).toBe('live');
      modeWhenLive = themeMode.value;
    });
    expect(modeWhenLive).toBe('dark');
    expect(dark()).toBe(true);
  });

  it("leaves an anonymous visitor this device's mode (no account to read it from)", async () => {
    setThemeMode('dark');
    renderShellHtml(ANONYMOUS);
    fakeShell();
    await main.boot({});
    expect([themeMode.value, dark()]).toEqual(['dark', true]);
  });

  it("switches the SPA to the account's own language when the session speaks another one", async () => {
    renderShellHtml({ ...ME, language: 'en', account_language: 'es' });
    fakeShell();
    await main.boot({});
    // createShell follows `session.language` (i18n locale and <html lang>).
    expect(shellOptions().session.value?.language).toBe('es');
  });

  it("also when the account's language comes with /api/me", async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...ME, language: 'es', account_language: 'en' });
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    await vi.waitFor(() => expect(status.value).toBe('live'));
    expect(session.value?.language).toBe('en');
  });

  it("keeps the session's language without an account language of its own", async () => {
    renderShellHtml({ ...ANONYMOUS, language: 'es' });
    fakeShell();
    await main.boot({});
    expect(shellOptions().session.value?.language).toBe('es');
  });
});

describe("the user menu's theme, kept in the account (accounts.preferences.update)", () => {
  it('choosing a mode in the user menu saves it through the typed client, and it stays painted', async () => {
    vi.mocked(sdk.client.api.call).mockResolvedValue({ theme_mode: 'dark' });
    fakeShell();
    await main.boot({});
    chooseThemeMode('dark');
    expect(sdk.client.api.call).toHaveBeenCalledExactlyOnceWith('accounts.preferences.update', { theme_mode: 'dark' });
    await Promise.resolve();
    expect(themeMode.value).toBe('dark');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a save that fails keeps the mode on screen and says so with a toast, in the language of the page', async () => {
    const failure = new ApiError(0, 'network_error', 'Network error');
    vi.mocked(sdk.client.api.call).mockRejectedValue(failure);
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeShell();
    await main.boot({});
    document.documentElement.lang = 'es';
    chooseThemeMode('light');
    await vi.waitFor(() => expect(toastError).toHaveBeenCalledExactlyOnceWith(entryEs.saas.userMenu.themeNotSaved));
    expect(themeMode.value).toBe('light');
    expect(logged).toHaveBeenCalledWith('saas: accounts.preferences.update failed', failure);
    logged.mockRestore();
  });

  it('without an account there is nothing to save it in: the mode is painted, no call', async () => {
    renderShellHtml(ANONYMOUS);
    fakeShell();
    await main.boot({});
    chooseThemeMode('dark');
    expect(themeMode.value).toBe('dark');
    expect(sdk.client.api.call).not.toHaveBeenCalled();
  });

  it("says it in en and es (the entry's own catalogue)", () => {
    expect([entryEn.saas.userMenu.themeNotSaved, entryEs.saas.userMenu.themeNotSaved]).toEqual([
      "Couldn't save the appearance to your account.",
      'No se ha podido guardar la apariencia en tu cuenta.',
    ]);
  });
});

describe('import order guards (hub#1060)', () => {
  it('imports the shell before anything that loads @ionic/vue (the SDK, the generated routes)', () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const runtimeImports = [...source.matchAll(/^import\s+(?!type\b)[^;]*?from\s+'([^']+)';/gms)].map((m) => m[1]);
    expect(runtimeImports[0]).toBe('@erplora/ui/shell');
  });

  it('puts «Skip to content» first in the page, in the language of the page (audit 2026-10-14, R-11)', async () => {
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

  it("loads the panel's fill layout after the shell's theme and the typeface (panel-fill.css)", () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const fill = source.indexOf("import './panel-fill.css';");
    expect(fill).toBeGreaterThan(-1);
    expect(fill).toBeGreaterThan(source.indexOf("import './fonts.css';"));
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

  it('globs the apps with a frontend: accounts, hubs, billing and fiscal (round 16: no marketplace; apps and public have none)', () => {
    const [[, globbed]] = globbedApps();
    expect(globbed).toEqual(['accounts', 'hubs', 'billing', 'fiscal']);
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
