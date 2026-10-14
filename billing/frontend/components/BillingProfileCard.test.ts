// Billing → Payment details: the billing details of one payer (mockups `billing.html` «payment»; README §3 and
// §4): who the invoices of its businesses are made out to — name, tax ID, address, email — and which
// businesses it pays, read with `hubs.billing_profile.get` (through the first of them: one payer, one set of
// details) and edited in BillingProfileModal on every surface (fiscal data is not selling).
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));

import type { BillingProfileOut } from '../../../frontend/sdk-types';
import { apiError, describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import BillingProfileCard from './BillingProfileCard.vue';
import BillingProfileModal from './BillingProfileModal.vue';

afterEach(() => {
  applySurface('web');
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

async function setup(answer: (call: ReturnType<typeof describeCall>) => Response = () => Response.json(PROFILE), locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(BillingProfileCard, { locale, props: { businesses: BUSINESSES }, api: (call) => answer(describeCall(call)) });
  await flush();
  return { ...s, q: (id: string) => s.wrapper.find(`[data-testid="${id}"]`) };
}

describe('BillingProfileCard', () => {
  it('reads the details of the payer through its first business and says who the invoices go to', async () => {
    const s = await setup();
    expect(s.calls()).toEqual([{ method: 'GET', path: '/api/hubs/billing-profile', body: undefined, query: { hub_id: 'bakery' } }]);
    expect(s.q('profile-name').text()).toBe('Panadería López S.L.');
    expect(s.wrapper.findAll('.kv > div').map((row) => [row.get('dt').text(), row.get('dd').text()])).toEqual([
      ['Tax ID', 'B12345678'],
      ['Address', 'C/ Mayor 12, 28013 Madrid'],
      ['Email', 'facturas@panaderialopez.es'],
      ['Pays', 'Panadería López and Bar La Plaza'],
    ]);
  });

  it('«Edit details» opens the dialog with them; saved, the card shows the new ones', async () => {
    const s = await setup();
    await s.q('profile-edit').trigger('click');
    await flush();
    const modal = s.wrapper.findComponent(BillingProfileModal);
    expect(modal.props()).toMatchObject({ open: true, businesses: BUSINESSES, profile: PROFILE });
    modal.vm.$emit('saved', { ...PROFILE, billing_city: 'Getafe' });
    await flush();
    expect(s.wrapper.findAll('.kv dd')[1].text()).toBe('C/ Mayor 12, 28013 Getafe');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface the details are edited too: it is not selling', async (surface) => {
    applySurface(surface);
    const s = await setup();
    expect(s.q('profile-edit').exists()).toBe(true);
  });

  it('without details yet, it says they are asked on the first payment', async () => {
    const s = await setup(() => Response.json({ ...PROFILE, billing_name: '', tax_id: '', billing_address: '', billing_city: '', billing_postal_code: '', billing_country: '', billing_email: '' }));
    expect(s.q('profile-empty').text()).toBe('None yet: they are asked on the first payment, so the invoice is in your name or your company’s.');
    expect(s.q('profile-edit').exists()).toBe(true);
  });

  it('a failure says why and retries', async () => {
    let fail = true;
    const s = await setup(() => (fail ? apiError(503, 'unavailable', 'Try again in a moment.') : Response.json(PROFILE)));
    expect(s.q('profile-error').text()).toContain('Try again in a moment.');
    fail = false;
    await s.q('profile-retry').trigger('click');
    await flush();
    expect(s.q('profile-name').text()).toBe('Panadería López S.L.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(undefined, 'es');
    expect(s.wrapper.findAll('.kv dt').map((dt) => dt.text())).toEqual(['NIF', 'Dirección', 'Correo', 'Paga']);
    expect(s.wrapper.findAll('.kv dd')[3].text()).toBe('Panadería López y Bar La Plaza');
    expect(s.q('profile-edit').text()).toBe('Editar datos');
  });
});
