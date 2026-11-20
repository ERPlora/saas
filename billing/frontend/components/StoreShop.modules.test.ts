// The Store's modules: the premium apps billing has on sale, a paying business adding one in its dialog, and
// cancelling or keeping one it pays, also once its app is off sale. A module is sold when its app is premium AND
// billing has it on sale. The dialogs have their own tests: here they are stubs, and what the shop hands them is
// checked.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { catalog, storeModule } from '../__tests__/fixtures';
import { apiError, flush } from '../__tests__/mount-billing';
import { setup, setUpStoreShop } from '../__tests__/store-shop';
import ProrationDialog from './ProrationDialog.vue';

beforeEach(() => {
  // The shop compares a module's `valid_until` with now (`apply`): the fixtures end on Oct 31, 2026, so the
  // clock stays before it. Only the date: the timers stay real (the harness has its own fake clock).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-20T10:00:00Z'));
});

setUpStoreShop();

describe('StoreShop', () => {
  it('Modules: the premium apps billing has on sale, named by the catalog and priced by billing', async () => {
    const s = await setup({ tab: 'modules' });
    expect(s.all('module-name').map((n) => n.text())).toEqual(['Bookings', 'Loyalty']);
    expect(s.el('module-booking').find('[data-testid="module-price"]').text()).toBe('€9.00/month + VAT');
    // Loyalty is cancelled but still works: it can be kept.
    expect(s.el('module-loyalty').find('[data-testid="module-keep"]').text()).toBe('Keep · no charge today');
  });

  it('the catalog’s names follow the language: they are asked again when it changes', async () => {
    const s = await setup({ tab: 'modules' });
    const before = s.calls().filter((c) => c.path === '/api/apps').length;
    s.i18n.global.locale.value = 'es';
    await flush();
    expect(s.calls().filter((c) => c.path === '/api/apps').length).toBe(before + 1);
  });

  it('with nothing on sale, it says so', async () => {
    // A business with no module: one it still has is shown although the catalog lists none.
    const none = catalog('bakery', { modules: [storeModule('booking', 900)] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) =>
        path === '/api/apps' ? Response.json({ apps: [] }) : path === '/api/billing/store' && query.hub_id === 'bakery' ? Response.json(none) : undefined,
    });
    expect(s.el('store-no-modules').text()).toContain('There are no modules on sale right now.');
  });

  it('a paying business adds a module in ITS dialog, and then it is «Activating…», never on sale twice', async () => {
    const s = await setup({ tab: 'modules' });
    await s.el('module-booking').find('[data-testid="module-add"]').trigger('click');
    const dialog = s.wrapper.findComponent(ProrationDialog);
    expect(dialog.props()).toMatchObject({
      open: true,
      business: { id: 'bakery', name: 'Panadería López' },
      item: { kind: 'module', slug: 'booking', name: 'Bookings', recurringCents: 900, interval: 'month' },
      renewal: '2026-10-31T12:00:00Z',
    });
    dialog.vm.$emit('done', {
      hub_id: 'bakery',
      plan: 'starter',
      billing_interval: 'month',
      status: 'active',
      cancel_at_period_end: false,
      current_period_end: '2026-10-31T12:00:00Z',
      trial_end: null,
      modules: [{ slug: 'booking', source: 'purchase', valid_until: null }, { slug: 'loyalty', source: 'purchase', valid_until: '2026-10-31T12:00:00Z' }],
    });
    await flush();
    expect(s.el('module-booking').find('[data-testid="module-activating"]').text()).toBe('Activating… in Panadería López');
    expect(s.el('module-booking').find('[data-testid="module-add"]').exists()).toBe(false);
  });

  it('«Keep · no charge today» keeps a cancelled module and says when it renews', async () => {
    const s = await setup({
      tab: 'modules',
      answer: ({ path }) =>
        path === '/api/billing/module/keep'
          ? Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [{ slug: 'loyalty', source: 'purchase', valid_until: null }] })
          : undefined,
    });
    await s.el('module-loyalty').find('[data-testid="module-keep"]').trigger('click');
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ path: '/api/billing/module/keep', body: { hub_id: 'bakery', module: 'loyalty' } });
    expect(toastSuccess).toHaveBeenCalledWith('Loyalty is kept: it renews on Oct 31, 2026');
    expect(s.el('module-loyalty').find('[data-testid="module-owned"]').exists()).toBe(true);
  });

  it('«Cancel module» confirms with the date it ends, cancels it, and it can be kept until then', async () => {
    const owned = catalog('bakery', { modules: [storeModule('booking', 900, { owned: true, source: 'purchase' })] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) => {
        if (path === '/api/billing/store' && query.hub_id === 'bakery') return Response.json(owned);
        if (path === '/api/billing/module/cancel')
          return Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [{ slug: 'booking', source: 'purchase', valid_until: '2026-10-31T12:00:00Z' }] });
        return undefined;
      },
    });
    await s.el('module-booking').find('[data-testid="module-cancel"]').trigger('click');
    await flush();
    const dialog = document.querySelector('[data-testid="store-cancel-module"]');
    expect(dialog?.textContent).toContain('Panadería López · Bookings');
    expect(dialog?.textContent).toContain('Bookings keeps working in Panadería López until Oct 31, 2026; then it turns off and is not charged again.');
    expect(dialog?.textContent).toContain('Nothing the business wrote with it is deleted.');
    expect(dialog?.textContent).toContain('Until then you can undo it with «Keep».');
    (document.querySelector('[data-testid="store-cancel-module-submit"]') as HTMLElement).click();
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ method: 'POST', path: '/api/billing/module/cancel', body: { hub_id: 'bakery', module: 'booking' } });
    expect(toastSuccess).toHaveBeenCalledWith('Bookings cancelled: it works until Oct 31, 2026');
    expect(s.el('module-booking').find('[data-testid="module-keep"]').exists()).toBe(true);
    expect(s.el('module-booking').find('[data-testid="module-cancel"]').exists()).toBe(false);
  });

  it('a refused cancellation stays in its dialog and says why', async () => {
    const owned = catalog('bakery', { modules: [storeModule('booking', 900, { owned: true, source: 'purchase' })] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) => {
        if (path === '/api/billing/store' && query.hub_id === 'bakery') return Response.json(owned);
        if (path === '/api/billing/module/cancel') return apiError(409, 'billing.plan_change_pending', 'Undo the scheduled plan change first.');
        return undefined;
      },
    });
    await s.el('module-booking').find('[data-testid="module-cancel"]').trigger('click');
    await flush();
    (document.querySelector('[data-testid="store-cancel-module-submit"]') as HTMLElement).click();
    await flush();
    expect(document.querySelector('[data-testid="store-cancel-module"]')?.textContent).toContain('Undo the scheduled plan change first.');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(s.el('module-booking').find('[data-testid="module-cancel"]').exists()).toBe(true);
  });

  it('a module off sale the business still pays is shown to cancel it, named by billing if the catalog retired its app', async () => {
    const retired = catalog('bakery', { modules: [storeModule('retired', 500, { owned: true, source: 'purchase', on_sale: false, name: 'Old reports' })] });
    const s = await setup({ tab: 'modules', answer: ({ path, query }) => (path === '/api/billing/store' && query.hub_id === 'bakery' ? Response.json(retired) : undefined) });
    expect(s.el('module-retired').find('[data-testid="module-name"]').text()).toBe('Old reports');
    expect(s.el('module-retired').find('[data-testid="module-off-sale"]').exists()).toBe(true);
    expect(s.el('module-retired').find('[data-testid="module-cancel"]').exists()).toBe(true);
  });
});
