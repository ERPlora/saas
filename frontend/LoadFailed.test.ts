// The panel's one «could not load» state (audit 2026-10-14, R-04/R-08): a danger notice that says what could
// not be loaded and offers «Retry»; never an empty state, never a spinner for ever. Pages pass their own
// sentence; without one it speaks of the page.
import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import LoadFailed from './LoadFailed.vue';
import en from './locale/en.json';
import es from './locale/es.json';

function mountIt(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mount(LoadFailed, {
    props,
    attachTo: document.body,
    global: { plugins: [createShellI18n({ locale, messages: { en, es } })] },
  });
}

describe('LoadFailed', () => {
  it('says the page could not be loaded and offers «Retry»', () => {
    const wrapper = mountIt();
    expect(wrapper.text()).toContain("We couldn't load this page");
    expect(wrapper.text()).toContain('Check your connection and try again.');
    expect(wrapper.get('[data-testid="load-failed-retry"]').text()).toContain('Retry');
    expect(wrapper.find('.inline-feedback').attributes('data-tone')).toBe('danger');
  });

  it('speaks Spanish', () => {
    const wrapper = mountIt({}, 'es');
    expect(wrapper.text()).toContain('No hemos podido cargar esta página');
    expect(wrapper.text()).toContain('Comprueba la conexión y vuelve a intentarlo.');
    expect(wrapper.get('[data-testid="load-failed-retry"]').text()).toContain('Reintentar');
  });

  it('takes the page’s own heading and sentence, and its test hooks', () => {
    const wrapper = mountIt({
      heading: 'We could not load your businesses.',
      message: 'Maybe the connection dropped.',
      testid: 'launch-error',
      retryTestid: 'launch-retry',
    });
    expect(wrapper.get('[data-testid="launch-error"]').text()).toContain('We could not load your businesses.');
    expect(wrapper.text()).toContain('Maybe the connection dropped.');
    expect(wrapper.find('[data-testid="launch-retry"]').exists()).toBe(true);
  });

  it('a refusal for the role (403, `permission_denied`) says so, never «check your connection», and offers no «Retry» (audit 2 R-19)', () => {
    for (const error of [{ code: 'permission_denied', status: 0 }, { code: 'forbidden', status: 403 }]) {
      const wrapper = mountIt({ error, heading: 'We could not load this business', message: 'Maybe the connection dropped.' });
      expect(wrapper.text()).toContain('You do not have permission to see this');
      expect(wrapper.text()).toContain('Your role does not allow it. If you need it, ask the owner.');
      expect(wrapper.text()).not.toContain('connection');
      expect(wrapper.find('[data-testid="load-failed-retry"]').exists()).toBe(false);
    }
  });

  it('a page names what may not be seen; in Spanish too', () => {
    const wrapper = mountIt({ error: { code: 'permission_denied', status: 0 }, forbiddenHeading: 'No tienes permiso para gestionar este negocio' }, 'es');
    expect(wrapper.text()).toContain('No tienes permiso para gestionar este negocio');
    expect(wrapper.text()).toContain('Tu rol no lo permite. Si lo necesitas, pídeselo al propietario.');
    expect(mountIt({ error: { code: 'permission_denied', status: 0 } }, 'es').text()).toContain('No tienes permiso para ver esto');
  });

  it('any other failure keeps the connection hint and «Retry»', () => {
    const wrapper = mountIt({ error: { code: 'network_error', status: 0 } });
    expect(wrapper.text()).toContain('Check your connection and try again.');
    expect(wrapper.find('[data-testid="load-failed-retry"]').exists()).toBe(true);
  });

  it('emits «retry»', async () => {
    const wrapper = mountIt();
    await wrapper.get('[data-testid="load-failed-retry"]').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });
});
