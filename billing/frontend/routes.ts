// Routes → pages of the billing app (the Store and Billing), and nothing else: the menu
// comes from the server (`base/navigation.py`). Types only: `main.ts` globs this file eagerly and Vite
// hoists that glob above the shell's boot hooks. Each page is its own chunk (`import()`).
// The Store sells, so it is the web's only (PLAN-SAAS §3.6 point 6): StorePage says so itself inside the
// apps, with the Store's own text and live with the surface; the shell's `meta.webOnly` would mount its
// generic NotInAppPage, which cannot say «The store is not in the app».
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/dashboard/store',
    redirect: (to) => ({ path: '/dashboard/store/plans', query: to.query }),
    meta: { auth: true },
  },
  {
    // One address per section (the footer tabbar follows it); `?business=` is the business it sells to.
    path: '/dashboard/store/:tab(plans|modules)',
    component: () => import('./pages/StorePage.vue'),
    props: true,
    meta: { auth: true },
  },
  {
    // Billing (lot L3-C; round 17 §2.7): what the account pays ERPlora. Not selling, so on every surface; the
    // menu and Stripe's Customer Portal come back to `/dashboard/billing`, which opens Invoices keeping the query.
    path: '/dashboard/billing',
    redirect: (to) => ({ path: '/dashboard/billing/invoices', query: to.query }),
    meta: { auth: true },
  },
  {
    path: '/dashboard/billing/:tab(invoices|subscriptions|payment)',
    component: () => import('./pages/BillingPage.vue'),
    props: true,
    meta: { auth: true },
  },
  {
    // One invoice (BILLING-G05): its lines, totals and recipient; Back returns to Invoices. Not selling either.
    path: '/dashboard/billing/invoices/:id',
    component: () => import('./pages/InvoicePage.vue'),
    props: true,
    meta: { auth: true },
  },
];

export default routes;
