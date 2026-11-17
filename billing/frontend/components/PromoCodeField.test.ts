// «Do you have a promo code?» in the Store: the code is checked with `billing.promo.check` before paying and the answer
// is the model the Store hands to the checkout. A code grants trial days or free months; an invalid one is said and
// never blocks the sale; a refusal of the server (too many tries) is said as it comes.
import { afterEach, describe, expect, it } from 'vitest';

import type { PromoCheckOut } from '../promo-types';
import { apiError, flush, ionProps, mountBilling } from '../__tests__/mount-billing';
import PromoCodeField from './PromoCodeField.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const SPRING: PromoCheckOut = { code: 'SPRING', valid: true, kind: 'trial_days', trial_days: 30, free_months: 0 };
const TESTERS: PromoCheckOut = { code: 'TESTERS', valid: true, kind: 'free_months', trial_days: 0, free_months: 6 };
const NOPE: PromoCheckOut = { code: 'NOPE', valid: false, kind: 'trial_days', trial_days: 0, free_months: 0 };

async function setup(answer: () => Response, locale: 'en' | 'es' = 'en') {
  const emitted: Array<PromoCheckOut | null> = [];
  const s = await mountBilling(PromoCodeField, {
    locale,
    // No `modelValue`: the field keeps its own answer, as when the Store has none yet.
    props: { 'onUpdate:modelValue': (value: PromoCheckOut | null) => emitted.push(value) },
    api: answer,
  });
  const el = (id: string) => s.wrapper.get(`[data-testid="${id}"]`);
  return { ...s, el, emitted };
}

async function type(s: Awaited<ReturnType<typeof setup>>, code: string): Promise<void> {
  await s.el('store-promo-toggle').trigger('click');
  s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: code } }));
  await s.el('store-promo-apply').trigger('click');
  await flush();
}

describe('PromoCodeField', () => {
  it('asks with Ionic’s controls: a clear button, an outlined md input and buttons with icons', async () => {
    const s = await setup(() => Response.json(SPRING));
    expect(s.el('store-promo-toggle').element.tagName).toBe('ION-BUTTON');
    expect((s.el('store-promo-toggle').find('ion-icon').element as unknown as { name?: string }).name).toBe('ticket-outline');
    await s.el('store-promo-toggle').trigger('click');
    expect(s.el('store-promo-code').element.tagName).toBe('ION-INPUT');
    expect(ionProps(s.el('store-promo-code'), 'mode', 'fill', 'label')).toEqual({ mode: 'md', fill: 'outline', label: 'Promo code' });
    expect(s.el('store-promo-apply').element.tagName).toBe('ION-BUTTON');
    expect(s.el('store-promo-apply').find('ion-icon').exists()).toBe(true);
  });

  it('a code of trial days says its days and is handed over', async () => {
    const s = await setup(() => Response.json(SPRING));
    await type(s, 'spring');
    expect(s.calls()).toEqual([{ method: 'GET', path: '/api/billing/promo-check', body: undefined, query: { code: 'spring' } }]);
    expect(s.el('store-promo-result').text()).toBe('Code SPRING: 30 days free before the first charge.');
    expect(s.emitted).toEqual([SPRING]);
  });

  it('a code of free months says how many, and that the regular price follows', async () => {
    const s = await setup(() => Response.json(TESTERS));
    await type(s, 'testers');
    expect(s.el('store-promo-result').text()).toBe('Code TESTERS: 6 months free, then the plan’s regular price.');
    expect(s.emitted).toEqual([TESTERS]);
  });

  it('says it in Spanish too', async () => {
    const s = await setup(() => Response.json(TESTERS), 'es');
    await type(s, 'testers');
    expect(s.el('store-promo-result').text()).toBe('Código TESTERS: 6 meses gratis; después, el precio normal del plan.');
  });

  it('an invalid code is said and never blocks the sale', async () => {
    const s = await setup(() => Response.json(NOPE));
    await type(s, 'nope');
    expect(s.el('store-promo-result').text()).toBe('This code is not valid, or it was already used.');
    expect(s.el('store-promo-result').classes()).toContain('is-invalid');
    expect(s.emitted).toEqual([NOPE]);
  });

  it('a refusal of the server is said as it comes, and the code applied before is not kept', async () => {
    const answers = [Response.json(SPRING), apiError(429, 'billing.promo_check_throttled', 'Too many promo codes tried in the last minute.')];
    const s = await setup(() => answers.shift() as Response);
    await type(s, 'spring');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'guess' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    expect(s.el('store-promo-result').text()).toBe('Too many promo codes tried in the last minute.');
    expect(s.el('store-promo-result').classes()).toContain('is-invalid');
    expect(s.emitted).toEqual([SPRING, null]);
  });

  it('the code can be removed', async () => {
    const s = await setup(() => Response.json(SPRING));
    await type(s, 'spring');
    await s.el('store-promo-remove').trigger('click');
    expect(s.emitted).toEqual([SPRING, null]);
    expect(ionProps(s.el('store-promo-code'), 'value')).toEqual({ value: '' });
  });
});
