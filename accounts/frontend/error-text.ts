// What a failed call says on screen. The server's message already speaks the person's language
// (`ctx.language`); the SDK's own codes do not: a call that never got the server's answer
// (`network_error`), got one that is not the API's envelope (`unexpected_response`: a proxy's HTML
// page, a 502) or broke in the browser (`client_error`) carries an English internal message, so the
// panel says a sentence of its catalogue instead. Every toast, dialog and notice of Account goes through it.
// A copy of hubs' `error-text.ts`: accounts never imports hubs (the dependency goes the other way, PLAN-SAAS
// §3.6 point 16), and its sentences live in the accounts catalogues.
import type { FormModalError } from '@erplora/ui/components';
import type { ApiError } from '@erplora/ui/sdk';
import { useI18n } from 'vue-i18n';

/** The SDK's codes for what is not a server's answer, and what the panel says for each. */
const OWN = {
  network_error: 'accounts.account.errors.network',
  unexpected_response: 'accounts.account.errors.unexpected',
  client_error: 'accounts.account.errors.unexpected',
} as const;

type Failure = Pick<ApiError, 'message' | 'code' | 'status'> & { fields?: Readonly<Record<string, string>> };

export function useErrorText() {
  const { t } = useI18n();

  /** The sentence for `error`; `''` without one. */
  function text(error: Failure | null | undefined): string {
    if (!error) return '';
    const key = OWN[error.code as keyof typeof OWN];
    return key ? t(key) : error.message;
  }

  /** `error` for a FormModal or a ConfirmDialog: its message said so, its per-field messages kept. */
  function forDialog(error: Failure | null | undefined): FormModalError | null {
    if (!error) return null;
    return {
      message: text(error),
      code: error.code,
      status: error.status,
      ...(error.fields ? { fields: { ...error.fields } } : {}),
    };
  }

  return { text, forDialog };
}
