// «Cancel plan» of a row of Subscriptions (mockups `billing.html` «modal-cancel»; README §3b; UX-AUDIT-4 W-F1,
// X-08, X-31; PLAN-SAAS §3.3): the confirmation speaks of THAT business and its own dates — until when it
// stays on its plan and that it then goes to Free without another charge, which of its modules turn off
// (nothing is deleted), what Free covers against the people it has now (`hubs.business.get` seats), that an
// unpaid invoice stays pending, and that «Keep the plan» undoes it until then. Confirmed, `billing.plan.cancel`
// and a toast that says until when.
import { ConfirmDialog } from '@erplora/ui/components';
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

import { subscriptionRow, unpaidRow } from '../__tests__/billing-fixtures';
import { FREE } from '../__tests__/fixtures';
import { apiError, describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import CancelPlanDialog from './CancelPlanDialog.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

const BAKERY_ROW = subscriptionRow('bakery', 'Panadería López', {
  modules: [
    { slug: 'booking', interval: 'month', price_cents: 900, source: 'purchase', valid_until: null },
    { slug: 'loyalty', interval: 'month', price_cents: 600, source: 'purchase', valid_until: null },
  ],
  next_invoice: { date: '2026-11-01T10:00:00Z', total_cents: 4718, currency: 'EUR' },
});
const NAMES = { booking: 'Bookings', loyalty: 'Loyalty' };

function seats(used: number) {
  return Response.json({ id: 'x', seats: { used, limit: null } });
}

async function setup(props: Record<string, unknown> = {}, api: (call: ReturnType<typeof describeCall>) => Response = () => seats(5), locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(CancelPlanDialog, {
    locale,
    props: { open: true, row: BAKERY_ROW, moduleNames: NAMES, freePlan: FREE, unpaid: null, ...props },
    api: (call) => api(describeCall(call)),
  });
  await flush();
  const dialog = () => s.wrapper.findComponent(ConfirmDialog as unknown as Component);
  const dialogProp = (name: string) => (dialog().props() as Record<string, unknown>)[name];
  const lines = () => (dialogProp('consequences') as Array<{ text: string }>).map((line) => line.text);
  return { ...s, dialog, dialogProp, lines };
}

describe('CancelPlanDialog', () => {
  it('speaks of that business, its plan and its own dates', async () => {
    const s = await setup();
    expect(s.dialog().props()).toMatchObject({
      open: true,
      title: 'Cancel the plan',
      message: 'Panadería López · Starter',
      confirmLabel: 'Cancel plan',
      cancelLabel: 'Back',
      tone: 'danger',
      testid: 'cancel-plan',
    });
    expect(s.calls()).toEqual([{ method: 'GET', path: '/api/hubs/businesses/detail', body: undefined, query: { id: 'bakery' } }]);
    expect(s.lines()).toEqual([
      'It stays on Starter until Nov 1, 2026; then it goes to Free and is not charged again.',
      'Bookings and Loyalty turn off on Nov 1, 2026. Nothing is deleted: back on a paid plan, they are as they were.',
      'Free covers 3 users and 1 device at a time. Panadería López has 5 people: before Nov 1, 2026 you choose who stays.',
      'Until then you can undo it with «Keep the plan».',
    ]);
  });

  it('with few people, nothing changes for them; without modules, none turns off', async () => {
    const row = subscriptionRow('plaza', 'Bar La Plaza');
    const s = await setup({ row }, () => seats(2));
    expect(s.dialogProp('message')).toBe('Bar La Plaza · Starter');
    expect(s.lines()).toEqual([
      'It stays on Starter until Nov 1, 2026; then it goes to Free and is not charged again.',
      'Free covers 3 users and 1 device at a time. Bar La Plaza has 2 people, so nothing changes for them.',
      'Until then you can undo it with «Keep the plan».',
    ]);
  });

  it('an unpaid invoice stays pending: cancelling does not cancel it', async () => {
    const row = subscriptionRow('plaza', 'Bar La Plaza', { unpaid_invoice_id: 'i9' });
    const s = await setup({ row, unpaid: unpaidRow('i9') }, () => seats(2));
    expect(s.lines()).toContain('The unpaid invoice of Oct 10, 2026 (€36.29) stays pending: cancelling does not cancel it.');
  });

  it('the people are not known: Free’s limits alone', async () => {
    const s = await setup({}, () => apiError(503, 'unavailable', 'Try again.'));
    expect(s.lines()[2]).toBe('Free covers 3 users and 1 device at a time.');
  });

  it('confirmed, it cancels the plan of that business and says until when', async () => {
    const s = await setup({}, (call) =>
      call.path === '/api/billing/plan/cancel'
        ? Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: true, current_period_end: '2026-11-01T10:00:00Z', trial_end: null, modules: [], scheduled_change: null })
        : seats(5),
    );
    s.dialog().vm.$emit('confirm');
    await flush();
    expect(s.calls().filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/api/billing/plan/cancel', body: { hub_id: 'bakery' }, query: {} }]);
    expect(toastSuccess).toHaveBeenCalledWith('Plan cancelled: Panadería López stays on Starter until Nov 1, 2026');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(s.wrapper.emitted('done')).toHaveLength(1);
  });

  it('a refusal stays in the dialog, with the server’s words', async () => {
    const s = await setup({}, (call) =>
      call.path === '/api/billing/plan/cancel' ? apiError(409, 'billing.payer_required', 'Only the account that pays this business can change its plan.') : seats(5),
    );
    s.dialog().vm.$emit('confirm');
    await flush();
    expect(s.dialogProp('error')).toMatchObject({ message: 'Only the account that pays this business can change its plan.', code: 'billing.payer_required' });
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ moduleNames: { booking: 'Reservas', loyalty: 'Fidelización' } }, () => seats(5), 'es');
    expect(s.dialogProp('title')).toBe('Cancelar el plan');
    expect(s.lines()).toEqual([
      'Sigue en Starter hasta el 1 nov 2026; después pasa a Gratis y no se vuelve a cobrar.',
      'Reservas y Fidelización se desactivan el 1 nov 2026. No se borra nada: si vuelves a un plan de pago, quedan como estaban.',
      'En Gratis caben 3 usuarios y 1 dispositivo a la vez. Panadería López tiene 5 personas: antes del 1 nov 2026 eliges quién sigue.',
      'Hasta entonces puedes deshacerlo con «Mantener el plan».',
    ]);
  });
});
