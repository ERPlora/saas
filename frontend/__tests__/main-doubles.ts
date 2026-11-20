// The module doubles of the tests of the SPA entry (`frontend/main.*.test.ts`), written once. `vi.mock` is hoisted in
// each test file, so the file keeps its own calls and hands the factories over:
//   vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
// Only `vi` is imported here: a real import of a mocked module from inside its own factory would load it unmocked.
import { vi } from 'vitest';

type Original = <T>() => Promise<T>;

export const sdk = {
  client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } },
  auth: { logout: (() => undefined) as (...args: unknown[]) => unknown },
};

/** The real theme (and i18n helpers) of the shell; only its boot and its toast are stand-ins. */
export async function shellDouble(importOriginal: Original) {
  return {
    ...((await importOriginal()) as object),
    createShell: vi.fn(),
    toastError: vi.fn(),
  };
}

/** The real chat (its configuration and its words); only the forgetting of a conversation is watched. */
export async function componentsDouble(importOriginal: Original) {
  return {
    ...((await importOriginal()) as object),
    forgetAssistant: vi.fn(),
  };
}

export async function sdkDouble(importOriginal: Original) {
  return {
    ...((await importOriginal()) as object),
    createLiveClient: vi.fn(() => sdk.client),
    createAllauthClient: vi.fn(() => sdk.auth),
    provideLiveClient: vi.fn(),
  };
}
