// What a failed call says on screen: the server's own message (it already speaks the person's
// language), or — when the call never got a server's answer (`network_error`), got one that is not the
// API's (`unexpected_response`, an HTML error page) or broke in the browser (`client_error`) — a
// sentence of ours, in English and Spanish, never the SDK's English internals. The Account page's own copy of
// hubs' `useErrorText` (accounts does not import hubs: the dependency goes the other way, PLAN-SAAS §3.6 point 16).
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountPanel } from './__tests__/mount-panel';
import { useErrorText } from './error-text';

async function texts(locale: 'en' | 'es') {
  let api!: ReturnType<typeof useErrorText>;
  await mountPanel(
    defineComponent({
      setup() {
        api = useErrorText();
        return () => h('div');
      },
    }),
    { locale },
  );
  return api;
}

describe('useErrorText', () => {
  it("says the server's message as it comes", async () => {
    const { text } = await texts('es');
    expect(text(new ApiError(409, 'accounts.email_taken', 'Este correo ya lo usa otra cuenta.'))).toBe('Este correo ya lo usa otra cuenta.');
  });

  it('says a lost connection, an answer that is not the API’s and a browser failure in the person’s language', async () => {
    const { text } = await texts('es');
    expect(text(new ApiError(0, 'network_error', 'Network error (Failed to fetch)'))).toBe(
      'No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.',
    );
    expect(text(new ApiError(502, 'unexpected_response', 'Unexpected response (HTTP 502)'))).toBe(
      'Algo ha fallado en ERPlora. Inténtalo de nuevo en unos minutos.',
    );
    expect(text(new ApiError(0, 'client_error', 'TypeError: x is undefined'))).toBe(
      'Algo ha fallado en ERPlora. Inténtalo de nuevo en unos minutos.',
    );
    const en = (await texts('en')).text;
    expect(en(new ApiError(0, 'network_error', 'x'))).toBe('We could not reach ERPlora. Check your connection and try again.');
  });

  it('nothing to say without an error', async () => {
    const { text, forDialog } = await texts('en');
    expect(text(null)).toBe('');
    expect(forDialog(null)).toBeNull();
  });

  it('hands a dialog the error with its message said so, its per-field messages kept', async () => {
    const { forDialog } = await texts('es');
    const error = new ApiError(422, 'invalid_payload', 'Invalid payload', { email: 'Correo no válido.' });
    expect(forDialog(error)).toEqual({ message: 'Invalid payload', code: 'invalid_payload', status: 422, fields: { email: 'Correo no válido.' } });
    expect(forDialog(new ApiError(0, 'network_error', 'x'))?.message).toBe(
      'No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.',
    );
  });
});
