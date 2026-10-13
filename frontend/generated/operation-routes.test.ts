// The op → route map the SDK's API client uses. Written by hand for now (generated from
// `/api/openapi.json` later, as in hub-next). Sign-in is not here: allauth.headless is not an
// operation, the SDK reaches it through its own client (`createAllauthClient`).
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from './operation-routes';

describe('OPERATION_ROUTES', () => {
  it('binds each operation of the API to its route (base/api.py, accounts/api.py)', () => {
    expect(OPERATION_ROUTES).toEqual({
      'base.session.me': { method: 'get', path: '/api/me' },
      'accounts.hub.list': { method: 'get', path: '/api/accounts/hubs' },
    });
  });
});
