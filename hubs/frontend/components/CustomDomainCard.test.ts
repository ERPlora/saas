// «Own domain» in a business's Settings (HUBS-F17, saas#195): the live `hubs.custom_domain.get` of the business — whether
// this deployment connects domains, whether its plan includes one and the domain it has — and, for its owner, asking
// for one (`hubs.custom_domain.request`) and removing it (`hubs.custom_domain.remove`). With a domain it shows its state
// and where it is stuck in the server's words, the two CNAME records to create with «Copy», the hourly check and its
// «three failures in a row and we stop serving it». A plan without it says so, with the way to the plans.
// clock: data only — no code under test compares these dates with now.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (original) => (await import('../__tests__/module-mocks')).ionicWithModalStub(original));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import {
  accessibleName,
  apiError,
  BYE,
  describeCall,
  errorFrame,
  flush,
  ionProps,
  mountHubs,
  stubClipboard,
  subId,
} from '../__tests__/mount-hubs';
import CustomDomainCard from './CustomDomainCard.vue';

const OP = 'hubs.custom_domain.get';
const OWNER_BUSINESS = { id: 'h1', role: 'hub_owner', plan: { slug: 'standard', name: 'Standard' }, can: { manage_billing: true } };
const ADMIN_BUSINESS = { ...OWNER_BUSINESS, role: 'hub_admin', can: { manage_billing: false } };

