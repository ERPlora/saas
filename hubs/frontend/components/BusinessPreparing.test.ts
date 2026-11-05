// The preparation of a new business (mockups `launch.html` «first-preparing», `businesses.html`
// «creating»): a running bar and three steps — created (done), setting it up (now, naming its type when
// one was picked) and what comes next — read out as they change (`role=status`).
import { afterEach, describe, expect, it } from 'vitest';

import { mountHubs } from '../__tests__/mount-hubs';
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

  it('without a type, sets up «your business», and in the dialog ends on «Ready to open»', async () => {
    const { wrapper } = await mountHubs(BusinessPreparing, { props: { name: 'Bar', typeName: null, last: 'ready' }, locale: 'es' });
    expect(steps(wrapper)).toEqual([
      ['done', 'Negocio creado'],
      ['current', 'Preparando tu negocio'],
      ['pending', 'Listo para abrir'],
    ]);
  });
});
