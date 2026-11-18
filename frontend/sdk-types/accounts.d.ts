// accounts (accounts/schemas.py): Account → Profile · Preferences, the account's hubs and «Report a problem».

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

/** `accounts.ThemeMode`: the shell's theme mode (`ThemeMode` of `@erplora/ui/shell`). */
export type AccountThemeMode = 'system' | 'light' | 'dark';

/** `accounts.Language`: `settings.LANGUAGES` (English, the source, and Spanish). */
export type AccountLanguage = 'en' | 'es';

/** `accounts.PreferencesOut`: Account → Preferences. */
export interface PreferencesOut {
  theme_mode: AccountThemeMode;
  transparency: boolean;
  language: AccountLanguage;
  hub_alerts: boolean;
}

/** `accounts.PreferencesUpdateIn`: only what is sent changes (each control saves on its own). */
export interface PreferencesUpdateIn {
  theme_mode?: AccountThemeMode;
  transparency?: boolean;
  language?: AccountLanguage;
  hub_alerts?: boolean;
}

/** `accounts.ProfileOut`: Account → Profile. `photo` is a data URL or null (the initials). */
export interface ProfileOut {
  id: string;
  email: string;
  email_verified: boolean;
  /** The new address waiting for its code, asked for in this session. */
  pending_email: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  photo: string | null;
  has_password: boolean;
  date_joined: string;
}

/** `accounts.ProfileUpdateIn`. */
export interface ProfileUpdateIn {
  first_name: string;
  last_name: string;
}

/** `accounts.ProfileDeletedOut`. */
export interface ProfileDeletedOut {
  deleted: boolean;
}

/** `accounts.ExportTermsOut`: what the account accepted, and when (ACCOUNTS-F10). */
export interface ExportTermsOut {
  accepted_at: string | null;
  terms_version: string | null;
  privacy_version: string | null;
}

/** `accounts.ExportAccountOut`: the account as «Download my data» writes it. */
export interface ExportAccountOut {
  id: string;
  email: string;
  email_verified: boolean;
  first_name: string;
  last_name: string;
  language: string;
  has_password: boolean;
  date_joined: string;
  last_login: string | null;
  terms: ExportTermsOut;
}

/** `accounts.ExportPreferencesOut`. */
export interface ExportPreferencesOut {
  theme_mode: AccountThemeMode;
  transparency: boolean;
  language: string;
  hub_alerts: boolean;
}

/** `accounts.ExportEmailAddressOut`. */
export interface ExportEmailAddressOut {
  email: string;
  verified: boolean;
  primary: boolean;
}

/** `accounts.ExportConnectedAccountOut`: a sign-in provider linked to the account (Google). */
export interface ExportConnectedAccountOut {
  provider: string;
  uid: string;
  date_joined: string;
  last_login: string | null;
}

/** `accounts.ExportSessionOut`. */
export interface ExportSessionOut {
  device: string;
  browser: string;
  browser_version: string;
  app_version: string | null;
  ip: string;
  created_at: string;
  last_seen_at: string;
}

/** `accounts.ExportApiKeyOut`: a key as it was made, revoked ones too; never its secret. */
export interface ExportApiKeyOut {
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** `accounts.DataExportOut`: the file of «Download my data» (GDPR art. 20, ACCOUNTS-F26); `businesses` and
 *  `invoices` are the rows of hubs and billing as those apps write them. */
export interface DataExportOut {
  format: 'erplora.account-export';
  version: number;
  exported_at: string;
  account: ExportAccountOut;
  preferences: ExportPreferencesOut;
  photo: string | null;
  email_addresses: ExportEmailAddressOut[];
  connected_accounts: ExportConnectedAccountOut[];
  sessions: ExportSessionOut[];
  api_keys: ExportApiKeyOut[];
  businesses: Record<string, unknown>[];
  invoices: Record<string, unknown>[];
}

/** `accounts.EmailChangeIn`. */
export interface EmailChangeIn {
  email: string;
}

/** `accounts.EmailVerifyIn`. */
export interface EmailVerifyIn {
  code: string;
}

/** `accounts.EmailVerifyOut`: a wrong code is no error, `verified` is false (0 tries left: ask again). */
export interface EmailVerifyOut {
  verified: boolean;
  attempts_left: number;
  profile: ProfileOut;
}

/** `accounts.PhotoUploadIn`: a JPEG, PNG or WebP as a `data:` URL. */
export interface PhotoUploadIn {
  image: string;
}

/** `accounts.SupportReportIn`: «Report a problem» (ACCOUNTS-F38). */
export interface SupportReportIn {
  subject: string;
  description: string;
  /** The panel's page the person came from. */
  page?: string | null;
}

/** `accounts.SupportReportOut`: where support answers. */
export interface SupportReportOut {
  reply_to: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'accounts.hub.list': { input: HubListIn; output: HubListOut };
    'accounts.profile.get': { input: Record<string, never> | undefined; output: ProfileOut };
    'accounts.profile.update': { input: ProfileUpdateIn; output: ProfileOut };
    'accounts.profile.delete': { input: Record<string, never> | undefined; output: ProfileDeletedOut };
    'accounts.data.export': { input: Record<string, never> | undefined; output: DataExportOut };
    'accounts.email.change': { input: EmailChangeIn; output: ProfileOut };
    'accounts.email.verify': { input: EmailVerifyIn; output: EmailVerifyOut };
    'accounts.photo.upload': { input: PhotoUploadIn; output: ProfileOut };
    'accounts.photo.remove': { input: Record<string, never> | undefined; output: ProfileOut };
    'accounts.preferences.get': { input: Record<string, never> | undefined; output: PreferencesOut };
    'accounts.preferences.update': { input: PreferencesUpdateIn; output: PreferencesOut };
    'accounts.support.report': { input: SupportReportIn; output: SupportReportOut };
  }
}
