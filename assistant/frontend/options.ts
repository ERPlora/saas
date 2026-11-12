// The panel's configuration of the shared assistant (`@erplora/ui/components`: the Hub's same chat, with erplora.com's
// own tools): `configureAssistant(panelAssistant(doc))` when the SPA
// boots (frontend/main.ts), and `SAAS_ASSISTANT` in the tests that mount its pieces.
// - A turn goes to `base.assistant.turn`'s route (base/api.py); the account's allowance and the report of an answer
//   through base's operations. Where nothing is sold (the installed app's account surface) the session says so
//   (base/surface.py): the route carries no `?surface=`, which would stick to the session and hide the Store from the
//   web too.
// - Whoever may ask the assistant sees its button (`assistant.ask`, every account's); nobody upgrades a plan from it:
//   the account's 30 messages a month are no plan's. Its microphone goes to `base.assistant.transcribe`:
//   the Hub's same dictation, counted in the account's month. «Read aloud» reads in the device's voice;
//   only when erplora.com has a voice of its own (`spa-config.assistantSpeech`, base/spa.py) does the chat ask the
//   server for each reading (`speak`: `base.assistant.speak`), falling back to the device's when it
//   fails. Without it (none today) `speak` is absent: no trip to the server per reading
//   (`panelAssistant`). No approvals: the panel has no
//   manager's approval (the Hub's).
// - The panel's words (`saas.assistant.*`, frontend/locale): the verb of each write the assistant may run, by its
//   operation (`card.operations.<app>.<entity>.<action>`, one per write: guardrail base/tests/
//   test_assistant_panel_words.py), else by its action (`card.actions.<action>`), else the chat's «Do this»; and the
//   menu's four screens (`screens.<key>`), by the server's key (base/assistant.py `SCREEN_OF_APP`) or by their path.
// - Under a spent allowance, where the Hub says to ask whoever runs the business to upgrade the plan, the panel says
//   that each business has its own assistant (`spentNoteKey`: `saas.assistant.errors.quotaSpentAccount`): the
//   account's messages are no plan's, and nobody is offered «Upgrade plan» here.
import type { AssistantConfig, AssistantSpeech } from '@erplora/ui/components';
import { createHeaderProvider, fetchFile, readSpaConfig } from '@erplora/ui/sdk';

import { ACCOUNT, BILLING, BUSINESSES, STORE } from '../../accounts/frontend/paths';
import { OPERATION_ROUTES } from '../../frontend/generated/operation-routes';
import en from '../../frontend/locale/en.json';

/** Who may ask the panel's assistant (assistant/apps.py, the `account` role's). */
export const ASK = 'assistant.ask';

/** The verb of each action a card or a receipt names. */
const ACTIONS: Readonly<Record<string, string>> = en.saas.assistant.card.actions;

/** The verb of each write the assistant may run, by app → entity → action. */
const OPERATIONS: Readonly<Record<string, Readonly<Record<string, Readonly<Record<string, string>>>>>> =
  en.saas.assistant.card.operations;

/** The panel's screens a receipt names by their key (the server's `screen`). */
const SCREENS: Readonly<Record<string, string>> = en.saas.assistant.screens;

/** The menu's screens by their path (base/navigation.py). */
export const PANEL_SCREENS: Readonly<Record<string, string>> = {
  [BUSINESSES]: 'businesses',
  [STORE]: 'store',
  [BILLING]: 'billing',
  [ACCOUNT]: 'account',
};

/** The key of the verb of a write, by its operation's name (`<app>.<entity>.<action>`): its own, else its action's,
 *  else the chat's «Do this». */
export function actionKey(operation: string): string {
  const [app, entity, action] = operation.split('.');
  const entities = Object.hasOwn(OPERATIONS, app) ? OPERATIONS[app] : {};
  const actions = entity !== undefined && Object.hasOwn(entities, entity) ? entities[entity] : {};
  if (action !== undefined && Object.hasOwn(actions, action)) return `saas.assistant.card.operations.${operation}`;
  const last = operation.split('.').at(-1) ?? '';
  return operation.includes('.') && Object.hasOwn(ACTIONS, last) ? `saas.assistant.card.actions.${last}` : 'assistant.card.other';
}

