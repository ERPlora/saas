// The op → route map the SDK's API client uses. Written by hand for now (generated from
// `/api/openapi.json` later, as in hub-next). Sign-in is not here: allauth.headless is not an
// operation, the SDK reaches it through its own client (`createAllauthClient`).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from './operation-routes';

const HUBS_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hubs', 'api.py'), 'utf8');
const ACCOUNTS_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'accounts', 'api.py'), 'utf8');
const BILLING_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'billing', 'api.py'), 'utf8');
const APPS_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps', 'api.py'), 'utf8');
const FISCAL_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'fiscal', 'api.py'), 'utf8');

/** The operations of the Store (plan 2026-10-13 L2-D): billing/api.py, apps/api.py and the payer of hubs/api.py. */
const STORE_ROUTES = {
  'apps.app.list': { method: 'get', path: '/api/apps' },
  'apps.app.get': { method: 'get', path: '/api/apps/get' },
  'hubs.billing_profile.get': { method: 'get', path: '/api/hubs/billing-profile' },
  'hubs.billing_profile.update': { method: 'post', path: '/api/hubs/billing-profile' },
  'billing.store.catalog': { method: 'get', path: '/api/billing/store' },
  'billing.promo.check': { method: 'get', path: '/api/billing/promo-check' },
  'billing.checkout.start': { method: 'post', path: '/api/billing/checkout/start' },
  'billing.checkout.confirm': { method: 'post', path: '/api/billing/checkout/confirm' },
  'billing.plan.change': { method: 'post', path: '/api/billing/plan/change' },
  'billing.plan.cancel': { method: 'post', path: '/api/billing/plan/cancel' },
  'billing.plan.keep': { method: 'post', path: '/api/billing/plan/keep' },
  'billing.module.cancel': { method: 'post', path: '/api/billing/module/cancel' },
  'billing.module.keep': { method: 'post', path: '/api/billing/module/keep' },
};

/**
 * The operations of the Billing section (plan 2026-10-13 L3-C front): ERPlora's invoices (the list, one, its PDF,
 * the CSV of the list and «Pay»), the subscriptions and «Keep it with my card» of a business handed over to you
 * (HUBS-F28), the payment method with Stripe's Customer Portal and the VIES check of the billing details
 * (billing/api.py).
 */
const BILLING_ROUTES = {
  'billing.invoice.list': { method: 'get', path: '/api/billing/invoices' },
  'billing.invoice.get': { method: 'get', path: '/api/billing/invoices/detail' },
  'billing.invoice.pdf': { method: 'get', path: '/api/billing/invoices/pdf' },
  'billing.invoice.csv': { method: 'get', path: '/api/billing/invoices/csv' },
  'billing.invoice.pay': { method: 'post', path: '/api/billing/invoices/pay' },
  'billing.subscription.list': { method: 'get', path: '/api/billing/subscriptions' },
  'billing.plan.take_over': { method: 'post', path: '/api/billing/plan/take-over' },
  'billing.payment_method.get': { method: 'get', path: '/api/billing/payment-method' },
  'billing.portal.open': { method: 'post', path: '/api/billing/portal' },
  'billing.vat_check.run': { method: 'post', path: '/api/billing/vat-check' },
};

/** The usage of a business (hubs/api.py, plan 2026-10-13 L4-A): the last day measured and the days of a window. */
const USAGE_ROUTES = {
  'hubs.usage.get': { method: 'get', path: '/api/hubs/usage' },
  'hubs.usage.series': { method: 'get', path: '/api/hubs/usage/series' },
};

/** The signed authorisation of a business (fiscal/api.py, plan 2026-10-15): its state on the business's page. */
const FISCAL_ROUTES = {
  'fiscal.representation.status': { method: 'get', path: '/api/fiscal/representation' },
};

