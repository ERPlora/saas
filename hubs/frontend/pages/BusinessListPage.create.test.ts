// «Create business» on the businesses page: the dialog (form → preparing → ready), or why another Free business is
// not possible; the new row appears «Preparing» through the live list, and the dialog follows the business until it
// is ready, paused for maintenance or refused by the Hub.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { enterView, flush } from '../__tests__/mount-hubs';
import { page, PREPARING, ROWS, row, setup, setUpBusinessListPage } from '../__tests__/business-list-page';

setUpBusinessListPage();

describe('BusinessListPage: «Create business»', () => {
  async function openCreate(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup({
      respond: (c) => (c.path === '/api/hubs/businesses' && c.method === 'POST' ? Response.json({ id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing' }) : undefined),
      ...extra,
    });
    await s.show(page(ROWS));
    await s.testid('businesses-add').trigger('click');
    await flush();
    return s;
  }

  async function submitDulce(s: Awaited<ReturnType<typeof openCreate>>): Promise<void> {
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
  }

  it('opens the dialog with the form, the dialog’s button creating', async () => {
    const s = await openCreate();
    expect(s.q('create-modal')?.getAttribute('aria-label')).toBe('Create business');
    expect(s.q('create-modal')?.textContent).toContain('What is your business called?');
    expect(s.q('create-modal-submit')?.textContent).toContain('Create my business');
  });

  describe('with the account’s Free business filling its quota', () => {
    const FULL = { free_business: { id: 'cafe', slug: 'cafe', name: 'Café Central' } };

    it('says so before the form, names the business and offers to change its plan in the Store', async () => {
      const s = await setup();
      await s.show(page(ROWS, FULL));
      await s.testid('businesses-add').trigger('click');
      await flush();
      expect(s.q('create-modal')?.getAttribute('aria-label')).toBe('Create business');
      // (booleans: a failing match on an element prints the whole Ionic DOM)
      expect(s.q('create-name') === null).toBe(true);
      expect(s.q('create-modal-submit') === null).toBe(true);
      expect(s.q('create-free-limit')?.textContent).toContain('You already have a free business');
      expect(s.q('create-free-limit')?.textContent).toContain(
        'Each account has one, and yours is Café Central. To create another business, move Café Central to a paid plan first.',
      );
      const store = s.q('create-free-limit-store')!;
      expect(store.textContent).toContain('Change the plan of Café Central');
      store.click();
      await flush();
      expect(s.router.currentRoute.value.fullPath).toBe('/dashboard/store/plans?business=cafe');
      expect(s.q('create-modal')?.querySelector('.ion-delegate-host') === null).toBe(true);
    });

    it('inside the apps it says where the plan is changed, without a link', async () => {
      applySurface('desktop');
      const s = await setup();
      await s.show(page(ROWS, FULL));
      await s.testid('businesses-add').trigger('click');
      await flush();
      expect(s.q('create-free-limit-store') === null).toBe(true);
      expect(s.q('create-free-limit')?.textContent).toContain('To change your plan or add modules, go to erplora.com in your browser.');
    });

    it('speaks Spanish', async () => {
      const s = await setup({ locale: 'es' });
      await s.show(page(ROWS, FULL));
      await s.testid('businesses-add').trigger('click');
      await flush();
      expect(s.q('create-free-limit')?.textContent).toContain('Ya tienes un negocio gratuito');
      expect(s.q('create-free-limit')?.textContent).toContain(
        'Cada cuenta tiene uno, y el tuyo es Café Central. Para crear otro negocio, pasa antes Café Central a un plan de pago.',
      );
      expect(s.q('create-free-limit-store')?.textContent).toContain('Cambiar el plan de Café Central');
    });
  });

  it('opens by itself from the launcher’s «Create another business» (?create=1), also when the page is shown again', async () => {
    const s = await setup({ path: '/dashboard/businesses?create=1' });
    await flush();
    expect(s.q('create-modal')).not.toBeNull();
    s.q('create-modal-cancel')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).toBeNull();
    await s.router.push('/dashboard/businesses?create=1');
    enterView(s.wrapper);
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('follows the new business on its own, also when the list does not show it (a search, another page)', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    s.q('create-modal-submit')!.click();
    await flush();
    expect(s.client.stream.subscriptions('hubs.business.get').map((sub) => sub.params)).toEqual([{ id: 'dulce' }]);
    // The focus moves to the step's own button.
    expect(focus.mock.contexts).toContain(s.q('create-modal-close-list'));
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'active', hub_error: null, can: { open: true } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Your business is ready');
    expect(focus.mock.contexts).toContain(s.q('create-modal-open'));
  });

  it('after creating: «Preparing», the new row «Preparing» in the list, then «ready» with «Open business»', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Preparing Pastelería Dulce');
    expect(s.q('create-modal')?.textContent).toContain('You can close this window: you will see it in your list as «Preparing».');
    await s.show(page([row('dulce', 'Pastelería Dulce', PREPARING), ...ROWS]), 2);
    expect(s.rows()[0].get('.status-pill').text()).toBe('Preparing');
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'active', hub_error: null, can: { open: true } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Your business is ready');
    expect(s.q('create-modal')?.textContent).toContain('Your address: dulce.localhost:8000');
    s.q('create-modal-open')!.click();
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/open')?.body).toEqual({ id: 'dulce', next: '/' });
  });

  it('maintenance reaches the dialog and the row without becoming an error', async () => {
    const maintenance = { frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' };
    const s = await openCreate();
    await submitDulce(s);
    await s.show(page([row('dulce', 'Pastelería Dulce', { ...PREPARING, maintenance }), ...ROWS]), 2);
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing', maintenance, hub_error: null, can: { open: false } });

    expect(s.q('create-modal')?.querySelector('[data-testid="preparing-maintenance"]')).not.toBeNull();
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('Preparing Pastelería Dulce');
    expect(s.rows()[0].get('.status-pill').text()).toBe('Paused for maintenance');
    expect(s.rows()[0].text()).toContain('Provisioning is paused for maintenance. It resumes automatically; you can check now.');
  });

  it('the dialog promises no seconds while the pause lasts, and says «a few seconds» again once it lifts', async () => {
    const maintenance = { frozen: true, reason: 'Aurora upgrade', since: '2026-11-09T20:00:00Z' };
    const business = { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing', hub_error: null, can: { open: false } };
    const s = await openCreate();
    await submitDulce(s);
    const lead = () => s.q('create-modal')?.querySelector('.create-lead')?.textContent?.trim();
    expect(lead()).toBe('It usually takes a few seconds.');
    await s.show(page([row('dulce', 'Pastelería Dulce', { ...PREPARING, maintenance }), ...ROWS]), 2);
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { ...business, maintenance }, 2);
    expect(s.q('create-modal')?.querySelector('[data-testid="preparing-maintenance"]')).not.toBeNull();
    expect(lead()).toBeUndefined();
    await s.result(s.net.lastStream(), 'hubs.business.get', { ...business, maintenance: null }, 3);
    expect(s.q('create-modal')?.querySelector('[data-testid="preparing-maintenance"]')).toBeNull();
    expect(lead()).toBe('It usually takes a few seconds.');
  });

  it('a preparation the Hub refused says so in the dialog', async () => {
    const s = await openCreate();
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = 'Pastelería Dulce';
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Pastelería Dulce' } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'hubs.business.get', { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000', status: 'preparing', hub_error: 'hub_refused', can: { open: false } });
    expect(s.q('create-modal')?.querySelector('ion-title')?.textContent).toContain('It could not be prepared');
    expect(s.q('create-modal')?.textContent).toContain('We saved Pastelería Dulce, but it could not be prepared.');
    s.q('create-modal-close-list')!.click();
    await flush();
    expect(s.q('create-modal')?.querySelector('.ion-delegate-host')).toBeNull();
  });
});
