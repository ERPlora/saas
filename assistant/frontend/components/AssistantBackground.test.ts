// ASSISTANT-F25: the panel's piece beside the pane (`createShell({ chrome: { background } })`, mounted once per
// signed-in person) is the shared chat's panel with the panel's own empty conversation: its sentence and three
// shortcuts, each asked at once. Its states as the person sees them: the empty conversation, the bubble «writing»
// while the answer has not come, a failure of the turn with its way out, what is left of the month's messages from 80 %
// (read with `base.assistant.usage`) and a spent month without «Upgrade plan» (an account has no plan for them).
import { createAssistant, installAssistant, type TurnFrame } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  flush,
  forgetTestAssistant,
  LENA,
  memoryStorage,
  mountAssistant,
  testAssistant,
  usage,
} from '../__tests__/mount-assistant';
import AssistantBackground from './AssistantBackground.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

let test_: ReturnType<typeof testAssistant>;

const done = (text = ''): TurnFrame => ({
  type: 'done',
  append: text ? [{ role: 'assistant', content: text }] : [],
  pending: [],
  continuation: null,
});

/** `base.assistant.usage` answers `answer`; any other call is a 404. */
function serving(answer: unknown, seen: string[] = []) {
  return ({ url }: { url: string }) => {
    seen.push(url);
    return url.startsWith('/api/assistant/usage')
      ? new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } })
      : new Response('{}', { status: 404 });
  };
}

beforeEach(() => {
  test_ = testAssistant(true);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(min-width: 768px)',
    addEventListener() {},
    removeEventListener() {},
  }));
});

afterEach(() => {
  forgetTestAssistant();
  document.body.innerHTML = '';
  document.documentElement.className = '';
  vi.unstubAllGlobals();
});

