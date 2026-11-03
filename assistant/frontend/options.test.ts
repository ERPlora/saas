// The panel's configuration of the shared assistant (`options.ts`, plan 2026-10-30-asistente-saas §6): the same chat as
// the Hub's, wired to the SaaS's own routes and operations (base/api.py), the account's words for its writes and its
// screens, its dictation (ASSISTANT-F21), its reading aloud in a server voice (ASSISTANT-F22) and nobody upgrading (an
// account has no plan for its 30 messages).
// clock: data only — no code under test compares these dates with now.
import { createShellSession, type SessionMe } from '@erplora/ui/shell';
import { ApiError, type LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import en from '../../frontend/locale/en.json';
import es from '../../frontend/locale/es.json';
import { actionKey, ASK, PANEL_SCREENS, panelScreenKey, placeKey, SAAS_ASSISTANT, speak } from './options';

type Catalogue = { [key: string]: string | Catalogue };

const ME: SessionMe = {
  user: { id: 'u1', label: 'Lena' },
  permissions: [ASK],
  menu: [],
  apps: [],
  language: 'en',
};

function sessionWith(permissions: string[]) {
  return createShellSession(ref<SessionMe | undefined>({ ...ME, permissions }), ref('live'));
}

function clientAnswering(answer: unknown) {
  const call = vi.fn().mockResolvedValue(answer);
  return { client: { api: { call } } as unknown as LiveClient, call };
}

/** The string at the dotted `key` of `catalogue`, or `undefined`. */
function lookup(catalogue: Catalogue, key: string): string | undefined {
  let node: string | Catalogue | undefined = catalogue;
  for (const part of key.split('.')) {
    if (node === undefined || typeof node === 'string' || !Object.hasOwn(node, part)) return undefined;
    node = node[part];
  }
  return typeof node === 'string' ? node : undefined;
}

/** Every operation named under `card.operations` (`<app>.<entity>.<action>`). */
function namedOperations(): string[] {
  const apps = en.saas.assistant.card.operations as unknown as Record<string, Record<string, Record<string, string>>>;
  return Object.entries(apps).flatMap(([app, entities]) =>
    Object.entries(entities).flatMap(([entity, actions]) => Object.keys(actions).map((action) => `${app}.${entity}.${action}`)),
  );
}

describe('SAAS_ASSISTANT', () => {
  it("posts a turn to base.assistant.turn's route; where nothing is sold the session says so, never the URL", () => {
    // `?surface=account` would stick to the session (base/surface.py) and hide the Store from the web too.
    expect(SAAS_ASSISTANT.turnUrl).toBe('/api/assistant/turn');
  });

  it("reads the account's allowance with base.assistant.usage", async () => {
    const usage = { used: 3, limit: 30, resets_at: '2026-11-01T00:00:00Z', demo: false };
    const { client, call } = clientAnswering(usage);

    await expect(SAAS_ASSISTANT.usage!(client)).resolves.toEqual(usage);
    expect(call).toHaveBeenCalledWith('base.assistant.usage', {});
  });

  it('sends the report of an answer with base.assistant.report', async () => {
    const { client, call } = clientAnswering({ sent: true, duplicate: false });
    const report = { message_id: 'm1', reason: 'incorrect' as const, comment: '', question: 'Q', answer: 'A' };

    await SAAS_ASSISTANT.report!(client, report);

    expect(call).toHaveBeenCalledWith('base.assistant.report', report);
  });

  it('dictates with base.assistant.transcribe: the microphone shows because the host transcribes', async () => {
    const words = { text: 'Dos negocios', language: 'es' };
    const { client, call } = clientAnswering(words);
    const clip = { audio: 'GkXfow==', mime_type: 'audio/webm', language: 'es' };

    expect(await SAAS_ASSISTANT.transcribe!(client, clip)).toEqual(words);
    expect(call).toHaveBeenCalledWith('base.assistant.transcribe', clip);
  });

  it('shows the button to whoever may ask the assistant (assistant.ask), to nobody else', () => {
    expect(SAAS_ASSISTANT.canUse!(sessionWith([ASK]))).toBe(true);
    expect(SAAS_ASSISTANT.canUse!(sessionWith(['accounts.view', 'hubs.view']))).toBe(false);
    expect(SAAS_ASSISTANT.canUse!(createShellSession(ref(undefined), ref('loading')))).toBe(false);
  });

  it("offers nobody «Upgrade plan»: the account's messages are not a plan's, not even a superuser's", () => {
    expect(SAAS_ASSISTANT.canUpgrade!(sessionWith(['*']))).toBe(false);
    expect(SAAS_ASSISTANT.planUrl).toBeUndefined();
  });

  it('under a spent allowance sends to the business, never to a plan nobody offers (ui#49)', () => {
    expect(SAAS_ASSISTANT.spentNoteKey).toBe('saas.assistant.errors.quotaSpentAccount');
    for (const catalogue of [en, es]) {
      const line = lookup(catalogue as unknown as Catalogue, SAAS_ASSISTANT.spentNoteKey!);
      expect(line).toBeTruthy();
      expect(line).not.toMatch(/plan/i);
    }
  });

  it("asks nobody's approval: the panel has no manager's approval (the Hub's)", () => {
    expect(SAAS_ASSISTANT.approval).toBeUndefined();
    expect(SAAS_ASSISTANT.elevationToken).toBeUndefined();
  });

  it("names writes and screens with the panel's own keys", () => {
    expect(SAAS_ASSISTANT.verbKey).toBe(actionKey);
    expect(SAAS_ASSISTANT.placeKey).toBe(placeKey);
    expect(SAAS_ASSISTANT.screenKey).toBe(panelScreenKey);
  });
});

describe('actionKey', () => {
  it('gives every write the catalogue names its own verb, said in en and es', () => {
    const named = namedOperations();
    expect(named).toContain('hubs.business.create');
    for (const operation of named) {
      const key = actionKey(operation);
      expect(key, operation).toBe(`saas.assistant.card.operations.${operation}`);
      expect(lookup(en as unknown as Catalogue, key), `${key} (en)`).toBeTruthy();
      expect(lookup(es as unknown as Catalogue, key), `${key} (es)`).toBeTruthy();
    }
  });

  it("falls back to its action's verb for a write the catalogue does not name, then to «Do this»", () => {
    expect(actionKey('hubs.widget.create')).toBe('saas.assistant.card.actions.create');
    expect(lookup(en as unknown as Catalogue, actionKey('hubs.widget.create'))).toBe('Create');
    expect(actionKey('hubs.widget.frobnicate')).toBe('assistant.card.other');
    // Never a key of an object's own prototype.
    expect(actionKey('hubs.business.constructor')).toBe('assistant.card.other');
    expect(actionKey('toString')).toBe('assistant.card.other');
  });

  it('says the three cancels apart: an invitation, a plan and an offer of the ownership', () => {
    const verbs = ['hubs.member.cancel', 'billing.plan.cancel', 'hubs.ownership.cancel'].map((op) =>
      lookup(en as unknown as Catalogue, actionKey(op)),
    );
    expect(verbs).toEqual(['Cancel invitation', 'Cancel plan', 'Withdraw the offer']);
  });
});

describe('placeKey', () => {
  it("names the panel's screen a receipt names by the server's key (base/assistant.py SCREEN_OF_APP)", () => {
    for (const screen of ['businesses', 'store', 'billing', 'account']) {
      const key = placeKey(screen);
      expect(key).toBe(`saas.assistant.screens.${screen}`);
      expect(lookup(en as unknown as Catalogue, key!)).toBeTruthy();
      expect(lookup(es as unknown as Catalogue, key!)).toBeTruthy();
    }
  });

  it('names none it does not know, nor none at all', () => {
    expect(placeKey(undefined)).toBeNull();
    expect(placeKey('')).toBeNull();
    expect(placeKey('settings')).toBeNull();
    expect(placeKey('constructor')).toBeNull();
  });
});

describe('panelScreenKey', () => {
  it("names the menu's four screens by their path (base/navigation.py)", () => {
    expect(PANEL_SCREENS).toEqual({
      '/dashboard/businesses': 'businesses',
      '/dashboard/store': 'store',
      '/dashboard/billing': 'billing',
      '/dashboard/account': 'account',
    });
    expect(panelScreenKey('/dashboard/billing')).toBe('saas.assistant.screens.billing');
    expect(lookup(es as unknown as Catalogue, panelScreenKey('/dashboard/billing')!)).toBe('Facturación');
  });

  it('leaves any other path to the menu', () => {
    expect(panelScreenKey('/dashboard/businesses/x')).toBeNull();
    expect(panelScreenKey('/')).toBeNull();
    expect(panelScreenKey('/settings')).toBeNull();
  });
});

/** A page of the panel: its SPA config and its CSRF cookie, as Django serves it. */
function panelPage(): Document {
  const doc = document.implementation.createHTMLDocument('panel');
  const config = doc.createElement('script');
  config.id = 'spa-config';
  config.type = 'application/json';
  config.textContent = JSON.stringify({ csrfCookieName: 'csrftoken', csrfHeader: 'X-CSRFToken', lang: 'es', deviceIdStorageKey: 'erplora.device' });
  doc.body.append(config);
  Object.defineProperty(doc, 'cookie', { value: 'csrftoken=tok123' });
  return doc;
}

const SPEECH = { text: 'Tienes dos negocios.', language: 'es' as const, voice: 'es-ES-Tristan:DragonHDLatestNeural' };

describe('speak (ASSISTANT-F22): the mp3 of an answer in a server voice, base.assistant.speak', () => {
  it('posts the text, its language and its voice to the route with the CSRF token, and gives back the mp3', async () => {
    const mp3 = new Blob(['ID3 spoken words'], { type: 'audio/mpeg' });
    const fetch = vi.fn().mockResolvedValue(new Response(mp3, { status: 200, headers: { 'Content-Type': 'audio/mpeg' } }));

    const audio = await speak(SPEECH, { fetch, doc: panelPage() });

    expect(audio).toBeInstanceOf(Blob);
    expect(await audio.text()).toBe('ID3 spoken words');
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('/api/assistant/speak');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(init.headers).toMatchObject({ 'X-CSRFToken': 'tok123', 'Content-Type': 'application/json', Accept: 'audio/mpeg' });
    expect(JSON.parse(init.body)).toEqual(SPEECH);
  });

  it("passes the chat's signal to the request, so a reading stopped before its audio arrives is aborted", async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValue(new Response(new Blob(['ID3']), { status: 200, headers: { 'Content-Type': 'audio/mpeg' } }));

    await speak({ ...SPEECH, signal: controller.signal }, { fetch, doc: panelPage() });

    const [, init] = fetch.mock.calls[0];
    expect(init.signal).toBe(controller.signal);
    expect(JSON.parse(init.body)).toEqual(SPEECH);
  });

  it('rejects with the envelope of a refusal, so the chat reads in the device voice', async () => {
    const refusal = { error: { code: 'assistant.speech_unavailable', message: 'Reading aloud is not available right now.' } };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(refusal), { status: 503, headers: { 'Content-Type': 'application/json' } }));

    const spoken = speak(SPEECH, { fetch, doc: panelPage() });

    await expect(spoken).rejects.toBeInstanceOf(ApiError);
    await expect(spoken).rejects.toMatchObject({ status: 503, code: 'assistant.speech_unavailable', message: 'Reading aloud is not available right now.' });
  });

  it('rejects when there is no network at all', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(speak(SPEECH, { fetch, doc: panelPage() })).rejects.toMatchObject({ status: 0, code: 'network_error' });
  });

  it('is what the panel gives the chat as its server voice', () => {
    expect(SAAS_ASSISTANT.speak).toBeTypeOf('function');
  });
});

