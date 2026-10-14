// Entry of the SaaS SPA (`LIVE["spa"]["entry"]`), the same as hub-next's: app routes and catalogues →
// shell, live client, session (`base.session.me`, a plain query: embedded by `base/spa.py`, else
// `GET /api/me`), mount. The SaaS has its own login: the auth gate sends to the SPA route `/login`.
// 🔴 Import order (hub#1060): the shell barrel goes first so its boot hooks wrap `customElements.define`
// before anything loads `@ionic/vue` (the SDK does). Vite hoists eager globs above everything, so an
// app's `routes.ts` only imports types; its pages load with `() => import(…)`. Guards: main.test.ts.
// The apps live at the project root, next to `base/` (no `apps/`, PLAN §20.2); a glob takes literal
// strings only, so every app with a `frontend/` is named in both globs (guard: main.test.ts).
// Round 17 (PLAN-SAAS §3.6): the menu comes from the server (`base/navigation.py`); the entry adds
// the user menu (Account, Help, Sign out) and the surface the server keeps in the session.
import {
  createShell,
  type CreateShellOptions,
  type SessionMe,
  type SessionStatus,
  type ShellUserMenuItem,
  type Surface,
} from '@erplora/ui/shell';
import {
  type AllauthClient,
  createAllauthClient,
  createLiveClient,
  type LiveClient,
  provideLiveClient,
  readSpaConfig,
} from '@erplora/ui/sdk';
// After the shell's theme, so the SaaS's typeface (IBM Plex) wins the cascade.
import './fonts.css';
import { ref } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { OPERATION_ROUTES } from './generated/operation-routes';
import en from './locale/en.json';
import es from './locale/es.json';

/** Where the auth gate sends a visitor without a session (it appends `next=`). */
const LOGIN_PATH = '/login';
/** «Help» of the user menu. */
const HELP_PATH = '/help';
/** The SaaS's entries of the user menu, before Help and Sign out (mockups README §3). */
const USER_MENU_ITEMS: ShellUserMenuItem[] = [
  { id: 'account', labelKey: 'saas.userMenu.account', icon: 'ion:person-outline', to: '/account' },
];
/** The entry's own texts (the user menu), merged with the apps' catalogues under `saas`. */
const ENTRY_CATALOGUES = { 'frontend/locale/en.json': en, 'frontend/locale/es.json': es };

/** An app's `frontend/routes.ts` default-exports its routes → pages, and nothing else. */
export type AppRoutes = { default: RouteRecordRaw[] };

/** Every app's routes, in path order; a page needs a session unless its route says `auth: false`. */
export function appRoutes(routeFiles: Record<string, AppRoutes>): RouteRecordRaw[] {
  return Object.keys(routeFiles)
    .sort()
    .flatMap((file) => routeFiles[file].default)
    .map((route) => ({ ...route, meta: { auth: true, ...route.meta } }) as RouteRecordRaw);
}

/** An app's `frontend/locale/<lang>.json`, all under the app id (guard: main.test.ts). */
export type AppCatalogue = Record<string, unknown>;

/** Every app catalogue, by the language in its file name; distinct app ids, so a spread never collides. */
export function appMessages(catalogues: Record<string, AppCatalogue>): CreateShellOptions['messages'] {
  const messages: Record<string, AppCatalogue> = {};
  for (const [file, catalogue] of Object.entries(catalogues)) {
    const language = file.slice(file.lastIndexOf('/') + 1, -'.json'.length);
    messages[language] = { ...messages[language], ...catalogue };
  }
  return messages;
}

/** A failed `/api/me` ends in `error`, so the auth gate stops waiting and sends to the login. */
function loadSession(client: LiveClient, doc: Document) {
  const text = doc.getElementById('session-me')?.textContent;
  const me = ref<SessionMe | undefined>(text ? (JSON.parse(text) as SessionMe) : undefined);
  const status = ref<SessionStatus>(me.value ? 'live' : 'loading');
  if (!me.value) {
    client.api.call('base.session.me', {}).then(
      (answer) => {
        me.value = answer;
        status.value = 'live';
      },
      (error: unknown) => {
        console.error('saas: base.session.me failed', error);
        status.value = 'error';
      },
    );
  }
  return { session: me, status };
}

/**
 * The surface the server keeps in the session (`spa-config.surface`, `base/surface.py`): only the
 * account one. `readSpaConfig` keeps the SDK's keys only, so it is read here; without it the shell
 * detects the surface itself (the Tauri bridge, the app's user agent, `?surface=`).
 */
function serverSurface(doc: Document): Surface | undefined {
  const raw = JSON.parse(doc.getElementById('spa-config')?.textContent ?? '{}') as { surface?: unknown };
  return raw.surface === 'account' ? 'account' : undefined;
}

/**
 * «Sign out»: allauth.headless ends the session (`DELETE …/auth/session`), then the login, as a full
 * load so the next page embeds an empty session. A failure rejects: the shell shows its toast.
 */
async function signOut(auth: AllauthClient): Promise<void> {
  const state = await auth.logout();
  if (state.authenticated) throw new Error('saas: still signed in after signing out');
  location.assign(LOGIN_PATH);
}

/** Boots the shell and mounts it on `#app`; no mount when the gate sent the page to the login. */
export async function boot(
  routeFiles: Record<string, AppRoutes>,
  catalogues: Record<string, AppCatalogue> = {},
  doc: Document = document,
): Promise<void> {
  const config = readSpaConfig(doc);
  const client = createLiveClient(config, { routes: OPERATION_ROUTES });
  const auth = createAllauthClient(config);
  const session = loadSession(client, doc);
  const { app, router } = await createShell({
    ...session,
    routes: appRoutes(routeFiles),
    messages: appMessages({ ...ENTRY_CATALOGUES, ...catalogues }),
    loginPath: LOGIN_PATH,
    surface: serverSurface(doc),
    userMenu: { items: USER_MENU_ITEMS, helpPath: HELP_PATH, logout: () => signOut(auth) },
  });
  provideLiveClient(client, app);
  try {
    await router.isReady();
  } catch (failure) {
    if (isNavigationFailure(failure)) return;
    throw failure;
  }
  app.mount('#app');
}

void boot(
  import.meta.glob<AppRoutes>('../{accounts,hubs,billing}/frontend/routes.ts', { eager: true }),
  import.meta.glob<AppCatalogue>('../{accounts,hubs,billing}/frontend/locale/*.json', {
    eager: true,
    import: 'default',
  }),
);
