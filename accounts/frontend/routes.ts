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
  {
    // Account (round 17, PLAN-SAAS §3.6): the user menu and the side menu land on its Profile.
    path: '/account',
    redirect: '/account/profile',
    meta: { auth: true },
  },
  {
    // One address per section of Account: the footer tabbar follows the route.
    path: '/account/:tab(profile|security|preferences|api-keys)',
    component: () => import('./pages/AccountPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
];

export default routes;
