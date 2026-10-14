// Billing → Payment details (mockups `billing.html` «payment», «empty», «loading», «error»; README §4): per
// payer of the account (`billing.payment_method.get`, asked to Stripe when the tab opens, not live), its card
// (PaymentMethodCard) next to its billing details (BillingProfileCard). Without any payment yet, what is asked
// on the first one. Loading and failing say so, with «Retry».
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));

import { paymentMethod, paymentMethods } from '../__tests__/billing-fixtures';
import { apiError, describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import BillingProfileCard from './BillingProfileCard.vue';
import PaymentMethodCard from './PaymentMethodCard.vue';
import PaymentTab from './PaymentTab.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

type Answer = (call: ReturnType<typeof describeCall>) => Response | Promise<Response>;

async function setup(answer: Answer, locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(PaymentTab, { locale, api: (call) => answer(describeCall(call)) });
  return { ...s, q: (id: string) => s.wrapper.find(`[data-testid="${id}"]`) };
}

const PROFILE = Response.json({ hub_id: 'bakery', paid_by_another_account: false, billing_name: 'X', tax_id: '', billing_address: '', billing_city: '', billing_postal_code: '', billing_country: '', billing_email: '', same_as_business: false });

describe('PaymentTab', () => {
  it('asks for the payment methods of the account and shows each card next to its billing details', async () => {
    const other = paymentMethod({ businesses: [{ id: 'norte', name: 'Bar Norte' }], card: null });
    const s = await setup((call) => (call.path === '/api/billing/payment-method' ? Response.json(paymentMethods([paymentMethod(), other])) : PROFILE.clone()));
    await flush();
    expect(s.calls()[0]).toEqual({ method: 'GET', path: '/api/billing/payment-method', body: undefined, query: {} });
    expect(s.wrapper.findAllComponents(PaymentMethodCard).map((card) => card.props('method').businesses[0].name)).toEqual(['Panadería López', 'Bar Norte']);
    expect(s.wrapper.findAllComponents(BillingProfileCard).map((card) => card.props('businesses')[0].id)).toEqual(['bakery', 'norte']);
  });

  it('says it is loading meanwhile', async () => {
    let answer!: (response: Response) => void;
    const s = await setup(() => new Promise((done) => (answer = done)));
    expect(s.q('payment-loading').attributes('aria-busy')).toBe('true');
    answer(Response.json(paymentMethods([])));
    await flush();
    expect(s.q('payment-loading').exists()).toBe(false);
  });

  it('without any payment yet, it says what the first one asks for', async () => {
    const s = await setup(() => Response.json(paymentMethods([])));
    await flush();
    expect(s.q('payment-method-empty').text()).toContain('None yet: it is asked on the first payment of a plan or a module.');
    expect(s.q('payment-profile-empty').text()).toContain('None yet: they are asked on the first payment, so the invoice is in your name or your company’s.');
  });

  it('a failure says it, and «Retry» asks again', async () => {
    let fail = true;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const s = await setup((call) =>
      call.path === '/api/billing/payment-method' ? (fail ? apiError(503, 'unavailable', 'Down.') : Response.json(paymentMethods([]))) : PROFILE.clone(),
    );
    await flush();
    expect(s.q('payment-error').text()).toContain('We could not load your payment details');
    expect(s.q('payment-error').text()).toContain('Try again in a few seconds.');
    fail = false;
    await s.q('payment-retry').trigger('click');
    await flush();
    expect(s.q('payment-error').exists()).toBe(false);
    expect(s.q('payment-method-empty').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(() => Response.json(paymentMethods([])), 'es');
    await flush();
    expect(s.q('payment-method-empty').text()).toContain('Aún no hay ninguno: se pide en el primer pago de un plan o un módulo.');
    expect(s.q('payment-method-empty').text()).toContain('Método de pago');
  });
});
