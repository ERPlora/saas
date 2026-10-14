// The Store (`/store/:tab`, round 17 §2.10; mockups `store.html`): the shell's page with its two sections in
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

async function page(path = '/store/plans?business=cafe', tab: 'plans' | 'modules' = 'plans', locale: 'en' | 'es' = 'en') {
  return mountBilling(StorePage, { path, locale, props: { tab }, stubs: { StoreShop: true } });
}

describe('StorePage', () => {
  it('is the shell page «Store» with Plans · Modules in the footer, each keeping the business', async () => {
    const s = await page();
    const frame = s.wrapper.findComponent(AppPage);
    expect(frame.props('title')).toBe('Store');
    expect(frame.props('tabsLabel')).toBe('Store sections');
    expect(frame.props('tabs')).toEqual([
      { id: 'plans', label: 'Plans', icon: 'ion:layers-outline', to: '/store/plans?business=cafe', webOnly: true },
      { id: 'modules', label: 'Modules', icon: 'ion:apps-outline', to: '/store/modules?business=cafe', webOnly: true },
    ]);
    expect(frame.props('tab')).toBe('plans');
  });

  it('hands the shop its section and the business of the address', async () => {
    const s = await page('/store/modules?business=cafe', 'modules');
    expect(s.wrapper.findComponent(StoreShop).props()).toEqual({ tab: 'modules', businessId: 'cafe' });
  });

  it('a business picked in the shop goes into the address, so the sections and a reload keep it', async () => {
    const s = await page('/store/plans');
    s.wrapper.findComponent(StoreShop).vm.$emit('update:businessId', 'bakery');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/store/plans?business=bakery');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it does not sell: it says how, without a link out, and loads nothing', async (surface) => {
    applySurface(surface);
    const s = await page();
    expect(s.wrapper.findComponent(StoreShop).exists()).toBe(false);
    const notice = s.wrapper.find('[data-testid="store-in-app"]');
    expect(notice.text()).toContain('The store is not in the app');
    expect(notice.text()).toContain('To change your plan or add modules, go to erplora.com in your browser.');
    expect(s.wrapper.find('[data-testid="store-in-app-businesses"]').attributes('routerlink')).toBe('/businesses');
    expect(s.wrapper.findAll('[href]')).toEqual([]);
    expect(s.wrapper.html()).not.toMatch(/https?:|€/);
    expect(s.calls()).toEqual([]);
  });

  it('speaks Spanish', async () => {
    applySurface('desktop');
    const s = await page('/store/plans', 'plans', 'es');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Tienda');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain('La tienda no está en la app');
    expect(s.wrapper.find('[data-testid="store-in-app"]').text()).toContain('Para cambiar de plan o añadir módulos, entra en erplora.com desde el navegador.');
  });
});
