// Test helper of the Account page (`/account/:tab`) and its parts: the SDK's live harness (fake clock, fake network
// serving the stream and the API) on the SaaS's op → route map, the shell's i18n with the accounts catalogues, a
// session and a memory router. Mounted as the shell would mount them, as hubs' `mount-hubs.ts` does.
//
// A test that opens a dialog mocks Ionic's overlay with the ui's stub, in its own file (hoisted):
//   vi.mock('@ionic/vue', async (importOriginal) => ({
//     ...(await importOriginal<typeof import('@ionic/vue')>()),
//     IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
//   }));
import { createShellI18n, ION_ICONS, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import { PopoverStub } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import {
  type ApiCall,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
  TEST_CONFIG,
} from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import type { ApiKeyListOut, PreferencesOut, ProfileOut, SessionRowOut } from '../../../frontend/sdk-types';
import saasEn from '../../../frontend/locale/en.json';
import saasEs from '../../../frontend/locale/es.json';
import accountsEn from '../locale/en.json';
import accountsEs from '../locale/es.json';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';
export { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';

// The catalogues the shell merges at boot (`main.ts`): the entry's own (`saas.*`: «could not load», LoadFailed)
// and the accounts' (`accounts.*`); different top-level keys, so they never collide.
const en = { ...saasEn, ...accountsEn };
const es = { ...saasEs, ...accountsEs };
export type { ApiCall, StreamCall };

// What `createShell` does at boot (`addIcons(ION_ICONS)`): `ion:` icons paint by name.
const ionicons = ((window as unknown as { Ionicons?: { map?: Map<string, string> } }).Ionicons ??= {});
ionicons.map ??= new Map();
for (const [name, url] of Object.entries(ION_ICONS)) ionicons.map.set(name, url);

/** The SaaS's `spa-config` as the tests read it (CSRF cookie, Google on). */
export const SAAS_CONFIG = { ...TEST_CONFIG, csrfCookieName: 'csrftoken', googleEnabled: true };

export const LAURA: SessionMe = {
  user: { id: 'u1', label: 'Laura Martín', email: 'laura@example.com' },
  permissions: ['accounts.view', 'accounts.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

/** `accounts.profile.get` of Laura, with what a test changes. */
export function profile(overrides: Partial<ProfileOut> = {}): ProfileOut {
  return {
    id: 'u1',
    email: 'laura@example.com',
    email_verified: true,
    pending_email: null,
    first_name: 'Laura',
    last_name: 'Martín Pérez',
    full_name: 'Laura Martín Pérez',
    photo: null,
    has_password: true,
    date_joined: '2026-01-10T09:00:00Z',
    ...overrides,
  };
}

/** `accounts.preferences.get`. */
export function preferences(overrides: Partial<PreferencesOut> = {}): PreferencesOut {
  return { theme_mode: 'system', language: 'en', hub_alerts: true, marketing_emails: false, ...overrides };
}

/** A row of `accounts.session.list`. */
export function session(id: number, overrides: Partial<SessionRowOut> = {}): SessionRowOut {
  return {
    id,
    device: 'mac',
    browser: 'Chrome',
    browser_version: '130',
    app_version: null,
    ip: '203.0.113.7',
    created_at: '2026-10-01T08:00:00Z',
    last_seen_at: '2026-10-14T08:00:00Z',
    is_current: false,
    ...overrides,
  };
}

/** The permissions a key may get, as the server labels them in English. */
export const SCOPES = [
  { id: 'hubs.read', label: 'Businesses · read' },
  { id: 'hubs.write', label: 'Businesses · write' },
  { id: 'billing.read', label: 'Invoices · read' },
];

/** `accounts.apikey.list` with these rows. */
export function keyList(rows: ApiKeyListOut['rows'] = []): ApiKeyListOut {
  return { rows, total: rows.length, scopes: SCOPES };
}

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** Answers every API call (not the stream); `{}` by default. */
  api?: (call: ApiCall) => Response | Promise<Response>;
  /** Keys of `spa-config` over the SaaS's (`googleEnabled: false`…). */
  config?: Record<string, unknown>;
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

/** The error envelope of the API, as ninja answers it (`extra`: the envelope's other keys). */
export function apiError(status: number, code: string, message: string, extra: Record<string, unknown> = {}): Response {
  return Response.json({ error: { code, message, ...extra } }, { status });
}

/** The 401 of a command that needs a recent sign-in, with the ways to confirm it. */
export function reauthRequired(flows = ['reauthenticate'], providers: string[] = []): Response {
  return apiError(401, 'reauthentication_required', "Confirm it's you: enter your password again.", { flows, providers });
}

/** The path and the JSON body (or query) of an API call. */
export function describeCall(call: ApiCall): { method: string; path: string; body: unknown } {
  const url = new URL(call.url, 'http://localhost');
  const body = typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined;
  return { method: (call.init.method ?? 'GET').toUpperCase(), path: url.pathname, body };
}

export async function mountPanel(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES }, { ...SAAS_CONFIG, ...options.config });
  if (options.api) harness.net.onApi(options.api);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/');
  await router.isReady();
  const app = createApp({});
  const me = ref<SessionMe | undefined>(options.session ?? LAURA);
  provideSession(me, ref('live'), { app });
  const i18n = createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } });
  const wrapper = mount(component, {
    props: options.props,
    attachTo: document.body,
    global: {
      plugins: [router, i18n],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
      stubs: { IonPopover: PopoverStub, ...options.stubs },
    },
  });
  /** Opens the stream; returns the call to push frames into. */
  const live = (): Promise<StreamCall> => harness.goLive();
  /** Pushes a result for the first subscription of `op` and lets Vue render it. */
  async function result(call: StreamCall, op: OpName, data: unknown, rev = 1): Promise<void> {
    call.push(resultFrame(subId(harness.client, op), data, rev));
    await flush();
  }
  /** The API calls made so far, described. */
  const calls = () => harness.net.api.map(describeCall);
  /** An element by its `data-testid`, anywhere in the document (dialogs render outside the mount). */
  const q = (testid: string) => document.querySelector(`[data-testid="${testid}"]`) as (HTMLElement & Record<string, unknown>) | null;
  return { ...harness, router, wrapper, live, result, calls, me, i18n, q };
}

