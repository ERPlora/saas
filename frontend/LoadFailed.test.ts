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

  it('emits «retry»', async () => {
    const wrapper = mountIt();
    await wrapper.get('[data-testid="load-failed-retry"]').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });
});