const PENDING = {
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
const ACTIVE = {
  ...PENDING,
  state: 'active',
  state_label: 'Connected',
  reason: '',
  reason_label: '',
  checked_at: '2026-11-05T09:00:00Z',
  activated_at: '2026-11-04T18:00:00Z',
};
const NONE = { available: true, in_plan: true, domain: null };
const status = (domain: unknown, extra: Record<string, unknown> = {}) => ({ ...NONE, domain, ...extra });

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(
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

describe('CustomDomainCard: what it asks and when it shows', () => {
  it('asks for the domain with the business’s id alone, so it rides the page’s first stream', async () => {
    const s = await setup(null, { business: null });
    expect(s.call.subs.map((sub) => [sub.op, sub.params])).toEqual([[OP, { id: 'h1' }]]);
  });

  it('shows nothing until the business is there (who may change it comes with it)', async () => {
    const s = await setup(NONE, { business: null });
    expect(s.testid('custom-domain').exists()).toBe(false);
    await s.wrapper.setProps({ business: OWNER_BUSINESS });
    expect(s.testid('custom-domain').text()).toContain('Own domain');
  });

  it('loading: a skeleton under its title; an answer replaces it', async () => {
    const s = await setup(null);
    expect(s.testid('domain-loading').exists()).toBe(true);
    expect(s.testid('domain-form').exists()).toBe(false);
    await s.show(NONE);
    expect(s.testid('domain-loading').exists()).toBe(false);
    expect(s.testid('domain-form').exists()).toBe(true);
  });

  it('a query that fails says so with «Retry», which asks again', async () => {
    const s = await setup(null);
    s.call.push(errorFrame(subId(s.client, OP), 'internal_error'));
    await flush();
    expect(s.testid('domain-error').text()).toContain('We could not load the domain of this business.');
    expect(s.testid('domain-form').exists()).toBe(false);
    s.q('domain-retry')!.click();
    await flush();
    expect(s.net.streams).toHaveLength(2);
  });

  it('nothing in time is an error too, never a skeleton for ever', async () => {
    const s = await setup(null);
    s.call.push(BYE);
    await s.clock.advance(LIVE_TIMEOUT_MS + 1);
    await flush();
    expect(s.testid('domain-error').exists()).toBe(true);
    expect(s.testid('domain-loading').exists()).toBe(false);
  });
});

describe('CustomDomainCard: what is offered', () => {
  it('a deployment that does not connect domains says so, with no form', async () => {
    const s = await setup(status(null, { available: false }));
    expect(s.testid('domain-unavailable').text()).toContain('Own domains are not available yet.');
    expect(s.testid('domain-form').exists()).toBe(false);
  });

  it('a plan without it says what it does not include and leads to the plans, not a disabled form', async () => {
    const s = await setup(status(null, { in_plan: false }), { business: { ...OWNER_BUSINESS, plan: { slug: 'starter', name: 'Starter' } } });
    const notice = s.testid('domain-not-in-plan');
    expect(notice.text()).toContain('The Starter plan does not include an own domain');
    expect(notice.text()).toContain('Change to a plan that includes one to show your website on your own domain.');
    const plans = s.testid('domain-plans');
    expect(plans.text()).toBe('See plans');
    expect(plans.attributes('routerlink')).toBe('/dashboard/store/plans?business=h1');
    expect(s.testid('domain-form').exists()).toBe(false);
    expect(s.wrapper.find('ion-input').exists()).toBe(false);
  });

  it('without a plan it says the same of «your plan»; whoever does not handle the billing has no way to the plans', async () => {
    const s = await setup(status(null, { in_plan: false }), { business: { ...ADMIN_BUSINESS, plan: null } });
    expect(s.testid('domain-not-in-plan').text()).toContain('Your plan does not include an own domain');
    expect(s.testid('domain-plans').exists()).toBe(false);
  });

  it('inside the app it says where the plan is changed, without a link', async () => {
    applySurface('desktop');
    const s = await setup(status(null, { in_plan: false }));
    expect(s.testid('domain-not-in-plan').text()).toContain('To change your plan or add modules, go to erplora.com in your browser.');
    expect(s.testid('domain-plans').exists()).toBe(false);
  });

  it('an administrator reads the state but only the owner connects or removes it', async () => {
    const empty = await setup(NONE, { business: ADMIN_BUSINESS });
    expect(empty.testid('domain-owner-only').text()).toContain('Only the owner of the business can connect or remove its domain.');
    expect(empty.testid('domain-form').exists()).toBe(false);
    empty.wrapper.unmount();
    const s = await setup(status(ACTIVE), { business: ADMIN_BUSINESS });
    expect(s.testid('domain-record-traffic').text()).toContain('hub-h1.erplora.com');
    expect(s.testid('domain-remove').exists()).toBe(false);
  });
});

describe('CustomDomainCard: connecting a domain', () => {
  it('the owner writes it, with the advice for a root domain, and gets the two records to create at once', async () => {
    const s = await setup(NONE, { api: () => Response.json(PENDING) });
    expect(ionProps(s.testid('domain-input'), 'label', 'placeholder', 'mode', 'fill')).toEqual({
      label: 'Your domain',
      placeholder: 'www.yourbusiness.com',
      mode: 'md',
      fill: 'outline',
    });
    expect(s.testid('domain-form').text()).toContain('A root domain such as yourbusiness.com cannot point to ERPlora');
    await s.type('  www.minegocio.es ');
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.method, c.path, c.body])).toEqual([
      ['POST', '/api/hubs/businesses/custom-domain', { id: 'h1', domain: 'www.minegocio.es' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Now create the records of www.minegocio.es');
    expect(s.testid('domain-form').exists()).toBe(false);
    expect(s.testid('domain-name').text()).toBe('www.minegocio.es');
    expect(s.testid('domain-record-validation').text()).toContain('_3639ac514e78.www.minegocio.es');
    expect(s.testid('domain-record-traffic').text()).toContain('hub-h1.erplora.com');
  });

  it('asks for nothing while the field is empty', async () => {
    const s = await setup(NONE);
    expect(s.testid('domain-connect').attributes('disabled')).toBeDefined();
    await s.type('   ');
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.calls()).toEqual([]);
  });

  it('what the server refuses of the name goes on the field', async () => {
    const s = await setup(NONE, {
      api: () => apiError(422, 'hubs.custom_domain_apex', 'Invalid payload', { domain: 'A root domain cannot point at ERPlora.' }),
    });
    await s.type('minegocio.es');
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(ionProps(s.testid('domain-input'), 'errorText')).toEqual({ errorText: 'A root domain cannot point at ERPlora.' });
    expect(s.testid('domain-input').classes()).toContain('ion-invalid');
    expect(s.testid('domain-form-error').exists()).toBe(false);
  });

  it('any other refusal is said above the button, in the server’s words', async () => {
    const s = await setup(NONE, { api: () => apiError(409, 'hubs.custom_domain_taken', 'Another business is connected to this domain.') });
    await s.type('www.minegocio.es');
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.testid('domain-form-error').text()).toContain('Another business is connected to this domain.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(NONE, { api: () => Promise.reject(new TypeError('Failed to fetch')) as never });
    await s.type('www.minegocio.es');
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.testid('domain-form-error').text()).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('the live answer that follows replaces the request’s own', async () => {
    const s = await setup(NONE, { api: () => Response.json(PENDING) });
    await s.type('www.minegocio.es');
    await s.testid('domain-connect').trigger('click');
    await flush();
    await s.show(status({ ...PENDING, reason: 'cname_missing', reason_label: 'Create the record that points your domain at ERPlora.' }));
    expect(s.testid('domain-reason').text()).toContain('Create the record that points your domain at ERPlora.');
  });
});

describe('CustomDomainCard: a domain on its way', () => {
  it('its state and where it is stuck, in the server’s words, and the two records in order with «Copy»', async () => {
    const s = await setup(status(PENDING));
    expect(s.testid('domain-name').text()).toBe('www.minegocio.es');
    expect(s.testid('domain-state').text()).toBe('Waiting for your records');
    expect(s.testid('domain-reason').text()).toContain('Create the validation record: the certificate is waiting for it.');
    const validation = s.testid('domain-record-validation');
    expect(validation.text()).toContain('1. Validation record');
    expect(validation.text()).toContain('Create it first and keep it for good: it renews the certificate.');
    expect(validation.findAll('[data-testid="copy-value"]').map((v) => v.text())).toEqual([
      '_3639ac514e78.www.minegocio.es',
      '_98d2646601fa.xlfgrmvvlj.acm-validations.aws',
    ]);
    const traffic = s.testid('domain-record-traffic');
    expect(traffic.text()).toContain('2. Record that points to ERPlora');
    expect(traffic.text()).toContain('Create it once the certificate is ready');
    expect(traffic.findAll('[data-testid="copy-value"]').map((v) => v.text())).toEqual(['www.minegocio.es', 'hub-h1.erplora.com']);
    expect(s.wrapper.findAll('[data-testid="domain-record-type"]').map((t) => t.text())).toEqual(['CNAME', 'CNAME']);
    expect(s.testid('domain-checks').text()).toContain(
      'If it stops pointing to ERPlora three times in a row, we stop serving your website on it and email you',
    );
  });

  it('each «Copy» copies its own value and says it was copied', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    const s = await setup(status(PENDING));
    const buttons = s.testid('domain-record-validation').findAll('[data-testid="copy-button"]');
    expect(buttons.map((b) => accessibleName(b))).toEqual(['Copy the name', 'Copy the value']);
    await buttons[1].trigger('click');
    await flush();
    expect(writeText).toHaveBeenCalledWith('_98d2646601fa.xlfgrmvvlj.acm-validations.aws');
    expect(toastSuccess).toHaveBeenCalledWith('Copied');
  });

  it('a validation record ACM has not given yet is on its way; «Look again» asks again', async () => {
    const s = await setup(status({ ...PENDING, validation: null }));
    expect(s.testid('domain-validation-coming').text()).toContain('It is still being prepared and appears here in a few seconds.');
    expect(s.testid('domain-record-validation').findAll('[data-testid="copy-value"]')).toHaveLength(0);
    await s.testid('domain-look-again').trigger('click');
    await flush();
    expect(s.net.streams).toHaveLength(2);
  });

  it('the last check is dated', async () => {
    const s = await setup(status({ ...PENDING, checked_at: '2026-11-05T09:00:00Z' }));
    expect(s.testid('domain-checked-at').text()).toMatch(/^Last check: Nov 5, 2026/);
  });
});

describe('CustomDomainCard: a connected domain', () => {
  it('says it is served there and since when; no failure, no warning of one', async () => {
    const s = await setup(status(ACTIVE));
    expect(s.testid('domain-state').text()).toBe('Connected');
    expect(s.testid('domain-reason').text()).toContain('Your website is served on www.minegocio.es.');
    expect(s.testid('domain-active-since').text()).toMatch(/^Connected since Nov 4, 2026/);
    expect(s.testid('domain-failures').exists()).toBe(false);
    expect(s.testid('domain-record-traffic').exists()).toBe(true);
  });

  it('a check that failed is counted against the three that stop it', async () => {
    const one = await setup(status({ ...ACTIVE, failures: 1, reason: 'cname_missing', reason_label: 'Create the record that points your domain at ERPlora.' }));
    expect(one.testid('domain-failures').text()).toBe(
      'The last check found a problem: at three in a row we stop serving your website on this domain.',
    );
    expect(one.testid('domain-reason').text()).toContain('Create the record that points your domain at ERPlora.');
    one.wrapper.unmount();
    const two = await setup(status({ ...ACTIVE, failures: 2 }));
    expect(two.testid('domain-failures').text()).toBe(
      'The last 2 checks found a problem: at three in a row we stop serving your website on this domain.',
    );
  });
});

describe('CustomDomainCard: a domain that is not connected', () => {
  const LAPSED = {
    ...PENDING,
    state: 'lapsed',
    state_label: 'Not connected',
    reason: 'checks_failed',
    reason_label: 'Your domain stopped pointing at ERPlora, so your website is no longer served on it. It comes back by itself when the record does.',
    failures: 3,
  };

  it('says why in the server’s words, and lets its owner ask for it again or for another one', async () => {
    const s = await setup(status(LAPSED), { api: () => Response.json(PENDING) });
    expect(s.testid('domain-state').text()).toBe('Not connected');
    expect(s.testid('domain-reason').text()).toContain('It comes back by itself when the record does.');
    expect(s.testid('domain-failures').exists()).toBe(false);
    expect(ionProps(s.testid('domain-input'), 'value')).toEqual({ value: 'www.minegocio.es' });
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/businesses/custom-domain', { id: 'h1', domain: 'www.minegocio.es' }]]);
  });

  it('is still removed by its owner', async () => {
    const s = await setup(status(LAPSED));
    expect(s.testid('domain-remove').exists()).toBe(true);
  });
});

describe('CustomDomainCard: removing it', () => {
  const REMOVING = { ...ACTIVE, state: 'removing', state_label: 'Being removed', reason: '', reason_label: '' };

  it('asks first, says what follows, then removes it and shows it going', async () => {
    const s = await setup(status(ACTIVE), { api: () => Response.json(status(REMOVING)) });
    await s.testid('domain-remove').trigger('click');
    await flush();
    expect(s.q('domain-remove-dialog')!.getAttribute('aria-label')).toBe('Remove www.minegocio.es');
    expect(s.q('domain-remove-dialog')!.textContent).toContain(
      'Your website stops being served on www.minegocio.es and stays at its erplora.com address.',
    );
    expect(s.q('domain-remove-dialog-submit')!.color).toBe('danger');
    s.q('domain-remove-dialog-submit')!.click();
    await flush();
    expect(s.calls().map((c) => [c.method, c.path, c.body])).toEqual([['POST', '/api/hubs/businesses/custom-domain/remove', { id: 'h1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('www.minegocio.es is being removed');
    expect(s.testid('domain-state').text()).toBe('Being removed');
    expect(s.testid('domain-removing').text()).toContain('Your website is no longer served on www.minegocio.es.');
    expect(s.testid('domain-record-traffic').exists()).toBe(false);
    expect(s.testid('domain-remove').exists()).toBe(false);
  });

  it('a refusal stays in the dialog, which stays open', async () => {
    const s = await setup(status(ACTIVE), { api: () => apiError(409, 'hubs.custom_domains_off', 'Own domains are not available yet.') });
    await s.testid('domain-remove').trigger('click');
    await flush();
    s.q('domain-remove-dialog-submit')!.click();
    await flush();
    expect(s.q('domain-remove-dialog-error')!.textContent).toContain('Own domains are not available yet.');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(s.testid('domain-state').text()).toBe('Connected');
  });

  it('once gone, the live answer brings the form back', async () => {
    const s = await setup(status(REMOVING));
    await s.show(NONE);
    expect(s.testid('domain-name').exists()).toBe(false);
    expect(s.testid('domain-form').exists()).toBe(true);
  });

  it('a deployment that stopped connecting domains shows the one there is, without changing it', async () => {
    const s = await setup(status(ACTIVE, { available: false }));
    expect(s.testid('domain-state').text()).toBe('Connected');
    expect(s.testid('domain-remove').exists()).toBe(false);
    expect(s.testid('domain-unavailable').exists()).toBe(false);
  });
});

describe('CustomDomainCard: the colours say who has to act', () => {
  const tones = (s: Awaited<ReturnType<typeof setup>>) => ({
    pill: s.wrapper.getComponent(StatusPill).props(),
    reason: s.testid('domain-reason').exists() ? s.wrapper.getComponent(InlineFeedback).props('tone') : null,
  });

  it.each([
    ['waiting for the owner’s records', PENDING, 'warning', false, 'warning'],
    ['waiting for ERPlora, which tries again by itself', { ...PENDING, reason: 'quota_full', reason_label: 'No room.' }, 'warning', false, 'info'],
    ['served', ACTIVE, 'success', false, 'success'],
    ['not served', { ...PENDING, state: 'lapsed', state_label: 'Not connected', reason: 'certificate_failed', reason_label: 'Refused.' }, 'danger', false, 'danger'],
    ['going', { ...ACTIVE, state: 'removing', state_label: 'Being removed' }, 'neutral', true, null],
  ])('%s', async (_, domain, pill, busy, reason) => {
    const s = await setup(status(domain));
    expect(tones(s)).toMatchObject({ pill: { tone: pill, busy }, reason });
  });

  it('the hourly check is said only of a domain it still looks at', async () => {
    for (const [domain, said] of [
      [PENDING, true],
      [ACTIVE, true],
      [{ ...PENDING, state: 'lapsed', state_label: 'Not connected', reason: 'checks_failed', reason_label: 'Gone.' }, false],
      [{ ...ACTIVE, state: 'removing', state_label: 'Being removed' }, false],
    ] as const) {
      const s = await setup(status(domain));
      expect(s.testid('domain-checks').exists(), domain.state).toBe(said);
      s.wrapper.unmount();
    }
  });
});

describe('CustomDomainCard: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup(status(null, { in_plan: false }), { locale: 'es' });
    expect(s.testid('custom-domain').text()).toContain('Dominio propio');
    expect(s.testid('domain-not-in-plan').text()).toContain('El plan Standard no incluye dominio propio');
    expect(s.testid('domain-plans').text()).toBe('Ver planes');
    await s.show(status(PENDING));
    expect(s.testid('domain-record-validation').text()).toContain('1. Registro de validación');
    expect(s.testid('domain-record-traffic').text()).toContain('2. Registro que apunta a ERPlora');
    expect(s.testid('domain-remove').text()).toContain('Quitar dominio');
  });
});
