// A plan the Store offers but Stripe does not sell with the billing the switch says (no Stripe price for it in the
// admin): its button does not buy and says why, instead of failing with «This cannot be bought right now» once pressed.
import { describe, expect, it } from 'vitest';

import { FREE_SUBSCRIPTION, plan, subscription } from '../__tests__/fixtures';
import { card } from '../__tests__/plan-card';

const STANDARD = plan('standard', 'Standard', '59.99', '599.90');
const disabled = (button: { element: unknown }) => (button.element as { disabled: boolean }).disabled;

describe('PlanCard, a billing Stripe does not sell the plan with', () => {
  it('a Free business is not offered to upgrade to a plan with no Stripe price, and is told it is not on sale', async () => {
    const s = await card({ plan: STANDARD, sold: [], subscription: FREE_SUBSCRIPTION });
    expect(disabled(s.text('plan-upgrade'))).toBe(true);
    expect(s.text('plan-hint').text()).toBe('Not on sale right now');
    const es = await card({ plan: STANDARD, sold: [], subscription: FREE_SUBSCRIPTION, locale: 'es' });
    expect(es.text('plan-hint').text()).toBe('No está a la venta ahora mismo');
  });

  it('a plan sold by the year only is not bought under «Monthly», and is under «Annual»', async () => {
    const monthly = await card({ plan: STANDARD, sold: ['year'], period: 'month', subscription: FREE_SUBSCRIPTION });
    expect(disabled(monthly.text('plan-upgrade'))).toBe(true);
    expect(monthly.text('plan-hint').text()).toBe('Only with annual billing');
    const annual = await card({ plan: STANDARD, sold: ['year'], period: 'year', subscription: FREE_SUBSCRIPTION });
    expect(disabled(annual.text('plan-upgrade'))).toBe(false);
    expect(annual.text('plan-hint').exists()).toBe(false);
  });

  it('a plan sold by the month only is not bought under «Annual», whatever its annual price says', async () => {
    const s = await card({ plan: STANDARD, sold: ['month'], period: 'year', subscription: FREE_SUBSCRIPTION, locale: 'es' });
    expect(disabled(s.text('plan-upgrade'))).toBe(true);
    expect(s.text('plan-hint').text()).toBe('Solo con pago mensual');
  });

  it('a business that pays is not offered to change to it', async () => {
    const s = await card({ plan: STANDARD, sold: [] });
    expect(s.text('plan-change').text()).toBe('Change to Standard');
    expect(disabled(s.text('plan-change'))).toBe(true);
    expect(s.text('plan-hint').text()).toBe('Not on sale right now');
    await s.text('plan-change').trigger('click');
    expect(s.wrapper.emitted('change')).toBeUndefined();
  });

  it('the plan it pays is not switched to a billing Stripe does not sell it with', async () => {
    const s = await card({ plan: STANDARD, sold: ['month'], period: 'year', subscription: subscription({ plan: 'standard' }) });
    expect(disabled(s.text('plan-switch'))).toBe(true);
    expect(s.text('plan-hint').text()).toBe('Only with monthly billing');
  });

  it('an unpaid invoice is still the first thing it says', async () => {
    const s = await card({ plan: STANDARD, sold: [], block: 'unpaid' });
    expect(s.text('plan-hint').text()).toBe('Pay the pending invoice first.');
  });
});
