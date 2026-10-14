// «Edit details» of the billing details (mockups `billing.html` «modal-profile», «profile-invalid»; README §3b
// and §4; PLAN-SAAS §3.1): the Store's BillingDetailsForm in a FormModal — legal name, tax ID, address, city,
// postal code, country and invoice email, or «use the business’s name and country» (of which business, when it
// pays several). The tax ID is checked in VIES as it is typed (`billing.vat_check.run`, after a pause): the
// verdict says what the invoice will do, and a malformed one is the field's error. Saved with
// `hubs.billing_profile.update`: a 422 puts each message under its field. It is not selling: every surface.
import { FormModal } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import type { BillingProfileOut } from '../../../frontend/sdk-types';
import { apiError, describeCall, flush, mountBilling, optionValue } from '../__tests__/mount-billing';
import BillingDetailsForm from './BillingDetailsForm.vue';
import BillingProfileModal from './BillingProfileModal.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

const PROFILE: BillingProfileOut = {
  hub_id: 'bakery',
  paid_by_another_account: false,
  billing_name: 'Panadería López S.L.',
  tax_id: 'B12345678',
  billing_address: 'C/ Mayor 12',
  billing_city: 'Madrid',
  billing_postal_code: '28013',
  billing_country: 'ES',
  billing_email: 'facturas@panaderialopez.es',
  same_as_business: false,
};
const BUSINESSES = [
  { id: 'bakery', name: 'Panadería López' },
  { id: 'plaza', name: 'Bar La Plaza' },
];
const verdict = (status: string, extra: Record<string, unknown> = {}) =>
  Response.json({ vat_number: 'X', status, valid: status === 'verified', name: '', address: '', consultation_number: '', checked_at: null, is_current: true, reverse_charge: status === 'verified', manual_override: false, ...extra });

type Answer = (call: ReturnType<typeof describeCall>) => Response;

async function setup(answer: Answer = () => verdict('national'), props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(BillingProfileModal, {
    locale,
    props: { open: true, businesses: BUSINESSES, profile: PROFILE, ...props },
    api: (call) => answer(describeCall(call)),
  });
  await flush();
  const modal = () => s.wrapper.findComponent(FormModal as unknown as Component);
  const modalProp = (name: string) => (modal().props() as Record<string, unknown>)[name];
  const form = () => s.wrapper.findComponent(BillingDetailsForm);
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const type = async (field: string, value: string, event = 'ionInput') => {
    q(field)?.dispatchEvent(new CustomEvent(event, { detail: event === 'ionInput' ? { value } : { value, checked: value === 'true' } }));
    await flush();
  };
  const checks = () => s.calls().filter((call) => call.path === '/api/billing/vat-check');
  return { ...s, modal, modalProp, form, q, type, checks };
}

