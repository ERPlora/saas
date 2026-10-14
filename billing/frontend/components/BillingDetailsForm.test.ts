// Who ERPlora invoices (PLAN-SAAS §3.1; mockups `store.html` checkout note): asked once, before the first
// payment, in the checkout dialog — legal name, tax ID (checked in VIES by the server), address, city,
// postal code and country, or «use the business’s name and country». Ionic fields, outlined in `md`, each
// with the server's message under it (`fieldErrors`, a 422). Country is an `ion-select`, never native.
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { ionProps, mountBilling, optionValue } from '../__tests__/mount-billing';
import BillingDetailsForm, { type BillingDetailsDraft } from './BillingDetailsForm.vue';

const EMPTY: BillingDetailsDraft = {
  billing_name: '',
  tax_id: '',
  billing_address: '',
  billing_city: '',
  billing_postal_code: '',
  billing_country: '',
  billing_email: '',
  same_as_business: false,
};

async function setup(draft: Partial<BillingDetailsDraft> = {}, fieldErrors: Record<string, string> = {}, locale: 'en' | 'es' = 'en') {
  const model = ref<BillingDetailsDraft>({ ...EMPTY, ...draft });
  const Host = {
    render: () =>
      h(BillingDetailsForm, {
        modelValue: model.value,
        'onUpdate:modelValue': (value: BillingDetailsDraft) => (model.value = value),
        fieldErrors,
      }),
  };
  const m = await mountBilling(Host, { locale });
  const field = (id: string) => m.wrapper.find(`[data-testid="details-${id}"]`);
  const fire = (id: string, event: string, detail: unknown) => field(id).element.dispatchEvent(new CustomEvent(event, { detail }));
  return { ...m, model, field, fire };
}

describe('BillingDetailsForm', () => {
  it('asks the legal name, tax ID, address, city, postal code, country and an invoice email', async () => {
    const s = await setup();
    expect(s.wrapper.text()).toContain('Who do we invoice? We ask it once, before the first payment.');
    const labels = ['name', 'tax-id', 'address', 'city', 'postal-code', 'email'].map((id) => ionProps(s.field(id), 'mode', 'fill', 'label'));
    expect(labels).toEqual([
      { mode: 'md', fill: 'outline', label: 'Legal name' },
      { mode: 'md', fill: 'outline', label: 'Tax ID (optional)' },
      { mode: 'md', fill: 'outline', label: 'Address' },
      { mode: 'md', fill: 'outline', label: 'City' },
      { mode: 'md', fill: 'outline', label: 'Postal code' },
      { mode: 'md', fill: 'outline', label: 'Invoice email (optional)' },
    ]);
    expect(ionProps(s.field('country'), 'mode', 'fill', 'label', 'interface')).toEqual({ mode: 'md', fill: 'outline', label: 'Country', interface: 'popover' });
    const countries = s.field('country').findAll('ion-select-option').map(optionValue);
    expect(countries).toHaveLength(27);
    expect(countries).toContain('ES');
  });

  it('writes what is typed into the draft', async () => {
    const s = await setup();
    s.fire('name', 'ionInput', { value: 'Panadería López SL' });
    s.fire('postal-code', 'ionInput', { value: '28001' });
    s.fire('country', 'ionChange', { value: 'ES' });
    expect(s.model.value).toMatchObject({ billing_name: 'Panadería López SL', billing_postal_code: '28001', billing_country: 'ES' });
  });

  it('«use the business’s name and country» leaves those two to the business', async () => {
    const s = await setup();
    s.fire('same', 'ionChange', { checked: true });
    await s.wrapper.vm.$nextTick();
    expect(s.model.value.same_as_business).toBe(true);
    expect(s.field('name').exists()).toBe(false);
    expect(s.field('country').exists()).toBe(false);
    expect(s.field('postal-code').exists()).toBe(true);
  });

  it('puts the server’s message under its field', async () => {
    const s = await setup({}, { tax_id: 'Enter a valid tax ID for the country of the payer.' });
    expect(ionProps(s.field('tax-id'), 'errorText')).toEqual({ errorText: 'Enter a valid tax ID for the country of the payer.' });
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, {}, 'es');
    expect(ionProps(s.field('name'), 'label')).toEqual({ label: 'Razón social' });
  });
});
