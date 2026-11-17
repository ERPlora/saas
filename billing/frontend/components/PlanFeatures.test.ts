import { describe, expect, it } from 'vitest';

import { mountBilling } from '../__tests__/mount-billing';
import PlanFeatures from './PlanFeatures.vue';

const LINES = Array.from({ length: 7 }, (_, index) => ({ kind: 'feature' as const, text: `Feature ${index + 1}` }));

async function features(locale: 'en' | 'es' = 'en') {
  return mountBilling(PlanFeatures, { locale, props: { lines: LINES, expanded: false } });
}

describe('PlanFeatures', () => {
  it('shows five lines and expands through a labelled disclosure button', async () => {
    const { wrapper } = await features();
    const list = wrapper.get('ion-list');
    const toggle = wrapper.get('[data-testid="plan-features-toggle"]');
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect(toggle.text()).toBe('Show all features');
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(toggle.attributes('aria-controls')).toBe(list.attributes('id'));

    await toggle.trigger('click');
    expect(wrapper.findAll('ion-item')).toHaveLength(7);
    expect(toggle.attributes('aria-expanded')).toBe('true');
    expect(toggle.text()).toBe('Show fewer');

    await toggle.trigger('click');
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect(wrapper.text()).not.toContain('Feature 6');
  });

  it('does not add a disclosure when every line fits', async () => {
    const { wrapper } = await features();
    await wrapper.setProps({ lines: LINES.slice(0, 5) });
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect(wrapper.find('[data-testid="plan-features-toggle"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await features('es');
    const toggle = wrapper.get('[data-testid="plan-features-toggle"]');
    expect(toggle.text()).toBe('Ver todas las características');
    await toggle.trigger('click');
    expect(toggle.text()).toBe('Ver menos');
  });
});
