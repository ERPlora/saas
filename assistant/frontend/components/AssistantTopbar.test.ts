// ASSISTANT-F25: the panel's piece at the end of the topbar (`createShell({ chrome: { topbar } })`) is the shared chat's
// sparkles «Assistant» (BASE-G110 in the Hub): it opens and closes the panel, only to an account that may ask the
// assistant (`assistant.ask`).
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { flush, forgetTestAssistant, LENA, mountAssistant, testAssistant } from '../__tests__/mount-assistant';
import AssistantTopbar from './AssistantTopbar.vue';

/** Attached, `ion-button` moves its `aria-*` to the native button of its shadow root, as in a browser. */
const native = (element: Element, name: string) =>
  element.shadowRoot?.querySelector('button')?.getAttribute(name) ?? element.getAttribute(name);

let assistant: ReturnType<typeof testAssistant>['assistant'];

beforeEach(() => {
  ({ assistant } = testAssistant());
});

afterEach(() => {
  forgetTestAssistant();
  document.body.innerHTML = '';
});

describe('AssistantTopbar', () => {
  it('opens and closes the panel with the sparkles «Assistant», pressed while it is open', async () => {
    const { wrapper } = await mountAssistant(AssistantTopbar);
    const button = wrapper.get('[data-testid="assistant-button"]');
    expect(native(button.element, 'aria-label')).toBe('Assistant');
    expect(native(button.element, 'aria-pressed')).toBe('false');

    await button.trigger('click');
    await flush();

    expect(assistant.state.open).toBe(true);
    expect(native(wrapper.get('[data-testid="assistant-button"]').element, 'aria-pressed')).toBe('true');
    await wrapper.get('[data-testid="assistant-button"]').trigger('click');
    expect(assistant.state.open).toBe(false);
  });

  it('says «Asistente» in Spanish', async () => {
    const { wrapper } = await mountAssistant(AssistantTopbar, { locale: 'es' });
    expect(native(wrapper.get('[data-testid="assistant-button"]').element, 'aria-label')).toBe('Asistente');
  });

  it('is not there for an account that may not ask the assistant', async () => {
    const { wrapper } = await mountAssistant(AssistantTopbar, { session: { ...LENA, permissions: ['accounts.view'] } });
    expect(wrapper.find('[data-testid="assistant-button"]').exists()).toBe(false);
  });

  it('is not there without a session', async () => {
    const { wrapper } = await mountAssistant(AssistantTopbar, { session: null });
    expect(wrapper.find('[data-testid="assistant-button"]').exists()).toBe(false);
  });
});
