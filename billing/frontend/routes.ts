// Routes → pages of the billing app; the menu comes from the server (`base/navigation.py`). Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own chunk
// (`import()`). The Store says itself that it is web only, with its own text: the shell's `meta.webOnly` would mount
// the generic NotInAppPage, which cannot say «The store is not in the app».
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
    // Billing: what the account pays ERPlora. Not selling, so on every surface; the
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
    // One invoice: its lines, totals and recipient; Back returns to Invoices. Not selling either.
    path: '/dashboard/billing/invoices/:id',
    component: () => import('./pages/InvoicePage.vue'),
    props: true,
    meta: { auth: true },
  },
];

export default routes;
