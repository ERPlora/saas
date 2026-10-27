// The Store (`/dashboard/store/:tab`, round 17 §2.10; mockups `store.html`): the shell's page with its two sections in
// the footer tabbar, Plans · Modules, each at its own address, carrying the business it sells to
// (`?business=`). It sells, so it is the web's only (PLAN-SAAS §3.6 point 6, README §4): inside the apps
// and on the account surface — also through a deep link — it says «The store is not in the app» and how
// to buy from a browser, WITHOUT a link out, and loads nothing (no prices, no Stripe).
import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { flush, mountBilling } from '../__tests__/mount-billing';
import StoreShop from '../components/StoreShop.vue';
import StorePage from './StorePage.vue';

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

async function page(path = '/dashboard/store/plans?business=cafe', tab: 'plans' | 'modules' = 'plans', locale: 'en' | 'es' = 'en') {
  return mountBilling(StorePage, { path, locale, props: { tab }, stubs: { StoreShop: true } });
}

describe('StorePage', () => {
  it('is the shell page «Store» with Plans · Modules in the footer, each keeping the business', async () => {
    const s = await page();
    const frame = s.wrapper.findComponent(AppPage);
    expect(frame.props('title')).toBe('Store');
    expect(frame.props('tabsLabel')).toBe('Store sections');
    expect(frame.props('tabs')).toEqual([
      { id: 'plans', label: 'Plans', icon: 'ion:layers-outline', to: '/dashboard/store/plans?business=cafe', webOnly: true },
      { id: 'modules', label: 'Modules', icon: 'ion:apps-outline', to: '/dashboard/store/modules?business=cafe', webOnly: true },
    ]);
    expect(frame.props('tab')).toBe('plans');
  });

  it('hands the shop its section and the business of the address', async () => {
    const s = await page('/dashboard/store/modules?business=cafe', 'modules');
    expect(s.wrapper.findComponent(StoreShop).props()).toEqual({ tab: 'modules', businessId: 'cafe' });
  });

  it('a business picked in the shop goes into the address, so the sections and a reload keep it', async () => {
    const s = await page('/dashboard/store/plans');
    s.wrapper.findComponent(StoreShop).vm.$emit('update:businessId', 'bakery');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/dashboard/store/plans?business=bakery');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it does not sell: it says why, without a link out, and loads nothing', async (surface) => {
    applySurface(surface);
    const s = await page();
    expect(s.wrapper.findComponent(StoreShop).exists()).toBe(false);
    const notice = s.wrapper.find('[data-testid="store-in-app"]');
    if (surface === 'account') {
      // Already in the browser (the account the app opens): no «go to erplora.com in your browser» (audit 2 S-09).
      expect(notice.text()).toContain('Nothing is bought from here');
      expect(notice.text()).toContain('This account was opened from the app, and the app does not sell: plans and modules are not bought from here.');
      expect(notice.text()).not.toContain('browser');
    } else {
      expect(notice.text()).toContain('The store is not in the app');
      expect(notice.text()).toContain('To change your plan or add modules, go to erplora.com in your browser.');
    }
    expect(s.wrapper.find('[data-testid="store-in-app-businesses"]').attributes('routerlink')).toBe('/dashboard/businesses');
    expect(s.wrapper.findAll('[href]')).toEqual([]);
    expect(s.wrapper.html()).not.toMatch(/https?:|€/);
    expect(s.calls()).toEqual([]);
  });

  it('the account surface speaks Spanish too', async () => {
    applySurface('account');
    const s = await page('/dashboard/store/plans', 'plans', 'es');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain('Desde aquí no se compra');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain(
      'Esta cuenta se ha abierto desde la app, y la app no vende: desde aquí no se compran planes ni módulos.',
    );
  });

  it('speaks Spanish', async () => {
    applySurface('desktop');
    const s = await page('/dashboard/store/plans', 'plans', 'es');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Tienda');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain('La tienda no está en la app');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain('Para cambiar de plan o añadir módulos, entra en erplora.com desde el navegador.');
  });
});
