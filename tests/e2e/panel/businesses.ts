import { type APIRequestContext, expect } from '@playwright/test';

import { djangoPrintWarm, runSeed } from './django';
import { apiPost } from './session';

/**
 * `tests/e2e/panel/panel_seed.py seed|clear`: the businesses panel's accounts and businesses (the
 * launcher's variants, Businesses, a business's page, the invitations), always from scratch.
 */
export function seedPanel(action: 'seed' | 'clear' = 'seed'): void {
  runSeed('panel_seed.py', action);
}

/** The id of the business called `name` among the businesses of `request`'s account. */
export async function businessIdOf(request: APIRequestContext, name: string): Promise<string> {
  const response = await request.get('/api/hubs/businesses?limit=50&offset=0');
  expect(response.status(), 'GET /api/hubs/businesses').toBe(200);
  const rows = ((await response.json()) as { rows: Array<{ id: string; name: string }> }).rows;
  const found = rows.find((row) => row.name === name);
  if (!found) throw new Error(`no business ${name} for this account`);
  return found.id;
}

/**
 * A business of `request`'s account called `name` (created through the API, as the panel creates it), ready as the Hub's
 * callback leaves it and with nothing owed to the Hub, on the plan `plan` (its slug); its id. For inside a test: the
 * rest of what the Hub's callback leaves goes through this worker's warm Django (`djangoPrintWarm`, saas#354).
 */
export async function readyBusinessOn(request: APIRequestContext, name: string, plan: string): Promise<string> {
  const created = await apiPost(request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), await created.text()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await djangoPrintWarm(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub, Plan, Subscription',
      `Hub.objects.filter(pk=${JSON.stringify(id)}).update(status="active", ready_at=timezone.now(), pending_hub_call="")`,
      `Subscription.objects.filter(hub_id=${JSON.stringify(id)}).update(plan=Plan.objects.get(slug=${JSON.stringify(plan)}))`,
    ].join('\n'),
  );
  return id;
}
