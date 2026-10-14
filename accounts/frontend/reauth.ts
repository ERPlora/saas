// «Confirm it's you» before a command that gives access or destroys (accounts/README.md, «Reautenticación»): the
// server answers 401 `reauthentication_required` with the ways to confirm (`flows`: `reauthenticate`, the password;
// `mfa_reauthenticate`, a code of the authenticator; `provider_redirect`, signing in again with a linked provider
// named in `providers`). `guard(run)` runs the command; on that 401 it asks the person (the page paints
// `ReauthModal` with `request`) and, once confirmed, runs the command once more. Closing the dialog gives up
// quietly (`undefined`); any other failure goes through untouched. Reusable by any page of the SaaS:
//   const reauth = useReauthentication();
//   const created = await reauth.guard(() => create.run(input));
//   <ReauthModal :request="reauth.request.value" @confirmed="reauth.confirmed" @cancel="reauth.cancelled" />
import { ApiError, ReauthenticationRequiredError } from '@erplora/ui/sdk';
import { shallowRef } from 'vue';

export { default as ReauthModal } from './components/ReauthModal.vue';

/** The ways the server accepts to confirm a recent sign-in. */
export interface ReauthRequest {
  flows: string[];
  providers: string[];
}

/** The code of the 401 that asks for a recent sign-in. */
export const REAUTHENTICATION_REQUIRED = 'reauthentication_required';

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

/** What the 401 asks for (ours, or allauth.headless's own at its account doors); `null` for any other failure. */
export function reauthRequestOf(error: unknown): ReauthRequest | null {
  if (error instanceof ReauthenticationRequiredError) return { flows: strings(error.flows), providers: [] };
  if (!(error instanceof ApiError) || error.code !== REAUTHENTICATION_REQUIRED) return null;
  return { flows: strings(error.details.flows), providers: strings(error.details.providers) };
}

export function useReauthentication() {
  /** What the dialog asks for while it is open; `null` when closed. */
  const request = shallowRef<ReauthRequest | null>(null);
  let answer: ((confirmed: boolean) => void) | null = null;

  function settle(confirmed: boolean): void {
    const done = answer;
    answer = null;
    request.value = null;
    done?.(confirmed);
  }

  function ask(asked: ReauthRequest): Promise<boolean> {
    settle(false);
    request.value = asked;
    return new Promise((resolve) => (answer = resolve));
  }

  /** Runs `run`; asks to confirm when the server wants a recent sign-in, then runs it once more. */
  async function guard<T>(run: () => Promise<T>): Promise<T | undefined> {
    try {
      return await run();
    } catch (error) {
      const asked = reauthRequestOf(error);
      if (!asked) throw error;
      if (!(await ask(asked))) return undefined;
      return await run();
    }
  }

  return { request, guard, confirmed: () => settle(true), cancelled: () => settle(false) };
}
