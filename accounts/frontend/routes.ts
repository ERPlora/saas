// Routes → pages of the accounts app, and nothing else. Types only: `main.ts` globs this file eagerly
// and Vite hoists that glob above the shell's boot hooks, so a runtime import here would load
// `@ionic/vue` too early. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    // The sign-in lives in the launcher, `/launch` (Ioan, 2026-10-15), where the shell's auth gate sends a
    // visitor without a session (`main.ts`): this old address (links, bookmarks) only leads there, keeping
    // `next` and the notice. Django answers a full load of it the same way (`config/urls.py`).
    path: '/login',
    redirect: (to) => ({ path: '/launch', query: to.query }),
    meta: { auth: false },
  },
  {
    // Every refused sign-in or jump to a hub (`?code=`), from Django's redirects.
    path: '/login/error',
    component: () => import('./pages/LoginErrorPage.vue'),
    meta: { auth: false },
  },
  {
    // The code mailed at every password sign-in, or to a new account (or a login whose address is not
    // verified): the login waits in the session, there is none yet.
    path: '/verify-email',
    component: () => import('./pages/VerifyEmailPage.vue'),
    meta: { auth: false },
  },
  {
    // «Forgot your password?»: allauth mails the link of the next route.
    path: '/password/reset',
    component: () => import('./pages/PasswordResetPage.vue'),
    meta: { auth: false },
  },
  {
    // The mailed link (allauth's `HEADLESS_FRONTEND_URLS`); `key` itself is reserved by Vue as a prop.
    path: '/password/reset/key/:resetKey',
    component: () => import('./pages/PasswordResetKeyPage.vue'),
    props: true,
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
  {
    // «Report a problem» of the user menu (ACCOUNTS-F38): the account, its businesses and the browser go with it.
    path: '/report-a-problem',
    component: () => import('./pages/ReportProblemPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
