// Entry of the SaaS SPA (`LIVE["spa"]["entry"]`), the same as hub-next's: app routes and catalogues →
// shell, live client, session (`base.session.me`, a plain query: embedded by `base/spa.py`, else
// `GET /api/me`), mount. The SaaS has its own login: the auth gate sends to the launcher, `/launch`,
// where the sign-in form is.
// 🔴 Import order (hub#1060): the shell barrel goes first so its boot hooks wrap `customElements.define`
// before anything loads `@ionic/vue` (the SDK does). Vite hoists eager globs above everything, so an
// app's `routes.ts` only imports types; its pages load with `() => import(…)`. Guards: main.test.ts.
// The apps live at the project root, next to `base/` (no `apps/`, PLAN §20.2); a glob takes literal
// strings only, so every app with a `frontend/` is named in both globs (guard: main.test.ts).
// Round 17 (PLAN-SAAS §3.6): the menu comes from the server (`base/navigation.py`); the entry adds
// the user menu (Account, Help, Sign out) and the surface the server keeps in the session. What the
// account chose (Account → Preferences, in `base.session.me`) is painted before the first paint: its
// theme mode and its own language; the user menu's theme is kept in the account.
import {
  createShell,
  type CreateShellOptions,
  type SessionStatus,
  setThemeMode,
  setThemePersister,
  shellLocale,
  type ShellUserMenuItem,
  type Surface,
  toastError,
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
// The panel's lists fill their page between the topbar and the tabbar (the `.panel-fill` height chain).
import './panel-fill.css';
// The panel's chrome: «Skip to content», touch targets of 44 px, Back without ☰ in a detail page (audit 2026-10-14).
import './panel-chrome.css';
import { type Ref, ref } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { LAUNCHER } from '../accounts/frontend/paths';
import { OPERATION_ROUTES } from './generated/operation-routes';
import en from './locale/en.json';
import es from './locale/es.json';
import type { SessionMeOut } from './sdk-types';
import { installSkipLink } from './skip-link';

/** «Help» of the user menu. */
const HELP_PATH = '/help';
/** The panel's home (the shell's Home: the menu's brand, «not found», «not in the app»): `/` is the public web,
 *  a Django page the SPA does not have (audit 2 R-18). */
const HOME_PATH = '/businesses';
/** The SaaS's entries of the user menu, before Help and Sign out (mockups README §3). */
const USER_MENU_ITEMS: ShellUserMenuItem[] = [
  { id: 'account', labelKey: 'saas.userMenu.account', icon: 'ion:person-outline', to: '/account' },
];
/**
 * The only origin whose script URLs the page's `default` Trusted Types policy admits: Stripe.js's loader
 * sets its chunks' `src` as plain strings (the Store's Embedded Checkout, `billing/frontend/stripe-js.ts`).
 * The CSP's `script-src` still decides page by page (the account surface names no Stripe, `base/csp.py`).
 */
const TRUSTED_SCRIPT_ORIGINS = ['https://js.stripe.com'] as const;
/** The entry's own texts (the user menu), merged with the apps' catalogues under `saas`; and, at the top, the shell's
 *  texts the panel says otherwise (`notFound`: the panel, not a hub; audit 2 R-18). */
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

/**
 * What the account chose, painted before the shell's first paint: its theme mode (an anonymous visitor
 * keeps this device's) and its own language, which the shell's i18n and `<html lang>` follow
 * (`createShell` watches `session.language`). On the panel the server already answers in it
 * (`base.language`); when the session still speaks another one, the account's wins.
 */
function applyAccount(me: SessionMeOut): SessionMeOut {
  if (me.preferences) setThemeMode(me.preferences.theme_mode);
  const own = me.account_language;
  return own && shellLocale(own) !== shellLocale(me.language) ? { ...me, language: own } : me;
}

/** A failed `/api/me` ends in `error`, so the auth gate stops waiting and sends to the login. */
function loadSession(client: LiveClient, doc: Document) {
  const text = doc.getElementById('session-me')?.textContent;
  const me = ref<SessionMeOut | undefined>(text ? applyAccount(JSON.parse(text) as SessionMeOut) : undefined);
  const status = ref<SessionStatus>(me.value ? 'live' : 'loading');
  if (!me.value) {
    client.api.call('base.session.me', {}).then(
      (answer) => {
        me.value = applyAccount(answer);
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
 * The user menu's theme (light, dark, system) is the account's: the shell paints it at once
 * (`chooseThemeMode`) and this keeps it in the account (`accounts.preferences.update`). Without an
 * account there is nowhere to keep it. A failed save leaves the mode painted and says so, in the
 * language of the page (`createShell` keeps `<html lang>` in step with the session's).
 */
function keepThemeInAccount(client: LiveClient, session: Ref<SessionMeOut | undefined>, doc: Document): void {
  setThemePersister((mode) => {
    if (!session.value?.user) return;
    client.api.call('accounts.preferences.update', { theme_mode: mode }).catch((error: unknown) => {
      console.error('saas: accounts.preferences.update failed', error);
      const texts = { en, es }[shellLocale(doc.documentElement.lang)];
      void toastError(texts.saas.userMenu.themeNotSaved);
    });
  });
}

/**
 * «Sign out»: allauth.headless ends the session (`DELETE …/auth/session`), then the login, as a full
 * load so the next page embeds an empty session. A failure rejects: the shell shows its toast.
 */
async function signOut(auth: AllauthClient): Promise<void> {
  const state = await auth.logout();
  if (state.authenticated) throw new Error('saas: still signed in after signing out');
  location.assign(LAUNCHER);
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
  keepThemeInAccount(client, session.session, doc);
  const { app, router } = await createShell({
    ...session,
    routes: appRoutes(routeFiles),
    messages: appMessages({ ...ENTRY_CATALOGUES, ...catalogues }),
    loginPath: LAUNCHER,
    homePath: HOME_PATH,
    surface: serverSurface(doc),
    userMenu: { items: USER_MENU_ITEMS, helpPath: HELP_PATH, logout: () => signOut(auth) },
    trustedScriptOrigins: TRUSTED_SCRIPT_ORIGINS,
    // AA contrast (audit 2 §5.1, option A): the primary solid at 4.87:1 with white, and dark text on the
    // dark theme's (`data-ep-contrast="aa"`, packages/ui theme/variables.css).
    contrast: 'aa',
  });
  provideLiveClient(client, app);
  try {
    await router.isReady();
  } catch (failure) {
    if (isNavigationFailure(failure)) return;
    throw failure;
  }
  installSkipLink(doc, { en: en.saas.skipLink, es: es.saas.skipLink }, { en: en.saas.skipNav, es: es.saas.skipNav });
  app.mount('#app');
}

void boot(
  import.meta.glob<AppRoutes>('../{accounts,hubs,billing}/frontend/routes.ts', { eager: true }),
  import.meta.glob<AppCatalogue>('../{accounts,hubs,billing}/frontend/locale/*.json', {
    eager: true,
    import: 'default',
  }),
);
