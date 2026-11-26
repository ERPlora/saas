// «Own domain» in a business's Settings (HUBS-F17, saas#195): the live `hubs.custom_domain.get` of the business — whether
// this deployment connects domains, whether its plan includes one and the domain it has — and, for its owner, asking
// for one (`hubs.custom_domain.request`) and removing it (`hubs.custom_domain.remove`). With a domain it shows its state
// and where it is stuck in the server's words, the two CNAME records to create with «Copy», the hourly check and its
// «three failures in a row and we stop serving it». A plan without it says so, with the way to the plans.
import { applySurface } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (original) => (await import('../__tests__/module-mocks')).ionicWithModalStub(original));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { ACTIVE, NONE, OP, OWNER_BUSINESS, PENDING, setup, setUpCustomDomainCard, status } from '../__tests__/custom-domain-card';
import { apiError, BYE, errorFrame, flush, ionProps, subId } from '../__tests__/mount-hubs';
import { iconAction, iconOnly } from '../../../frontend/__tests__/icon-action';

const ADMIN_BUSINESS = { ...OWNER_BUSINESS, role: 'hub_admin', can: { manage_billing: false } };

setUpCustomDomainCard();

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

  it('names the first plan on sale that includes it, read from `hubs.plan.list` (saas#301)', async () => {
    const asked: string[] = [];
    const plans = {
      signup_trial_days: 0,
      cheapest_slug: 'free',
      plans: [
        { slug: 'free', name: 'Free', includes_custom_domain: false },
        { slug: 'starter', name: 'Starter', includes_custom_domain: false },
        { slug: 'standard', name: 'Standard', includes_custom_domain: true },
        { slug: 'pro', name: 'Pro', includes_custom_domain: true },
      ],
    };
    const s = await setup(status(null, { in_plan: false }), {
      business: { ...OWNER_BUSINESS, plan: { slug: 'starter', name: 'Starter' } },
      api: (c) => {
        asked.push(`${c.method} ${c.path}`);
        return c.path === '/api/plans' ? Response.json(plans) : Response.json({});
      },
    });
    await flush();
    const notice = s.testid('domain-not-in-plan');
    expect(asked).toEqual(['GET /api/plans']);
    expect(notice.text()).toContain('The Starter plan does not include an own domain');
    expect(notice.text()).toContain('The Standard plan includes it. Switch to it to show your website on your own domain.');
    expect(notice.text()).not.toContain('Change to a plan that includes one');
  });

  it('never names an upgrade-only plan, which a business can only reach from a paid one: then «a plan that includes one»', async () => {
    const plans = {
      plans: [
        { slug: 'starter', name: 'Starter', includes_custom_domain: false, upgrade_only: false },
        { slug: 'standard', name: 'Standard', includes_custom_domain: false, upgrade_only: false },
        { slug: 'pro', name: 'Pro', includes_custom_domain: true, upgrade_only: true },
      ],
    };
    const s = await setup(status(null, { in_plan: false }), {
      business: { ...OWNER_BUSINESS, plan: { slug: 'free', name: 'Free' } },
      api: (c) => Response.json(c.path === '/api/plans' ? plans : {}),
    });
    await flush();
    const notice = s.testid('domain-not-in-plan');
    expect(notice.text()).toContain('Change to a plan that includes one to show your website on your own domain.');
    expect(notice.text()).not.toContain('Pro');
  });

  it('names the first plan one can sign up for that includes it, past an upgrade-only one listed before it', async () => {
    const plans = {
      plans: [
        { slug: 'pro', name: 'Pro', includes_custom_domain: true, upgrade_only: true },
        { slug: 'standard', name: 'Standard', includes_custom_domain: true, upgrade_only: false },
      ],
    };
    const s = await setup(status(null, { in_plan: false }), { api: (c) => Response.json(c.path === '/api/plans' ? plans : {}) });
    await flush();
    expect(s.testid('domain-not-in-plan').text()).toContain('The Standard plan includes it. Switch to it to show your website on your own domain.');
  });

  it('with a plan that includes it the plans are never asked for', async () => {
    const asked: string[] = [];
    const s = await setup(NONE, { api: (c) => (asked.push(c.path), Response.json({})) });
    await flush();
    expect(s.testid('domain-form').exists()).toBe(true);
    expect(asked).toEqual([]);
  });

  it('when the plans cannot be read, or none includes it, it says «a plan that includes one»', async () => {
    const failing = await setup(status(null, { in_plan: false }), { api: () => new Response('', { status: 500 }) });
    await flush();
    expect(failing.testid('domain-not-in-plan').text()).toContain('Change to a plan that includes one to show your website on your own domain.');
    failing.wrapper.unmount();
    const none = await setup(status(null, { in_plan: false }), {
      api: (c) => Response.json(c.path === '/api/plans' ? { plans: [{ slug: 'free', name: 'Free', includes_custom_domain: false }] } : {}),
    });
    await flush();
    expect(none.testid('domain-not-in-plan').text()).toContain('Change to a plan that includes one to show your website on your own domain.');
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

describe('CustomDomainCard: Spanish', () => {
  it('names the plan that includes it in Spanish', async () => {
    const s = await setup(status(null, { in_plan: false }), {
      locale: 'es',
      api: (c) => Response.json(c.path === '/api/plans' ? { plans: [{ slug: 'pro', name: 'Pro', includes_custom_domain: true }] } : {}),
    });
    await flush();
    expect(s.testid('domain-not-in-plan').text()).toContain('Lo incluye el plan Pro. Cámbiate a él para mostrar tu web en tu propio dominio.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(status(null, { in_plan: false }), { locale: 'es' });
    expect(s.testid('custom-domain').text()).toContain('Dominio propio');
    expect(s.testid('domain-not-in-plan').text()).toContain('El plan Standard no incluye dominio propio');
    expect(s.testid('domain-plans').text()).toBe('Ver planes');
    await s.show(status(PENDING));
    expect(s.testid('domain-record-validation').text()).toContain('1. Registro de validación');
    expect(s.testid('domain-record-traffic').text()).toContain('2. Registro que apunta a ERPlora');
    expect(iconAction(s.testid('domain-remove').element)).toEqual(iconOnly('Quitar dominio'));
  });
});
