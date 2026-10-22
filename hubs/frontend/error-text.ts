// What a failed call says on screen. The server's message already speaks the person's language
// (`ctx.language`). A failure that is not the server's answer — a call that never got one (`network_error`),
// one that is not the API's envelope (`unexpected_response`: a proxy's HTML page, a 502) or a failure in the
// browser (`client_error`) — is said with a sentence of the panel's catalogue, in its voice and naming ERPlora,
// the same whoever made the error: the SDK words these in the person's language too (hub#2281), with its own
// generic sentences, and the panel's own `client_error`s (`new ApiError(0, 'client_error', String(error))`)
// carry the browser's English text. Every toast, dialog and notice of hubs goes through it.
import type { FormModalError } from '@erplora/ui/components';
import type { ApiError } from '@erplora/ui/sdk';
import { useI18n } from 'vue-i18n';

/** The SDK's codes for what is not a server's answer, and what the panel says for each. */
const OWN = {
  network_error: 'hubs.errors.network',
  unexpected_response: 'hubs.errors.unexpected',
  client_error: 'hubs.errors.unexpected',
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