/** The key of the name of the panel's screen a receipt names (the server's `screen`); none for one it does not know. */
export function placeKey(screen: string | undefined): string | null {
  return screen && Object.hasOwn(SCREENS, screen) ? `saas.assistant.screens.${screen}` : null;
}

/** The key of the name of one of the menu's screens by its path; none for any other, which the menu names. */
export function panelScreenKey(path: string): string | null {
  return Object.hasOwn(PANEL_SCREENS, path) ? `saas.assistant.screens.${PANEL_SCREENS[path]}` : null;
}

/** What `speak` takes from the browser: its `fetch` and the page (its SPA config and its CSRF cookie). */
export interface SpeakDeps {
  fetch: typeof globalThis.fetch;
  doc: Document;
}

/** The SDK's headers of a write on this page: the CSRF token and the device's id. */
function writeHeaders(doc: Document): Record<string, string> {
  const provider = createHeaderProvider(readSpaConfig(doc), {
    storage: {
      getItem: (key) => {
        try {
          return globalThis.localStorage?.getItem(key) ?? null;
        } catch {
          return null;
        }
      },
      setItem: (key, value) => {
        try {
          globalThis.localStorage?.setItem(key, value);
        } catch {
          // A storage that refuses: the device id lives in memory (the SDK's own fallback).
        }
      },
    },
    cookies: () => doc.cookie,
    randomUUID: () => globalThis.crypto.randomUUID(),
  });
  return provider.apiHeaders('POST');
}

/** The mp3 of `input` read in its server voice (`base.assistant.speak`). Its answer is the file itself,
 *  not JSON, so it is the SDK's `fetchFile` with the write's method, body and headers (the session cookie, the CSRF
 *  token): anything but an mp3 rejects with the envelope's `ApiError`, and no network (or an aborted request) with the
 *  SDK's `network_error`. The chat then reads the answer in the device's voice, unless it stopped the reading. */
export async function speak(
  input: AssistantSpeech,
  deps: SpeakDeps = { fetch: (url, init) => globalThis.fetch(url, init), doc: document },
): Promise<Blob> {
  const { path } = OPERATION_ROUTES['base.assistant.speak'];
  const body = JSON.stringify({ text: input.text, language: input.language, voice: input.voice });
  const headers = { ...writeHeaders(deps.doc), 'Content-Type': 'application/json' };
  // The chat's `signal`: a reading stopped before its audio arrives aborts the request.
  const file = await fetchFile(path, 'audio/mpeg', (url, init) =>
    deps.fetch(url, { ...init, method: 'POST', headers: { ...headers, ...init?.headers }, body, signal: input.signal }),
  );
  return file.blob;
}

/** The panel's chat, reading aloud in the device's voice (no `speak`: no server voice to offer). */
export const SAAS_ASSISTANT: AssistantConfig = {
  turnUrl: '/api/assistant/turn',
  usage: (client) => client.api.call('base.assistant.usage', {}),
  transcribe: (client, clip) => client.api.call('base.assistant.transcribe', clip),
  report: (client, report) => client.api.call('base.assistant.report', report),
  canUse: (session) => session.can(ASK),
  canUpgrade: () => false,
  verbKey: actionKey,
  placeKey,
  screenKey: panelScreenKey,
  spentNoteKey: 'saas.assistant.errors.quotaSpentAccount',
};

/** Whether erplora.com has a voice of its own to read the answers aloud (`spa-config.assistantSpeech`, base/spa.py):
 *  only `true` says so; absent, anything else or an unreadable config is no voice of the server. */
export function readsAloud(doc: Document = document): boolean {
  try {
    const raw = JSON.parse(doc.getElementById('spa-config')?.textContent ?? '{}') as { assistantSpeech?: unknown };
    return raw.assistantSpeech === true;
  } catch {
    return false;
  }
}

/** The panel's chat for this page: with the server's voice (`speak`) only when erplora.com has one. */
export function panelAssistant(doc: Document = document): AssistantConfig {
  return readsAloud(doc) ? { ...SAAS_ASSISTANT, speak: (input) => speak(input) } : SAAS_ASSISTANT;
}
