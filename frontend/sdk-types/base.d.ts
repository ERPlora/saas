// Types of the SaaS's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), one file per area,
// written by hand from the schemas of the API. Keep them in step with `../generated/operations.json`.
// Dates and UUIDs travel as strings (ISO 8601). Sign-in is not an operation: the
// SDK reaches allauth.headless through `createAllauthClient`.
import type { SessionMe } from '@erplora/ui/shell';

import type { PreferencesOut } from './accounts';

/** `base.SessionMeIn`: no parameters. */
export type SessionMeIn = Record<string, never>;

/** `base.SessionPreferences`: what the account chose in Account → Preferences that the shell paints with. */
export type SessionPreferences = Pick<PreferencesOut, 'theme_mode' | 'transparency'>;

/** `base.SessionMeOut`: what the shell reads (`SessionMe`), the scope it was resolved for (the user) and what the
 *  account chose (`null` without one): its theme mode, its transparency effects and its language (`User.language`). */
export interface SessionMeOut extends SessionMe {
  scope: { kind: string; key: string };
  preferences: SessionPreferences | null;
  account_language: string | null;
}

/** `base.AssistantUsageIn`: no input (the session's account). */
export type AssistantUsageIn = Record<string, never>;

/** `base.AssistantUsageOut`: the account's messages of the month with the panel's assistant (ASSISTANT-F26). */
export interface AssistantUsageOut {
  used: number;
  limit: number;
  /** When the allowance comes back (UTC): the first of next month. */
  resets_at: string | null;
  /** Always false: the panel's assistant is never a demo's. */
  demo: boolean;
}

/** `base.AssistantReportIn`: a bad answer the person reports to ERPlora's team (ASSISTANT-F23). */
export interface AssistantReportIn {
  message_id: string;
  reason: 'incorrect' | 'harmful' | 'instructions' | 'other';
  comment?: string;
  question?: string;
  answer: string;
  /** Whether the answer's turn brought pages from the web (the `web` of its `done` frame): its text is then not mailed. */
  web?: boolean | null;
}

/** `base.AssistantReportOut`: mailed, or already reported. */
export interface AssistantReportOut {
  sent: boolean;
  duplicate: boolean;
}

/** `base.AssistantTranscribeIn`: a dictation of the session's account, its audio in base64 (ASSISTANT-F21). */
export interface AssistantTranscribeIn {
  audio: string;
  mime_type: string;
  language?: string;
}

/** `base.AssistantTranscribeOut`: the words, for the person to check, and the language they went in. */
export interface AssistantTranscribeOut {
  text: string;
  language: string;
}

/**
 * `base.AssistantSpeakIn`: an answer to read aloud for the session's account (ASSISTANT-F22), in the language asked
 * (empty: the account's) and a voice of the engine, or its own for the language (empty). Its route answers with the mp3
 * itself (`audio/mpeg`), so the operation has no JSON output; without an engine, 503 `assistant.speech_unavailable`.
 */
export interface AssistantSpeakIn {
  text: string;
  language?: '' | 'es' | 'en';
  voice?: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.session.me': { input: SessionMeIn; output: SessionMeOut };
    'base.assistant.usage': { input: AssistantUsageIn; output: AssistantUsageOut };
    'base.assistant.report': { input: AssistantReportIn; output: AssistantReportOut };
    'base.assistant.transcribe': { input: AssistantTranscribeIn; output: AssistantTranscribeOut };
    'base.assistant.speak': { input: AssistantSpeakIn; output: never };
  }
}