describe('AssistantBackground', () => {
  it("mounts the chat's panel, closed until the person opens it", async () => {
    test_ = testAssistant(false);
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });
    expect(wrapper.get('[data-testid="assistant-panel"]').attributes('data-open')).toBe('false');
  });

  it('opens docked beside the screen from 768 px, pushing it (the shell moves the pane)', async () => {
    await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });
    await flush();
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(true);
    expect(document.querySelector('[data-testid="assistant-veil"]')).toBeNull();
  });

  it('covers the screen over a veil on a phone', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });
    await flush();
    expect(wrapper.find('[data-testid="assistant-veil"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="assistant-panel"]').attributes('aria-modal')).toBe('true');
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(false);
  });

  it('is not there for an account that may not ask the assistant, even on a device that left it open', async () => {
    const { wrapper } = await mountAssistant(AssistantBackground, {
      session: { ...LENA, permissions: ['accounts.view'] },
      onApi: serving(usage(0)),
    });
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(false);
  });

  it("says the panel's sentence in the empty conversation, with its three shortcuts", async () => {
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });
    const empty = wrapper.get('[data-testid="assistant-empty"]');
    expect(empty.text()).toContain('Ask me about your businesses, your invoices or your account.');
    expect(wrapper.findAll('[data-testid="assistant-shortcut"]').map((s) => s.text())).toEqual([
      'Which businesses do I have?',
      'How much do I pay a month?',
      'How do I create a business?',
    ]);
  });

  it('says them in Spanish', async () => {
    const { wrapper } = await mountAssistant(AssistantBackground, { locale: 'es', onApi: serving(usage(0)) });
    expect(wrapper.get('[data-testid="assistant-empty"]').text()).toContain(
      'Pregúntame por tus negocios, tus facturas o tu cuenta.',
    );
    expect(wrapper.findAll('[data-testid="assistant-shortcut"]').map((s) => s.text())).toEqual([
      '¿Qué negocios tengo?',
      '¿Cuánto pago al mes?',
      '¿Cómo creo un negocio?',
    ]);
  });

  it('asks a shortcut at once, and paints its answer', async () => {
    test_.script.push([{ type: 'text', text: 'You have **Bar Lena**.' }, done('You have **Bar Lena**.')]);
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });

    await wrapper.findAll('[data-testid="assistant-shortcut"]')[0].trigger('click');
    await flush();

    expect(test_.posted[0].messages.at(-1)).toEqual({ role: 'user', content: 'Which businesses do I have?' });
    expect(wrapper.get('[data-testid="assistant-bubble-user"]').text()).toBe('Which businesses do I have?');
    expect(wrapper.get('[data-testid="assistant-bubble-assistant"]').text()).toContain('You have Bar Lena.');
  });

  it('shows the bubble «writing» while the answer has not come', async () => {
    installAssistant(
      createAssistant({
        storage: memoryStorage(),
        openStorage: Object.assign(memoryStorage(), { getItem: () => '1' }),
        post: () => new Promise(() => undefined),
      }),
    );
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });

    await wrapper.findAll('[data-testid="assistant-shortcut"]')[1].trigger('click');
    await flush();

    expect(wrapper.find('[data-testid="assistant-writing"]').exists()).toBe(true);
  });

  it('a turn that fails says so, with «Try again»', async () => {
    test_.script.push([{ type: 'error', code: 'assistant.unavailable', retriable: true }, done()]);
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(0)) });

    await wrapper.findAll('[data-testid="assistant-shortcut"]')[0].trigger('click');
    await flush();

    expect(wrapper.get('[data-testid="assistant-failure"]').text()).toContain(
      'The assistant is not available right now. Try again in a few minutes.',
    );
    expect(wrapper.find('[data-testid="assistant-retry"]').exists()).toBe(true);
  });

  it("from 80 % of the month says what is left, as base.assistant.usage counts it", async () => {
    const seen: string[] = [];
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(24), seen) });
    await flush();

    expect(seen.some((url) => url.startsWith('/api/assistant/usage'))).toBe(true);
    expect(wrapper.get('[data-testid="assistant-usage"]').text()).toBe(
      'You have 6 of 30 messages left this month. They renew on November 1.',
    );
  });

  it('says nothing of the allowance under 80 %', async () => {
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(23)) });
    await flush();
    expect(wrapper.find('[data-testid="assistant-usage"]').exists()).toBe(false);
  });

  it('a spent month says when the messages come back and where to keep asking, never «Upgrade plan»', async () => {
    test_.script.push([
      { type: 'error', code: 'assistant.quota_exceeded', used: 30, limit: 30, resets_at: '2026-11-01T00:00:00Z', demo: false },
      done(),
    ]);
    const { wrapper } = await mountAssistant(AssistantBackground, { onApi: serving(usage(30)) });
    await flush();
    expect(wrapper.get('[data-testid="assistant-usage"]').text()).toBe(
      'You have used all 30 messages of this month. They renew on November 1.',
    );

    await wrapper.findAll('[data-testid="assistant-shortcut"]')[0].trigger('click');
    await flush();

    const failure = wrapper.get('[data-testid="assistant-failure"]');
    expect(failure.text()).toContain("You have used all the assistant's messages of this month (30 of 30).");
    expect(failure.text()).toContain('They renew on November 1.');
    expect(failure.text()).toContain(
      'Each business has its own assistant, with its own messages: open the business to keep asking there.',
    );
    expect(failure.text()).not.toMatch(/upgrade|plan/i);
    expect(wrapper.find('[data-testid="assistant-upgrade"]').exists()).toBe(false);
  });

  it('and in Spanish', async () => {
    test_.script.push([
      { type: 'error', code: 'assistant.quota_exceeded', used: 30, limit: 30, resets_at: '2026-11-01T00:00:00Z', demo: false },
      done(),
    ]);
    const { wrapper } = await mountAssistant(AssistantBackground, { locale: 'es', onApi: serving(usage(30)) });

    await wrapper.findAll('[data-testid="assistant-shortcut"]')[0].trigger('click');
    await flush();

    const failure = wrapper.get('[data-testid="assistant-failure"]');
    expect(failure.text()).toContain('Has usado todos los mensajes del asistente de este mes (30 de 30).');
    expect(failure.text()).toContain('Cada negocio tiene su propio asistente');
    expect(failure.text()).not.toMatch(/mejorar|plan/i);
  });
});
