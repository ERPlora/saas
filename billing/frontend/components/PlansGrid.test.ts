import { AlignedCardGrid } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { FREE_SUBSCRIPTION, STARTER, plan } from '../__tests__/fixtures';
import { flush, mountBilling } from '../__tests__/mount-billing';
import type { BillingInterval } from '../../../frontend/sdk-types/store';
import PlansGrid from './PlansGrid.vue';

const longPlan = (slug: string, name: string) =>
  plan(slug, name, slug === 'free' ? '0.00' : '29.99', slug === 'free' ? '0.00' : '299.90', {
    features: Array.from({ length: 7 }, (_, index) => `${name} feature ${index + 1}`),
  });

async function grid(sold: Record<string, BillingInterval[]> = { starter: ['month', 'year'], standard: ['month', 'year'] }) {
  return mountBilling(PlansGrid, {
    props: {
      plans: [longPlan('free', 'Free'), longPlan('starter', 'Starter'), longPlan('standard', 'Standard')],
      period: 'month',
      sold,
      subscription: FREE_SUBSCRIPTION,
      block: null,
      scheduledPlanName: '',
    },
  });
}

describe('PlansGrid', () => {
  it('uses its own grid and expands every plan together', async () => {
    const { wrapper } = await grid();
    expect(wrapper.classes()).toContain('plans-grid');
    expect(wrapper.classes()).not.toContain('card-grid');
    expect(wrapper.findAll('ion-card')).toHaveLength(3);
    expect(wrapper.findAll('ion-card').map((card) => card.findAll('ion-item').length)).toEqual([5, 5, 5]);

    await wrapper.findAll('[data-testid="plan-features-toggle"]')[1].trigger('click');
    await flush();
    const toggles = wrapper.findAll('[data-testid="plan-features-toggle"]');
    const states = () => toggles.map((toggle) => toggle.element.shadowRoot?.querySelector('button')?.getAttribute('aria-expanded'));
    expect(states()).toEqual(['true', 'true', 'true']);
    expect(wrapper.findAll('ion-card').map((card) => card.findAll('ion-item').length)).toEqual([8, 8, 8]);

    await toggles[0].trigger('click');
    await flush();
    expect(states()).toEqual(['false', 'false', 'false']);
    expect(wrapper.findAll('ion-card').map((card) => card.findAll('ion-item').length)).toEqual([5, 5, 5]);
  });

  it('lays the plans on the shared aligned grid, seven rows per card', async () => {
    const { wrapper } = await grid();
    const aligned = wrapper.findComponent(AlignedCardGrid);
    expect(aligned.exists()).toBe(true);
    expect(aligned.props('rows')).toBe(7);
    expect(aligned.findAll('ion-card')).toHaveLength(3);
  });

  it('keeps the card actions and their plan context', async () => {
    const { wrapper } = await grid();
    await wrapper.get('[data-testid="plan-starter"]').get('[data-testid="plan-upgrade"]').trigger('click');
    expect(wrapper.emitted('upgrade')).toEqual([[{ ...STARTER, features: expect.any(Array) }, 'month']]);
  });

  it('hands each card the billings its plan is sold with: a plan the catalog lists none for is not bought', async () => {
    const { wrapper } = await grid({ starter: ['month', 'year'] });
    const button = (slug: string) => wrapper.get(`[data-testid="plan-${slug}"]`).get('[data-testid="plan-upgrade"]').element as unknown as { disabled: boolean };
    expect(button('starter').disabled).toBe(false);
    expect(button('standard').disabled).toBe(true);
    expect(wrapper.get('[data-testid="plan-standard"]').get('[data-testid="plan-hint"]').text()).toBe('Not on sale right now');
  });
});