/** The operations of the Account page (accounts/api.py, plan 2026-10-13 L3-A): queries GET, commands POST. */
const ACCOUNT_PAGE_ROUTES = {
  'accounts.profile.get': { method: 'get', path: '/api/accounts/profile' },
  'accounts.profile.update': { method: 'post', path: '/api/accounts/profile' },
  'accounts.profile.delete': { method: 'post', path: '/api/accounts/profile/delete' },
  'accounts.data.export': { method: 'get', path: '/api/accounts/export' },
  'accounts.email.change': { method: 'post', path: '/api/accounts/email/change' },
  'accounts.email.verify': { method: 'post', path: '/api/accounts/email/verify' },
  'accounts.photo.upload': { method: 'post', path: '/api/accounts/photo' },
  'accounts.photo.remove': { method: 'post', path: '/api/accounts/photo/remove' },
  'accounts.preferences.get': { method: 'get', path: '/api/accounts/preferences' },
  'accounts.preferences.update': { method: 'post', path: '/api/accounts/preferences' },
  'accounts.session.list': { method: 'get', path: '/api/accounts/sessions' },
  'accounts.session.close': { method: 'post', path: '/api/accounts/sessions/close' },
  'accounts.session.close_others': { method: 'post', path: '/api/accounts/sessions/close_others' },
  'accounts.browser_trust.get': { method: 'get', path: '/api/accounts/browser-trust' },
  'accounts.browser_trust.revoke': { method: 'post', path: '/api/accounts/browser-trust/revoke' },
  'accounts.apikey.list': { method: 'get', path: '/api/accounts/api-keys' },
  'accounts.apikey.create': { method: 'post', path: '/api/accounts/api-keys' },
  'accounts.apikey.revoke': { method: 'post', path: '/api/accounts/api-keys/revoke' },
  'accounts.support.report': { method: 'post', path: '/api/accounts/support/report' },
};

/**
 * The routes accounts/api.py binds and the kind of each operation: `run_operation(request,
 * queries.x)` is a query (GET), `services.x` a command (POST), whether or not it takes a body.
 */
function accountsRoutes(source: string): Record<string, { method: string; path: string }> {
  const bound = source.matchAll(/@bind\(router, "([\w.]+)", "([^"]+)"[^)]*\)\nasync def \w+\([^)]*\):\n\s+return await run_operation\(request, (queries|services)\./g);
  return Object.fromEntries([...bound].map(([, op, path, module]) => [op, { method: module === 'queries' ? 'get' : 'post', path: `/api${path}` }]));
}

/**
 * The routes hubs/api.py binds (`live.ninja.bind`): the API mounts its routers at `/api`; a route whose
 * view takes the operation's input as a body (`data: …`) is a command (POST), any other a query (GET).
 */
function hubsRoutes(source: string): Record<string, { method: string; path: string }> {
  // The decorator's other arguments may hold a call of their own (`openapi_extra=_binary("text/csv")`).
  const bound = source.matchAll(/@bind\(router, "([\w.]+)", "([^"]+)"(?:[^()\n]|\([^()]*\))*\)\nasync def \w+\(request(?:, (\w+):)?/g);
  return Object.fromEntries([...bound].map(([, op, path, param]) => [op, { method: param === 'data' ? 'post' : 'get', path: `/api${path}` }]));
}

