// Account (`/account/:tab`, round 17: PLAN-SAAS §3.6 point 1; mockups `account.html`): Profile · Security ·
// Preferences · API keys in the footer tabbar, each at its own address, the top bar naming the section. Everything
// here shows on every surface (nothing is sold here); the account's bills are Billing, a section of the menu.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { fakeAllauth, ok } from '../__tests__/allauth-server';
import { flush, mountPanel } from '../__tests__/mount-panel';
import AccountPage from './AccountPage.vue';

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function open(tab: string, locale: 'en' | 'es' = 'en') {
  fakeAllauth({ 'GET /account/authenticators': ok([]), 'GET /account/providers': ok([]) });
  const s = await mountPanel(AccountPage, { props: { tab }, path: `/account/${tab}`, locale });
  await flush();
  return s;
}

const tabs = () =>
  [...document.querySelectorAll('[data-testid^="tab-"]')].map((el) => [el.getAttribute('data-testid'), el.textContent?.trim()]);

describe('AccountPage', () => {
  it('has four sections in the footer tabbar, each at its own address', async () => {
    await open('profile');
    expect(tabs()).toEqual([
      ['tab-profile', 'Profile'],
      ['tab-security', 'Security'],
      ['tab-preferences', 'Preferences'],
      ['tab-api-keys', 'API keys'],
    ]);
    expect(document.querySelector('ion-segment.tabbar')?.getAttribute('aria-label')).toBe('Account sections');
  });

  it('names the page and the section in the top bar', async () => {
    const s = await open('security');
    expect(s.wrapper.text()).toContain('Account');
    expect(s.wrapper.text()).toContain('Security');
  });

  it('paints the section of its address', async () => {
    expect((await open('profile')).q('profile-loading')).not.toBeNull();
    document.body.innerHTML = '';
    const security = await open('security');
    expect(security.q('security-loading')).not.toBeNull();
    expect(security.wrapper.text()).toContain('Active sessions');
    document.body.innerHTML = '';
    expect((await open('preferences')).q('preferences-loading')).not.toBeNull();
    document.body.innerHTML = '';
    expect((await open('api-keys')).wrapper.text()).toContain('API keys');
  });

  it.each([
    ['security', 'detail-fill', true],
    ['api-keys', 'detail-fill', true],
    ['profile', 'detail', false],
    ['preferences', 'detail', false],
  ] as const)('%s is `%s`: a list fills the space between the topbar and the tabbar (Ioan, 2026-10-14)', async (tab, layout, fills) => {
    const s = await open(tab);
    expect(s.wrapper.findComponent(AppPage).props('contentLayout')).toBe(layout);
    expect(s.wrapper.get('.account-stack').classes('panel-fill')).toBe(fills);
  });

  it('speaks Spanish', async () => {
    await open('profile', 'es');
    expect(tabs().map(([, label]) => label)).toEqual(['Perfil', 'Seguridad', 'Preferencias', 'Claves de API']);
  });
});
