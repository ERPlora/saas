// Routes → pages of the hubs app (the businesses panel), and nothing else: the menu comes from the
// server (`base.session.me`). Types only: `main.ts` globs this file eagerly and Vite hoists that glob
// above the shell's boot hooks, so a runtime import here would load `@ionic/vue` too early. Each page
// is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    // The entry of erplora.com and of the apps (round 17 §2.2): signed out it asks to sign in and
    // comes back, so it is open to visitors; its own centred card, never the shell's menu.
    path: '/launch',
    component: () => import('./pages/LaunchPage.vue'),
    meta: { auth: false, chrome: false },
  },
  {
    // The panel's home: the account's businesses (where the web sign-in lands).
    path: '/businesses',
    component: () => import('./pages/BusinessListPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/businesses/:id',
    redirect: (to) => `/businesses/${String(to.params.id)}/summary`,
    meta: { auth: true },
  },
  {
    // A business's page, one address per section: the footer tabbar follows the route.
    path: '/businesses/:id/:tab(summary|members|modules|settings)',
    component: () => import('./pages/BusinessPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  {
    // Every invitation waiting for an answer (the invitation email links here).
    path: '/invitation',
    component: () => import('./pages/InvitationPage.vue'),
    meta: { auth: true, chrome: false },
  },
  {
    // One invitation first (the banners of the launcher and Businesses link here).
    path: '/invitations/:id',
    component: () => import('./pages/InvitationPage.vue'),
    props: true,
    meta: { auth: true, chrome: false },
  },
];

export default routes;