describe('BillingProfileModal', () => {
  it('edits the billing details in a dialog, with the form of the Store filled with them', async () => {
    const s = await setup();
    expect(s.modal().props()).toMatchObject({ open: true, title: 'Billing details', submitLabel: 'Save details', testid: 'billing-profile' });
    expect(s.form().props('modelValue')).toEqual({
      billing_name: 'Panadería López S.L.',
      tax_id: 'B12345678',
      billing_address: 'C/ Mayor 12',
      billing_city: 'Madrid',
      billing_postal_code: '28013',
      billing_country: 'ES',
      billing_email: 'facturas@panaderialopez.es',
      same_as_business: false,
    });
    expect(s.q('billing-profile-note')?.textContent?.trim()).toBe(
      'They apply to the next invoices of the businesses you pay; the ones already issued do not change. With a tax ID of another EU country we check it in VIES.',
    );
  });

  it('checks the tax ID it has in VIES when it opens, and says the verdict', async () => {
    const s = await setup(() => verdict('national'));
    expect(s.checks()).toEqual([{ method: 'POST', path: '/api/billing/vat-check', body: { vat_number: 'B12345678', country: 'ES' }, query: {} }]);
    expect(s.q('vies-status')?.textContent?.trim()).toBe('Valid tax ID.');
  });

  it('checks a typed tax ID after a pause, once, and says what the invoice will do', async () => {
    const s = await setup((call) => ((call.body as { vat_number?: string } | undefined)?.vat_number === 'DE812871812' ? verdict('verified', { name: 'ACME GMBH' }) : verdict('national')));
    await s.type('details-tax-id', 'DE81287');
    await s.type('details-tax-id', 'DE812871812');
    expect(s.checks()).toHaveLength(1);
    expect(s.q('vies-status')?.textContent?.trim()).toBe('Checking in VIES…');
    await s.clock.advance(800);
    expect(s.checks().map((call) => call.body)).toEqual([
      { vat_number: 'B12345678', country: 'ES' },
      { vat_number: 'DE812871812', country: 'ES' },
    ]);
    expect(s.q('vies-status')?.textContent?.trim()).toBe('Checked in VIES: ACME GMBH. The invoice goes without VAT (reverse charge).');
  });

  it.each([
    ['invalid', 'VIES does not know this number: the invoice will carry VAT.'],
    ['unavailable', 'VIES does not answer right now: we check it again when invoicing.'],
    ['outside_vies', 'A UK number: it is not checked in VIES.'],
  ])('a %s verdict says what it means for the invoice', async (status, sentence) => {
    const s = await setup(() => verdict(status));
    expect(s.q('vies-status')?.textContent?.trim()).toBe(sentence);
  });

  it('a malformed tax ID is the field’s error', async () => {
    const s = await setup(() => apiError(422, 'invalid_payload', 'Invalid payload', { vat_number: 'Write the VAT number with its two-letter country prefix, e.g. DE123456789.' }));
    expect(s.form().props('fieldErrors')).toEqual({ tax_id: 'Write the VAT number with its two-letter country prefix, e.g. DE123456789.' });
    expect(s.q('vies-status')).toBeNull();
  });

  it('a short or empty tax ID is not asked to VIES', async () => {
    const s = await setup(() => verdict('national'), { profile: { ...PROFILE, tax_id: '' } });
    expect(s.checks()).toEqual([]);
    await s.type('details-tax-id', 'B12');
    await s.clock.advance(800);
    expect(s.checks()).toEqual([]);
  });

  it('saves them for the business it pays, and says so', async () => {
    const s = await setup((call) => (call.path === '/api/hubs/billing-profile' ? Response.json({ ...PROFILE, billing_city: 'Getafe' }) : verdict('national')));
    await s.type('details-city', 'Getafe');
    s.modal().vm.$emit('submit');
    await flush();
    expect(s.calls().filter((call) => call.method === 'POST' && call.path === '/api/hubs/billing-profile')).toEqual([
      {
        method: 'POST',
        path: '/api/hubs/billing-profile',
        query: {},
        body: {
          hub_id: 'bakery',
          billing_name: 'Panadería López S.L.',
          tax_id: 'B12345678',
          billing_address: 'C/ Mayor 12',
          billing_city: 'Getafe',
          billing_postal_code: '28013',
          billing_country: 'ES',
          billing_email: 'facturas@panaderialopez.es',
          same_as_business: false,
        },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Billing details saved');
    expect(s.wrapper.emitted('saved')).toEqual([[{ ...PROFILE, billing_city: 'Getafe' }]]);
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('«use the business’s name and country»: of which business, when it pays several', async () => {
    const s = await setup((call) => (call.path === '/api/hubs/billing-profile' ? Response.json(PROFILE) : verdict('national')));
    expect(s.q('billing-profile-business')).toBeNull();
    await s.type('details-same', 'true', 'ionChange');
    const select = s.wrapper.find('[data-testid="billing-profile-business"]');
    expect(select.findAll('ion-select-option').map((option) => [optionValue(option), option.text()])).toEqual([
      ['bakery', 'Panadería López'],
      ['plaza', 'Bar La Plaza'],
    ]);
    select.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'plaza' } }));
    await flush();
    s.modal().vm.$emit('submit');
    await flush();
    const saved = s.calls().find((call) => call.path === '/api/hubs/billing-profile');
    expect(saved?.body).toMatchObject({ hub_id: 'plaza', same_as_business: true });
  });

  it('a refusal stays in the dialog, each message under its field', async () => {
    const s = await setup((call) =>
      call.path === '/api/hubs/billing-profile'
        ? apiError(422, 'invalid_payload', 'Invalid payload', { billing_postal_code: 'A Spanish postal code has five digits, e.g. 28001.' })
        : verdict('national'),
    );
    s.modal().vm.$emit('submit');
    await flush();
    expect(s.modalProp('error')).toMatchObject({ code: 'invalid_payload' });
    expect(s.form().props('fieldErrors')).toEqual({ billing_postal_code: 'A Spanish postal code has five digits, e.g. 28001.' });
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup(() => verdict('national'), {}, 'es');
    expect(s.modalProp('title')).toBe('Datos de facturación');
    expect(s.modalProp('submitLabel')).toBe('Guardar datos');
    expect(s.q('vies-status')?.textContent?.trim()).toBe('NIF válido.');
  });
});
