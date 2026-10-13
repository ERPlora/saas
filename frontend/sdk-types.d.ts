// Types of the SaaS's operations for the SDK (`useLive`, `useCommand`, `client.api.call`).
// WRITTEN BY HAND for now from base/schemas.py and accounts/schemas.py (generated from `/api/openapi.json` later, as in
// hub-next). Keep it in step with `./generated/operations.json`. Sign-in is not an operation: the
// SDK reaches allauth.headless through `createAllauthClient`.
import type { SessionMe } from '@erplora/ui/shell';

/** `base.SessionMeIn`: no parameters. */
export type SessionMeIn = Record<string, never>;

/** `base.SessionMeOut`: what the shell reads (`SessionMe`) plus the scope it was resolved for (the user). */
export interface SessionMeOut extends SessionMe {
  scope: { kind: string; key: string };
}

/** `accounts.HubListIn`: no parameters (the account is the session's). */
export type HubListIn = Record<string, never>;

/** `accounts.HubOut`: a hub the account can enter, its host and the jump to it (`/hub-login/`). */
export interface HubOut {
  slug: string;
  host: string;
  url: string;
}

/** `accounts.HubListOut`: the account's hubs, alphabetically. */
export interface HubListOut {
  hubs: HubOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.session.me': { input: SessionMeIn; output: SessionMeOut };
    'accounts.hub.list': { input: HubListIn; output: HubListOut };
  }
}
