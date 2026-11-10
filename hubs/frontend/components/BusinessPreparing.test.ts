// The preparation of a new business (mockups `launch.html` «first-preparing», `businesses.html`
// «creating»): a running bar and three steps — created (done), setting it up (now, naming its type when
// one was picked) and what comes next — read out as they change (`role=status`).
// clock: data only — the maintenance timestamps are compared as ISO strings, never with now.
import { afterEach, describe, expect, it } from 'vitest';

import { apiError, describeCall, flush, mountHubs } from '../__tests__/mount-hubs';
import BusinessPreparing from './BusinessPreparing.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const steps = (w: Awaited<ReturnType<typeof mountHubs>>['wrapper']) =>
  w.findAll('ol.deploy-steps li').map((li) => [li.classes().find((c) => ['done', 'current', 'pending'].includes(c)), li.text()]);

describe('BusinessPreparing', () => {
  it('says the business exists, that it is being set up and that it opens by itself', async () => {
    const { wrapper } = await mountHubs(BusinessPreparing, { props: { name: 'Pastelería Dulce', typeName: 'Bakery and pastry', last: 'opensAlone' } });
    expect(steps(wrapper)).toEqual([
      ['done', 'Business created'],
      ['current', 'Setting up your business: Bakery and pastry'],
      ['pending', 'It opens by itself when it finishes'],
    ]);
    const list = wrapper.get('ol.deploy-steps');
    expect(list.attributes()).toMatchObject({ role: 'status', 'aria-live': 'polite', 'aria-label': 'Preparation of Pastelería Dulce' });
    expect(wrapper.get('li.current').attributes('aria-current')).toBe('step');
    const bar = wrapper.get('ion-progress-bar');
    expect((bar.element as HTMLElement & { type?: string }).type).toBe('indeterminate');
    expect(bar.attributes('aria-label')).toBe('Preparation progress');
  });

  // A business is born with every app off (PLAN §33): this step names its type, it installs nothing.
  it.each([
    ['en', 'Setting up your business: Restaurant'],
    ['es', 'Preparando tu negocio: Restaurant'],
  ] as const)('in %s, names the type it is setting up and never modules being installed', async (locale, step) => {
    const { wrapper } = await mountHubs(BusinessPreparing, { props: { name: 'Bar', typeName: 'Restaurant', last: 'ready' }, locale });
    const current = wrapper.get('li.current').text();
    expect(current).toBe(step);
    expect(current).not.toMatch(/m[oó]dul|instal/i);
  });

  it('during maintenance explains the pause and checks again on demand', async () => {
    const { wrapper, calls } = await mountHubs(BusinessPreparing, {
      props: {
        id: 'bakery',
        name: 'Bar',
        typeName: null,
        last: 'ready',
        maintenance: { frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' },
      },
    });
    expect(wrapper.get('[data-testid="preparing-maintenance"]').text()).toContain('Provisioning is paused for maintenance. Your business will be ready in a few minutes.');
    await flush();
    await wrapper.get('[data-testid="preparing-check"]').trigger('click');
    await flush();
    expect(calls().filter((call) => call.path === '/api/hubs/businesses/check').map((call) => call.body)).toEqual([{ id: 'bakery' }, { id: 'bakery' }]);
    expect(wrapper.find('[data-testid="preparing-check-error"]').exists()).toBe(false);
  });

  it('when the check fails, says so and keeps a retry available', async () => {
    const { wrapper } = await mountHubs(BusinessPreparing, {
      props: { id: 'bakery', name: 'Bar', typeName: null, last: 'ready', maintenance: null },
      api: (call) => describeCall(call).path === '/api/hubs/businesses/check'
        ? apiError(503, 'hubs.unavailable', 'Try again.')
        : Response.json({}),
    });
    await flush();
    expect(wrapper.get('[data-testid="preparing-check-error"]').text()).toContain('We could not check the status. Try again.');
    expect(wrapper.get('[data-testid="preparing-check"]').text()).toContain('Check now');
  });

  it('in Spanish, names the maintenance pause and the recovery action', async () => {
    const { wrapper } = await mountHubs(BusinessPreparing, {
      props: { id: 'bakery', name: 'Bar', typeName: null, last: 'ready', maintenance: { frozen: true, reason: 'Aurora upgrade', since: null } },
      locale: 'es',
    });
    expect(wrapper.get('[data-testid="preparing-maintenance"]').text()).toContain('Alta en pausa por mantenimiento: tu negocio estará listo en unos minutos.');
    expect(wrapper.get('[data-testid="preparing-check"]').text()).toContain('Comprobar ahora');
  });

  it('without a type, sets up «your business», and in the dialog ends on «Ready to open»', async () => {
    const { wrapper } = await mountHubs(BusinessPreparing, { props: { name: 'Bar', typeName: null, last: 'ready' }, locale: 'es' });
    expect(steps(wrapper)).toEqual([
      ['done', 'Negocio creado'],
      ['current', 'Preparando tu negocio'],
      ['pending', 'Listo para abrir'],
    ]);
  });
});
