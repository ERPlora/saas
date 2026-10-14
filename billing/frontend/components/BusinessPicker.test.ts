// «Which business is it for?» (mockups `store.html`): every business has its own plan and modules, so the
// Store sells to the one chosen here — an `ion-select` (never a native select), outlined in `md`, each
// option the business and its plan.
import { describe, expect, it } from 'vitest';

import { BAKERY, CAFE } from '../__tests__/fixtures';
import { ionProps, mountBilling, optionValue } from '../__tests__/mount-billing';
import BusinessPicker from './BusinessPicker.vue';

async function picker(locale: 'en' | 'es' = 'en') {
  const m = await mountBilling(BusinessPicker, { locale, props: { businesses: [BAKERY, CAFE], modelValue: 'bakery' } });
  return { ...m, select: m.wrapper.find('[data-testid="store-business"]') };
}

describe('BusinessPicker', () => {
  it('asks which business it is for, with each business and its plan', async () => {
    const s = await picker();
    expect(s.wrapper.text()).toContain('Which business is it for?');
    expect(s.wrapper.text()).toContain('Each business has its plan and its modules, with a single invoice a month.');
    expect(ionProps(s.select, 'mode', 'fill', 'label', 'interface', 'value')).toEqual({
      mode: 'md',
      fill: 'outline',
      label: 'Business',
      interface: 'popover',
      value: 'bakery',
    });
    const options = s.select.findAll('ion-select-option');
    expect(options.map((o) => [optionValue(o), o.text()])).toEqual([
      ['bakery', 'Panadería López · Starter'],
      ['cafe', 'Café Central · Free'],
    ]);
  });

  it('choosing another business says which', async () => {
    const s = await picker();
    s.select.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'cafe' } }));
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['cafe']]);
  });

  it('speaks Spanish', async () => {
    const s = await picker('es');
    expect(s.wrapper.text()).toContain('¿Para qué negocio?');
    expect(ionProps(s.select, 'label')).toEqual({ label: 'Negocio' });
  });
});
