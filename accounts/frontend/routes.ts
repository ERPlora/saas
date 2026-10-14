// Routes → pages of the accounts app, and nothing else. Types only: `main.ts` globs this file eagerly
// and Vite hoists that glob above the shell's boot hooks, so a runtime import here would load
// `@ionic/vue` too early. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    // Where the shell's auth gate sends a visitor without a session (`main.ts`).
    path: '/login',
    component: () => import('./pages/LoginPage.vue'),
    meta: { auth: false },
  },
  {
    // Every refused sign-in or jump to a hub (`?code=`), from Django's redirects.
    path: '/login/error',
    component: () => import('./pages/LoginErrorPage.vue'),
    meta: { auth: false },
  },
  {
    // The second step of a sign-in with 2FA: the login waits in the session, there is none yet.
    path: '/2fa/authenticate',
    component: () => import('./pages/TwoFactorAuthenticatePage.vue'),
    meta: { auth: false },
  },
  {
    // The 2FA settings (authenticator app, recovery codes), in the auth frame as the launcher.
    path: '/2fa',
    component: () => import('./pages/TwoFactorSettingsPage.vue'),
    meta: { auth: true, chrome: false },
  },
  {
    // «Confirm it's you», when allauth asks for a recent login before a security change.
    path: '/reauthenticate',
    component: () => import('./pages/ReauthenticatePage.vue'),
    meta: { auth: true, chrome: false },
  },
];

export default routes;
