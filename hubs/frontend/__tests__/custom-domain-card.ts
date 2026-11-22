// «Own domain» (`CustomDomainCard`) mounted for its tests, for the owner by default, with the answers of its live
// `hubs.custom_domain.get`. A test file mocks `@ionic/vue` and `@erplora/ui/shell` as the panel's tests do and calls
// `setUpCustomDomainCard()` at its top.
// clock: data only — no code under test compares these dates with now.
import { applySurface, toastSuccess } from '@erplora/ui/shell';
import { afterEach, vi } from 'vitest';

import CustomDomainCard from '../components/CustomDomainCard.vue';
import { describeCall, flush, mountHubs } from './mount-hubs';

export const OP = 'hubs.custom_domain.get';
export const OWNER_BUSINESS = { id: 'h1', role: 'hub_owner', plan: { slug: 'standard', name: 'Standard' }, can: { manage_billing: true } };

export const PENDING = {
  id: 'd1',
  domain: 'www.minegocio.es',
  state: 'pending',
  state_label: 'Waiting for your records',
  reason: 'certificate_pending',
  reason_label: 'Create the validation record: the certificate is waiting for it.',
  validation: { type: 'CNAME', name: '_3639ac514e78.www.minegocio.es', value: '_98d2646601fa.xlfgrmvvlj.acm-validations.aws' },
  traffic: { type: 'CNAME', name: 'www.minegocio.es', value: 'hub-h1.erplora.com' },
  failures: 0,
  checked_at: null,
  activated_at: null,
};
export const ACTIVE = {
  ...PENDING,
  state: 'active',
  state_label: 'Connected',
  reason: '',
  reason_label: '',
  checked_at: '2026-11-05T09:00:00Z',
  activated_at: '2026-11-04T18:00:00Z',
};
export const NONE = { available: true, in_plan: true, domain: null };
export const status = (domain: unknown, extra: Record<string, unknown> = {}) => ({ ...NONE, domain, ...extra });

export function setUpCustomDomainCard(): void {
  afterEach(() => {
    applySurface('web');
    vi.restoreAllMocks();
    vi.mocked(toastSuccess).mockClear();
    document.body.innerHTML = '';
  });
}

export async function setup(
  answer: unknown = NONE,
  options: { business?: Record<string, unknown> | null; locale?: 'en' | 'es'; api?: (c: ReturnType<typeof describeCall>) => Response } = {},
) {
  const business = options.business === undefined ? OWNER_BUSINESS : options.business;
  const m = await mountHubs(CustomDomainCard, {
    props: { id: 'h1', ...(business ? { business } : {}) },
    locale: options.locale,
    api: (call) => (options.api ?? (() => Response.json({})))(describeCall(call)),
  });
  const call = await m.live();
  if (answer !== null) await m.result(call, OP, answer);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as (HTMLElement & Record<string, unknown>) | null;
  async function type(value: string) {
    testid('domain-input').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  return { ...m, call, testid, q, type, show: (data: unknown, rev = 2) => m.result(call, OP, data, rev) };
}
