// The op → route map the SDK's API client uses. Written by hand for now (generated from
// `/api/openapi.json` later, as in hub-next). Sign-in is not here: allauth.headless is not an
// operation, the SDK reaches it through its own client (`createAllauthClient`).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from './operation-routes';

const HUBS_API = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hubs', 'api.py'), 'utf8');

/**
 * The routes hubs/api.py binds (`live.ninja.bind`): the API mounts its routers at `/api`; a route whose
 * view takes the operation's input as a body (`data: …`) is a command (POST), any other a query (GET).
 */
function hubsRoutes(source: string): Record<string, { method: string; path: string }> {
  const bound = source.matchAll(/@bind\(router, "([\w.]+)", "([^"]+)"[^)]*\)\nasync def \w+\(request(?:, (\w+):)?/g);
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
      ].sort(),
    );
  });
});
