// The Store's «Cancel module» of a module the business bought: the confirmation says until when it works, that
// nothing is deleted and that it can be kept; confirmed, `billing.module.cancel`, the subscription it left to the
// Store and a toast with the date it ends. A refusal stays in the dialog.
// clock: data only — no code under test compares these dates with now.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import type { SaleModule } from '../store';
import { confirmDialogOf } from '../__tests__/confirm-dialog';
import { apiError, describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import CancelModuleDialog from './CancelModuleDialog.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

const BOOKINGS: SaleModule = {
  slug: 'booking',
  name: 'Bookings',
  summary: '',
  iconSvg: '',
  priceMonthlyCents: 900,
  priceAnnualCents: 9000,
  owned: true,
  source: 'purchase',
  validUntil: null,
  onSale: true,
};

const CANCELLED = {
  hub_id: 'bakery',
  plan: 'starter',
  billing_interval: 'month',
  status: 'active',
  cancel_at_period_end: false,
  current_period_end: '2026-10-31T12:00:00Z',
  trial_end: null,
  modules: [{ slug: 'booking', source: 'purchase', valid_until: '2026-10-28T12:00:00Z' }],
  scheduled_change: null,
};

type Answer = (call: ReturnType<typeof describeCall>) => Response;

async function setup(props: Record<string, unknown> = {}, api: Answer = () => Response.json(CANCELLED), locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(CancelModuleDialog, {
    locale,
    props: { module: BOOKINGS, business: { id: 'bakery', name: 'Panadería López' }, renewal: '2026-10-31T12:00:00Z', ...props },
    api: (call) => api(describeCall(call)),
  });
  await flush();
  const { dialog, dialogProp } = confirmDialogOf(s.wrapper);
  const confirm = async () => {
    s.q('store-cancel-module-submit')!.click();
    await flush();
  };
  return { ...s, dialog, dialogProp, confirm };
}

describe('CancelModuleDialog', () => {
  it('speaks of that module, its business and the date it ends', async () => {
    const s = await setup();
    expect(s.dialog().props()).toMatchObject({
      open: true,
      testid: 'store-cancel-module',
      title: 'Cancel the module',
      message: 'Panadería López · Bookings',
      confirmLabel: 'Cancel module',
      cancelLabel: 'Back',
      confirmIcon: 'ion:close-circle-outline',
      pending: false,
      error: null,
    });
    expect(s.dialogProp('consequences')).toEqual([
      {
        icon: 'ion:calendar-outline',
        text: 'Bookings keeps working in Panadería López until Oct 31, 2026; then it turns off and is not charged again.',
      },
      { icon: 'ion:folder-outline', text: 'Nothing the business wrote with it is deleted.' },
      { icon: 'ion:refresh-outline', text: 'Until then you can undo it with «Keep».' },
    ]);
  });

  it('without a renewal date it works until the end of the period', async () => {
    const s = await setup({ renewal: null });
    expect((s.dialogProp('consequences') as Array<{ text: string }>)[0].text).toBe(
      'Bookings keeps working in Panadería López until the end of the period; then it turns off and is not charged again.',
    );
  });

  it('closed while no module is asked', async () => {
    const s = await setup({ module: null });
    expect(s.dialogProp('open')).toBe(false);
    expect(s.dialogProp('message')).toBe('Panadería López · ');
  });

  it('confirmed, it cancels the module, hands the subscription to the Store, says until when and closes', async () => {
    const s = await setup();
    await s.confirm();
    expect(s.calls().at(-1)).toMatchObject({ method: 'POST', path: '/api/billing/module/cancel', body: { hub_id: 'bakery', module: 'booking' } });
    expect(s.wrapper.emitted('done')).toEqual([[CANCELLED]]);
    expect(toastSuccess).toHaveBeenCalledWith('Bookings cancelled: it works until Oct 28, 2026');
    expect(s.wrapper.emitted('update:module')).toEqual([[null]]);
  });

  it('a module the answer leaves without an end works until the end of the period it says', async () => {
    const s = await setup({}, () => Response.json({ ...CANCELLED, modules: [] }));
    await s.confirm();
    expect(toastSuccess).toHaveBeenCalledWith('Bookings cancelled: it works until Oct 31, 2026');
  });

  it('with no date at all, until the end of the period', async () => {
    const s = await setup({}, () => Response.json({ ...CANCELLED, modules: [], current_period_end: null }));
    await s.confirm();
    expect(toastSuccess).toHaveBeenCalledWith('Bookings cancelled: it works until the end of the period');
  });

  it('a refusal stays in the dialog and says why; asked again, the dialog starts clean', async () => {
    const s = await setup({}, () => apiError(409, 'billing.plan_change_pending', 'Undo the scheduled plan change first.'));
    await s.confirm();
    expect(s.dialogProp('error')).toEqual({ message: 'Undo the scheduled plan change first.', code: 'billing.plan_change_pending', status: 409 });
    expect(s.wrapper.emitted('done')).toBeUndefined();
    expect(s.wrapper.emitted('update:module')).toBeUndefined();
    expect(toastSuccess).not.toHaveBeenCalled();
    await s.wrapper.setProps({ module: null });
    await s.wrapper.setProps({ module: { ...BOOKINGS } });
    expect(s.dialogProp('error')).toBeNull();
  });

  it('«Back» closes it without cancelling', async () => {
    const s = await setup();
    s.dialog().vm.$emit('update:open', false);
    await flush();
    expect(s.wrapper.emitted('update:module')).toEqual([[null]]);
    expect(s.calls()).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, undefined, 'es');
    expect(s.dialog().props()).toMatchObject({ title: 'Cancelar el módulo', confirmLabel: 'Cancelar el módulo', cancelLabel: 'Volver' });
    expect((s.dialogProp('consequences') as Array<{ text: string }>).map((line) => line.text)).toEqual([
      'Bookings sigue funcionando en Panadería López hasta el 31 oct 2026; después se apaga y no se vuelve a cobrar.',
      'No se borra nada de lo que el negocio escribió con él.',
      'Hasta entonces puedes deshacerlo con «Mantener».',
    ]);
  });
});
