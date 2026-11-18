// accounts (accounts/schemas.py): Account → Security (the signed-in sessions and this browser) · API keys.

/** `accounts.SessionRowOut`: a signed-in browser or app; `device` is a code the panel names. */
export interface SessionRowOut {
  id: number;
  device: string;
  browser: string;
  browser_version: string;
  /** The app's version inside the ERPlora app (`browser` is then empty). */
  app_version: string | null;
  ip: string;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

/** `accounts.SessionListIn`: a page of the sessions, `limit` rows (at most 100) from `offset`. */
export interface SessionListIn {
  limit?: number;
  offset?: number;
}

/** `accounts.SessionListOut`: a page, this session first; `total` and `others` count every session, not the page. */
export interface SessionListOut {
  rows: SessionRowOut[];
  total: number;
  limit: number;
  offset: number;
  /** The sessions but this one: what «Close other sessions» ends. */
  others: number;
}

/** `accounts.SessionCloseIn`. */
export interface SessionCloseIn {
  id: number;
}

/** `accounts.SessionsClosedOut`. */
export interface SessionsClosedOut {
  closed: number;
}

/** `accounts.BrowserTrustOut`: until when this browser skips the app's code at sign-in, or `null` (ACCOUNTS-F17). */
export interface BrowserTrustOut {
  trusted_until: string | null;
}

/** `accounts.ApiKeyRowOut`: a key of the account, never its secret. */
export interface ApiKeyRowOut {
  id: string;
  name: string;
  /** `erps_live_` and the first characters of the secret. */
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  expired: boolean;
}

/** `accounts.ApiKeyScopeOut`: a permission a key may get, with its label in the reader's language. */
export interface ApiKeyScopeOut {
  id: string;
  label: string;
}

/** `accounts.ApiKeyListOut`: the keys not revoked, the newest first, and the permissions on offer. */
export interface ApiKeyListOut {
  rows: ApiKeyRowOut[];
  total: number;
  scopes: ApiKeyScopeOut[];
}

/** `accounts.ApiKeyCreateIn`: 30 or 90 days, or null for a key that does not expire (90 by default). */
export interface ApiKeyCreateIn {
  name: string;
  scopes: string[];
  expires_in_days?: 30 | 90 | null;
}

/** `accounts.ApiKeyCreatedOut`: `secret` is the whole key, shown this once. */
export interface ApiKeyCreatedOut {
  key: ApiKeyRowOut;
  secret: string;
}

/** `accounts.ApiKeyRevokeIn`. */
export interface ApiKeyRevokeIn {
  id: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'accounts.session.list': { input: SessionListIn | undefined; output: SessionListOut };
    'accounts.session.close': { input: SessionCloseIn; output: SessionsClosedOut };
    'accounts.session.close_others': { input: Record<string, never> | undefined; output: SessionsClosedOut };
    'accounts.browser_trust.get': { input: Record<string, never> | undefined; output: BrowserTrustOut };
    'accounts.browser_trust.revoke': { input: Record<string, never> | undefined; output: BrowserTrustOut };
    'accounts.apikey.list': { input: Record<string, never> | undefined; output: ApiKeyListOut };
    'accounts.apikey.create': { input: ApiKeyCreateIn; output: ApiKeyCreatedOut };
    'accounts.apikey.revoke': { input: ApiKeyRevokeIn; output: ApiKeyRowOut };
  }
}
