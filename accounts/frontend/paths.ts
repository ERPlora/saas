// Paths of the panel named once, for every page and component that sends a visitor there. Pure values: the
// `routes.ts` files import types only (main.test.ts), so they spell the path themselves (guard: paths.test.ts).

/** The launcher (round 19, PLAN-SAAS §3.7): the sign-in and sign-up form, and the businesses of a session. */
export const LAUNCHER = '/launch';

/** The panel: every page shown with its menu lives under it, as the old product's `apps/dashboard/`
 *  (FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX; the server's `base/navigation.py` names the same). The launcher, the
 *  sign-in's pages and the invitations stay at the root. */
export const PANEL = '/dashboard';
/** Businesses, the panel's home (HUBS-F10): where «Go to the panel» lands. */
export const BUSINESSES = `${PANEL}/businesses`;
/** The Store (`/plans`, `/modules`; `?business=` is the business it sells to). */
export const STORE = `${PANEL}/store`;
/** Billing (`/invoices`, `/subscriptions`, `/payment`; `/invoices/:id` is one invoice). */
export const BILLING = `${PANEL}/billing`;
/** Account (`/profile`, `/security`, `/preferences`, `/api-keys`). */
export const ACCOUNT = `${PANEL}/account`;
/** «Report a problem» of the user menu (ACCOUNTS-F38). */
export const REPORT_PROBLEM = `${PANEL}/report-a-problem`;