/** What Ionic Vue sets on its elements: a property (fill, label, value…) or, for `mode`, an attribute. */
export function ionProps(el: Element | null, ...names: string[]): Record<string, unknown> {
  if (!el) throw new Error('no element');
  const element = el as unknown as Record<string, unknown> & Element;
  const kebab = (name: string) => name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
  return Object.fromEntries(names.map((name) => [name, element[name] ?? element.getAttribute(kebab(name)) ?? undefined]));
}

/** Types `value` into an Ionic field as a person does (its `ionInput`, which `v-model` listens to). */
export async function typeInto(el: Element | null, value: string): Promise<void> {
  if (!el) throw new Error('no field');
  (el as unknown as { value: string }).value = value;
  el.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
  await flush();
}

/** Picks `value` in an `ion-select`, `ion-segment` or `ion-toggle`/`ion-checkbox` (`checked`). */
export async function choose(el: Element | null, detail: { value?: unknown; checked?: boolean }): Promise<void> {
  if (!el) throw new Error('no control');
  el.dispatchEvent(new CustomEvent('ionChange', { detail }));
  await flush();
}

/**
 * The accessible name of an Ionic control: Ionic moves `aria-label` from its host to the native control inside
 * (its shadow `button`), as it does in a browser.
 */
export function accessibleName(el: Element | null): string | null {
  if (!el) return null;
  return el.getAttribute('aria-label') ?? el.shadowRoot?.querySelector('button, [role]')?.getAttribute('aria-label') ?? null;
}