describe('OPERATION_ROUTES', () => {
  it('binds each operation of the API to its route (base/api.py, accounts/api.py)', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'base.session.me': { method: 'get', path: '/api/me' },
      'accounts.hub.list': { method: 'get', path: '/api/accounts/hubs' },
    });
  });

  it('binds the operations of the businesses panel to their routes (hubs/api.py): queries GET, commands POST', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'hubs.business_type.list': { method: 'get', path: '/api/catalog/business-types' },
      'hubs.plan.list': { method: 'get', path: '/api/plans' },
      'hubs.business.list': { method: 'get', path: '/api/hubs/businesses' },
      'hubs.business.create': { method: 'post', path: '/api/hubs/businesses' },
      'hubs.business.get': { method: 'get', path: '/api/hubs/businesses/detail' },
      'hubs.business.update': { method: 'post', path: '/api/hubs/businesses/update' },
      'hubs.business.change_address': { method: 'post', path: '/api/hubs/businesses/address' },
      'hubs.business.delete': { method: 'post', path: '/api/hubs/businesses/delete' },
      'hubs.business.restore': { method: 'post', path: '/api/hubs/businesses/restore' },
      'hubs.business.open': { method: 'post', path: '/api/hubs/businesses/open' },
      'hubs.address.propose': { method: 'get', path: '/api/hubs/address' },
      'hubs.member.list': { method: 'get', path: '/api/hubs/members' },
      'hubs.member.invite': { method: 'post', path: '/api/hubs/members/invite' },
      'hubs.member.change_role': { method: 'post', path: '/api/hubs/members/change_role' },
      'hubs.member.remove': { method: 'post', path: '/api/hubs/members/remove' },
      'hubs.member.resend': { method: 'post', path: '/api/hubs/members/resend' },
      'hubs.member.cancel': { method: 'post', path: '/api/hubs/members/cancel' },
      'hubs.invitation.list_mine': { method: 'get', path: '/api/hubs/invitations' },
      'hubs.invitation.accept': { method: 'post', path: '/api/hubs/invitations/accept' },
      'hubs.invitation.decline': { method: 'post', path: '/api/hubs/invitations/decline' },
      'hubs.ownership.transfer': { method: 'post', path: '/api/hubs/ownership/transfer' },
      'hubs.ownership.accept': { method: 'post', path: '/api/hubs/ownership/accept' },
      'hubs.ownership.decline': { method: 'post', path: '/api/hubs/ownership/decline' },
      'hubs.ownership.cancel': { method: 'post', path: '/api/hubs/ownership/cancel' },
    });
  });

  it('binds the operations of the Account page to their routes (accounts/api.py), as accounts/api.py does', () => {
    expect(OPERATION_ROUTES).toMatchObject(ACCOUNT_PAGE_ROUTES);
    const api = accountsRoutes(ACCOUNTS_API);
    for (const [op, route] of Object.entries(ACCOUNT_PAGE_ROUTES)) expect(api[op], op).toEqual(route);
  });

  it('binds the operations of the Store to their routes, as billing/api.py, apps/api.py and hubs/api.py do', () => {
    expect(OPERATION_ROUTES).toMatchObject(STORE_ROUTES);
    const api = { ...hubsRoutes(HUBS_API), ...hubsRoutes(BILLING_API), ...hubsRoutes(APPS_API) };
    for (const [op, route] of Object.entries(STORE_ROUTES)) expect(api[op], op).toEqual(route);
  });

  it('binds every hubs operation exactly as hubs/api.py does (path and method)', () => {
    const api = hubsRoutes(HUBS_API);
    expect(Object.keys(api).length).toBeGreaterThan(20);
    for (const [op, route] of Object.entries(OPERATION_ROUTES).filter(([name]) => name.startsWith('hubs.'))) {
      expect(route, op).toEqual(api[op]);
    }
  });

  it('reads the routes of hubs/api.py as they are written (the reader itself)', () => {
    const source = '@bind(router, "x.a.list", "/a", auth=None)\nasync def a(request, params: Query[In]):\n\n@bind(router, "x.a.create", "/a", status=201)\nasync def b(request, data: In):\n';
    expect(hubsRoutes(source)).toEqual({ 'x.a.list': { method: 'get', path: '/api/a' }, 'x.a.create': { method: 'post', path: '/api/a' } });
  });

  it('reads a route whose decorator holds a call of its own (the files of billing/api.py)', () => {
    const source = '@bind(router, "x.a.pdf", "/a/pdf", openapi_extra=_binary("application/pdf"))\nasync def a(request, params: Query[In]):\n';
    expect(hubsRoutes(source)).toEqual({ 'x.a.pdf': { method: 'get', path: '/api/a/pdf' } });
  });

  it('binds the usage of a business to its routes, as hubs/api.py does', () => {
    expect(OPERATION_ROUTES).toMatchObject(USAGE_ROUTES);
    const api = hubsRoutes(HUBS_API);
    for (const [op, route] of Object.entries(USAGE_ROUTES)) expect(api[op], op).toEqual(route);
  });

  it('binds the operations of the Billing section to their routes, as billing/api.py does', () => {
    expect(OPERATION_ROUTES).toMatchObject(BILLING_ROUTES);
    const api = hubsRoutes(BILLING_API);
    for (const [op, route] of Object.entries(BILLING_ROUTES)) expect(api[op], op).toEqual(route);
  });

  it('binds the authorisation of a business to its route, as fiscal/api.py does', () => {
    expect(OPERATION_ROUTES).toMatchObject(FISCAL_ROUTES);
    const api = hubsRoutes(FISCAL_API);
    expect(api).toEqual(FISCAL_ROUTES);
  });

  it('holds nothing else: every operation in the map is one of the API (no stale route)', () => {
    expect(Object.keys(OPERATION_ROUTES).sort()).toEqual(
      [
        'base.session.me',
        'accounts.hub.list',
        'hubs.business_type.list',
        'hubs.plan.list',
        'hubs.business.list',
        'hubs.business.create',
        'hubs.business.get',
        'hubs.business.update',
        'hubs.business.change_address',
        'hubs.business.delete',
        'hubs.business.restore',
        'hubs.business.open',
        'hubs.address.propose',
        'hubs.member.list',
        'hubs.member.invite',
        'hubs.member.change_role',
        'hubs.member.remove',
        'hubs.member.resend',
        'hubs.member.cancel',
        'hubs.invitation.list_mine',
        'hubs.invitation.accept',
        'hubs.invitation.decline',
        'hubs.ownership.transfer',
        'hubs.ownership.accept',
        'hubs.ownership.decline',
        'hubs.ownership.cancel',
        ...Object.keys(ACCOUNT_PAGE_ROUTES),
        ...Object.keys(STORE_ROUTES),
        ...Object.keys(BILLING_ROUTES),
        ...Object.keys(USAGE_ROUTES),
        ...Object.keys(FISCAL_ROUTES),
      ].sort(),
    );
  });
});
