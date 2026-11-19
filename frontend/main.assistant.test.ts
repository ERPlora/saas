import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
vi.mock('@erplora/ui/components', async (original) => (await import('./__tests__/main-doubles')).componentsDouble(original));
vi.mock('@erplora/ui/sdk', async (original) => (await import('./__tests__/main-doubles')).sdkDouble(original));

import { createShell } from '@erplora/ui/shell';
import { ApiError } from '@erplora/ui/sdk';
import { assistantConfig, type AssistantConfig, assistantMessages, configureAssistant, forgetAssistant } from '@erplora/ui/components';
import type { Component } from 'vue';

import AssistantBackground from '../assistant/frontend/components/AssistantBackground.vue';
import AssistantTopbar from '../assistant/frontend/components/AssistantTopbar.vue';
import { SAAS_ASSISTANT } from '../assistant/frontend/options';

import { assign, fakeShell, importBoot, main, ME, renderShellHtml, setUpMain, shellOptions } from './__tests__/main-boot';
import { sdk } from './__tests__/main-doubles';

setUpMain();

describe("the panel's assistant (ASSISTANT-F25)", () => {
  /** What an async component of the chrome loads (`defineAsyncComponent`). */
  async function loaded(component: Component | undefined): Promise<unknown> {
    const module = (await (component as { __asyncLoader: () => Promise<unknown> }).__asyncLoader()) as
      | { default?: unknown }
      | unknown;
    return (module as { default?: unknown }).default ?? module;
  }

  it("configures the shared chat as the panel's before the shell boots", async () => {
    configureAssistant(undefined);
    let configured: unknown;
    vi.mocked(createShell).mockImplementation(async () => {
      configured = assistantConfig();
      return { app: { mount: vi.fn() }, router: { isReady: () => Promise.resolve() } } as never;
    });
    await main.boot({});
    expect(configured).toBe(SAAS_ASSISTANT);
  });

  it("gives the chat the server's voice only when the page says erplora.com has one (spa-config.assistantSpeech)", async () => {
    const configuredWith = async (config: object) => {
      configureAssistant(undefined);
      renderShellHtml(ME, config);
      let configured: AssistantConfig | undefined;
      vi.mocked(createShell).mockImplementation(async () => {
        configured = assistantConfig();
        return { app: { mount: vi.fn() }, router: { isReady: () => Promise.resolve() } } as never;
      });
      await main.boot({});
      return configured;
    };

    expect((await configuredWith({ assistantSpeech: true }))?.speak).toBeTypeOf('function');
    // None: no choice of voice, and «Read aloud» never asks the server.
    expect((await configuredWith({ assistantSpeech: false }))?.speak).toBeUndefined();
    renderShellHtml();
  });

  it('puts its button at the end of the topbar and its panel beside the pane, each loaded on demand', async () => {
    fakeShell();
    await main.boot({});
    const { chrome } = shellOptions();
    expect(Object.keys(chrome ?? {}).sort()).toEqual(['background', 'topbar']);
    expect(await loaded(chrome?.topbar)).toBe(AssistantTopbar);
    expect(await loaded(chrome?.background)).toBe(AssistantBackground);
  });

  it("speaks with the chat's own words (`assistant.*`) and the panel's (`saas.assistant.*`), in en and es", () => {
    type Words = { assistant: { title: string }; saas: { assistant: { empty: string } } };
    const messages = importBoot.messages as Record<string, Words>;
    expect([messages.en.assistant.title, messages.es.assistant.title]).toEqual([
      assistantMessages.en.assistant.title,
      assistantMessages.es.assistant.title,
    ]);
    expect([messages.en.saas.assistant.empty, messages.es.saas.assistant.empty]).toEqual([
      'Ask me about your businesses, your invoices or your account.',
      'Pregúntame por tus negocios, tus facturas o tu cuenta.',
    ]);
  });

  it('under a spent allowance says where to keep asking, never to ask whoever runs the business for a plan', () => {
    // The account's 30 messages are no plan's (ASSISTANT-F26): the chat's «Ask whoever runs the business to upgrade
    // the plan» under «Upgrade plan», which nobody is offered here, would send the person after a plan that gives none.
    // The panel gives its own line (`spentNoteKey`), which the real catalogues say in en and es.
    const messages = importBoot.messages as Record<string, unknown>;
    const say = (language: string) =>
      SAAS_ASSISTANT.spentNoteKey!.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages[language]);
    expect([say('en'), say('es')]).toEqual([
      'Each business has its own assistant, with its own messages: open the business to keep asking there.',
      'Cada negocio tiene su propio asistente, con sus propios mensajes: abre el negocio para seguir preguntando allí.',
    ]);
  });

  it("forgets the tab's conversation once the session ended, before the launcher loads", async () => {
    vi.mocked(sdk.auth.logout).mockResolvedValue({ authenticated: false, flows: [] });
    assign.mockImplementation(() => expect(forgetAssistant).toHaveBeenCalledOnce());
    fakeShell();
    await main.boot({});
    await shellOptions().userMenu!.logout!();
    expect(forgetAssistant).toHaveBeenCalledOnce();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('keeps the conversation when the sign out fails: the person is still signed in', async () => {
    vi.mocked(sdk.auth.logout).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    fakeShell();
    await main.boot({});
    await expect(shellOptions().userMenu!.logout!()).rejects.toThrow('Network error');
    expect(forgetAssistant).not.toHaveBeenCalled();
  });
});
