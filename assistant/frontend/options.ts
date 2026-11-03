// The panel's configuration of the shared assistant (`@erplora/ui/components`: the Hub's same chat, with erplora.com's
// own tools; plan 2026-10-30-asistente-saas §6, PLAN-SAAS §23): `configureAssistant(SAAS_ASSISTANT)` when the SPA boots
// (frontend/main.ts), and in the tests that mount its pieces.
// - A turn goes to `base.assistant.turn`'s route (base/api.py); the account's allowance and the report of an answer
//   through base's operations. Where nothing is sold (the installed app's account surface) the session says so
//   (base/surface.py): the route carries no `?surface=`, which would stick to the session and hide the Store from the
//   web too.
// - Whoever may ask the assistant sees its button (`assistant.ask`, every account's); nobody upgrades a plan from it:
//   the account's 30 messages a month are no plan's (ASSISTANT-F26). No microphone: the voice stays out of the panel
//   (D9). No approvals: the panel has no manager's approval (the Hub's).
// - The panel's words (`saas.assistant.*`, frontend/locale): the verb of each write the assistant may run, by its
//   operation (`card.operations.<app>.<entity>.<action>`, one per write: guardrail base/tests/
//   test_assistant_panel_words.py), else by its action (`card.actions.<action>`), else the chat's «Do this»; and the
//   menu's four screens (`screens.<key>`), by the server's key (base/assistant.py `SCREEN_OF_APP`) or by their path.
// - Under a spent allowance, where the Hub says to ask whoever runs the business to upgrade the plan, the panel says
//   that each business has its own assistant (`spentNoteKey`: `saas.assistant.errors.quotaSpentAccount`): the
//   account's messages are no plan's, and nobody is offered «Upgrade plan» here.
import type { AssistantConfig } from '@erplora/ui/components';

import { ACCOUNT, BILLING, BUSINESSES, STORE } from '../../accounts/frontend/paths';
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

export const SAAS_ASSISTANT: AssistantConfig = {
  turnUrl: '/api/assistant/turn',
  usage: (client) => client.api.call('base.assistant.usage', {}),
  report: (client, report) => client.api.call('base.assistant.report', report),
  canUse: (session) => session.can(ASK),
  canUpgrade: () => false,
  verbKey: actionKey,
  placeKey,
  screenKey: panelScreenKey,
  spentNoteKey: 'saas.assistant.errors.quotaSpentAccount',
};
