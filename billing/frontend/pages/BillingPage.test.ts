// Billing (`/billing/:tab`; round 17, PLAN-SAAS §3.6 points 1, 6, 7 and 11; mockups `billing.html`): the shell's
// page with its three sections in the footer tabbar — Invoices · Subscriptions · Payment details — each at its
// own address. A composition surface: on top, what waits for a payment (BillingNotices) and, on Invoices, what
// this section is in one line (V-30); below, the section. Billing is not selling: it shows on every surface,
// to look at invoices and subscriptions and edit the fiscal data (paying and changing plan are web only,
// inside each section).
import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { mountBilling } from '../__tests__/mount-billing';
import BillingNotices from '../components/BillingNotices.vue';
import InvoicesTab from '../components/InvoicesTab.vue';
import PaymentTab from '../components/PaymentTab.vue';
import SubscriptionsTab from '../components/SubscriptionsTab.vue';
import BillingPage from './BillingPage.vue';

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

const STUBS = { BillingNotices: true, InvoicesTab: true, SubscriptionsTab: true, PaymentTab: true };

async function page(tab: 'invoices' | 'subscriptions' | 'payment' = 'invoices', locale: 'en' | 'es' = 'en') {
  return mountBilling(BillingPage, { path: `/billing/${tab}`, locale, props: { tab }, stubs: STUBS });
}

describe('BillingPage', () => {
  it('is the shell page «Billing» with Invoices · Subscriptions · Payment details in the footer', async () => {
    const s = await page();
    const frame = s.wrapper.findComponent(AppPage);
    expect(frame.props()).toMatchObject({ title: 'Billing', tabsLabel: 'Billing sections', contentLayout: 'detail-fill' });
    expect(frame.props('tabs')).toEqual([
      { id: 'invoices', label: 'Invoices', icon: 'ion:receipt-outline', to: '/billing/invoices' },
      { id: 'subscriptions', label: 'Subscriptions', icon: 'ion:sync-outline', to: '/billing/subscriptions' },
      { id: 'payment', label: 'Payment details', icon: 'ion:card-outline', to: '/billing/payment' },
    ]);
  });

  it.each([
    ['invoices', 'detail-fill', true],
    ['subscriptions', 'detail-fill', true],
    ['payment', 'detail', false],
  ] as const)('on %s the page is `%s`: a list fills the space between the topbar and the tabbar (Ioan, 2026-10-14)', async (tab, layout, fills) => {
    const s = await page(tab);
    expect(s.wrapper.findComponent(AppPage).props('contentLayout')).toBe(layout);
    expect(s.wrapper.get('.billing-stack').classes('panel-fill')).toBe(fills);
  });

  it('on Invoices: what this section is, what waits for a payment, and the invoices', async () => {
    const s = await page('invoices');
    expect(s.wrapper.get('[data-testid="billing-lead"]').text()).toBe(
      'What you pay ERPlora for all your businesses. The invoices of your sales are inside each business.',
    );
    expect(s.wrapper.findComponent(BillingNotices).props('tab')).toBe('invoices');
    expect(s.wrapper.findComponent(InvoicesTab).exists()).toBe(true);
    expect(s.wrapper.findComponent(SubscriptionsTab).exists()).toBe(false);
  });

  it.each([
    ['subscriptions', SubscriptionsTab],
    ['payment', PaymentTab],
  ] as const)('on %s: the notices in one line and that section, without the lead', async (tab, section) => {
    const s = await page(tab);
    expect(s.wrapper.find('[data-testid="billing-lead"]').exists()).toBe(false);
    expect(s.wrapper.findComponent(BillingNotices).props('tab')).toBe(tab);
    expect(s.wrapper.findComponent(section as never).exists()).toBe(true);
    expect(s.wrapper.findComponent(InvoicesTab).exists()).toBe(false);
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it is there, every section too', async (surface) => {
    applySurface(surface);
    const s = await page('subscriptions');
    expect(s.wrapper.findComponent(AppPage).props('tabs')).toHaveLength(3);
    expect(s.wrapper.findComponent(SubscriptionsTab).exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await page('invoices', 'es');
    const frame = s.wrapper.findComponent(AppPage);
    expect(frame.props('title')).toBe('Facturación');
    expect((frame.props('tabs') as Array<{ label: string }>).map((tab) => tab.label)).toEqual(['Facturas', 'Suscripciones', 'Datos de pago']);
    expect(s.wrapper.get('[data-testid="billing-lead"]').text()).toBe(
      'Lo que pagas a ERPlora por todos tus negocios. Las facturas de tus ventas están dentro de cada negocio.',
    );
  });
});
