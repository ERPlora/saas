// A module of the Store (mockups `store.html` «Módulos»; round 17 §2.10; UX-AUDIT-4 W-F4/X-14): name,
// summary and icon from the app catalog, net price at the business's billing, and what the business can do:
//   - «Add · €9.00/month» (one dialog per module, with its own proration, or the checkout on Free);
//   - just bought: «Activating… in <business>», never on sale twice;
//   - owned: «You have it» (or «Included in your plan»), disabled;
//   - cancelled but still working: until when, and «Keep · no charge today»;
//   - with an unpaid invoice nothing that charges, with the reason.
import { describe, expect, it } from 'vitest';

import { mountBilling } from '../__tests__/mount-billing';
import type { Block, SaleModule } from '../store';
import ModuleCard from './ModuleCard.vue';

const BOOKING: SaleModule = {
  slug: 'booking',
  name: 'Bookings',
  summary: 'Calendar, online bookings and reminders.',
  iconSvg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="M0 0h1"/></svg>',
  priceMonthlyCents: 900,
  priceAnnualCents: 9000,
  owned: false,
  source: null,
  validUntil: null,
};
const nb = (text: string) => text.replace(/ €/g, ' €');

async function card(module: Partial<SaleModule> = {}, extra: { interval?: 'month' | 'year'; block?: Block | null; activating?: boolean; renewal?: string | null; locale?: 'en' | 'es' } = {}) {
  const { locale, ...props } = extra;
  const m = await mountBilling(ModuleCard, {
    locale,
    props: { module: { ...BOOKING, ...module }, interval: 'month', block: null, activating: false, businessName: 'Panadería López', renewal: '2026-11-01T12:00:00Z', ...props },
  });
  const el = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const disabled = (id: string) => (el(id).element as unknown as { disabled: boolean }).disabled;
  return { ...m, el, disabled };
}

describe('ModuleCard', () => {
  it('paints the catalog’s name, summary and icon and billing’s net price', async () => {
    const s = await card();
    expect(s.el('module-name').text()).toBe('Bookings');
    expect(s.wrapper.text()).toContain('Calendar, online bookings and reminders.');
    expect((s.wrapper.find('ion-icon').element as unknown as { icon?: string }).icon).toContain('data:image/svg+xml;utf8,<svg');
    expect(s.el('module-price').text()).toBe('€9.00/month + VAT');
  });

  it('adds it at the business’s billing, saying the price on the button', async () => {
    const s = await card();
    expect(s.el('module-add').text()).toBe('Add · €9.00/month');
    await s.el('module-add').trigger('click');
    expect(s.wrapper.emitted('add')).toHaveLength(1);
    const annual = await card({}, { interval: 'year', locale: 'es' });
    expect(annual.el('module-price').text()).toBe(nb('90,00 €/año + IVA'));
    expect(annual.el('module-add').text()).toBe(nb('Añadir · 90,00 €/año'));
  });

  it('a module without an annual price is not sold to an annual business', async () => {
    const s = await card({ priceAnnualCents: 0 }, { interval: 'year' });
    expect(s.disabled('module-add')).toBe(true);
    expect(s.el('module-hint').text()).toBe('Only with monthly billing');
  });

  it('owned: «You have it», never on sale twice', async () => {
    const s = await card({ owned: true, source: 'purchase' });
    expect(s.el('module-owned').text()).toBe('You have it');
    expect(s.disabled('module-owned')).toBe(true);
    expect(s.el('module-add').exists()).toBe(false);
  });

  it('included in the plan says so', async () => {
    const s = await card({ owned: true, source: 'plan' });
    expect(s.el('module-included').text()).toBe('Included in your plan');
  });

  it('just bought: «Activating…» in the business, and not on sale again', async () => {
    const s = await card({ owned: true, source: 'purchase' }, { activating: true });
    expect(s.el('module-activating').text()).toBe('Activating… in Panadería López');
    expect(s.disabled('module-owned')).toBe(true);
    expect(s.el('module-add').exists()).toBe(false);
  });

  it('cancelled but still working: until when, and keeping it charges nothing today', async () => {
    const s = await card({ owned: true, source: 'purchase', validUntil: '2026-10-31T12:00:00Z' });
    expect(s.el('module-cancelled').text()).toBe(
      'You have it until Oct 31, 2026 (cancelled). «Keep» undoes the cancellation; nothing is charged until Nov 1, 2026.',
    );
    expect(s.el('module-keep').text()).toBe('Keep · no charge today');
    await s.el('module-keep').trigger('click');
    expect(s.wrapper.emitted('keep')).toHaveLength(1);
  });

  it('with an unpaid invoice nothing charges, and it says why', async () => {
    const s = await card({}, { block: 'card_declined' });
    expect(s.disabled('module-add')).toBe(true);
    expect(s.el('module-hint').text()).toBe('Pay the pending invoice first.');
    expect(s.el('module-hint').element.tagName).toBe('ION-NOTE');
    expect(s.el('module-add').attributes('aria-describedby')).toBe(s.el('module-hint').attributes('id'));
    const keep = await card({ owned: true, validUntil: '2026-10-31T12:00:00Z' }, { block: 'unpaid' });
    expect(keep.disabled('module-keep')).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await card({ owned: true }, { locale: 'es' });
    expect(s.el('module-owned').text()).toBe('Ya lo tienes');
  });
});
