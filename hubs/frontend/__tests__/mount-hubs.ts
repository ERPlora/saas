// Test helper of the businesses panel's pages and components: the SDK's live harness (fake clock, fake
// network serving the stream and the API) on the SaaS's op → route map, the shell's i18n with the hubs
// catalogues, a session and a memory router. Pages are mounted as the shell would mount them.
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

import {
  type ApiCall,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
  TEST_CONFIG,
} from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { PopoverStub } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import entryEn from '../../../frontend/locale/en.json';
import entryEs from '../../../frontend/locale/es.json';
import accountsEn from '../../../accounts/frontend/locale/en.json';
import accountsEs from '../../../accounts/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';
// What IonRouterOutlet does each time a page comes on screen: one helper for the accounts' pages and these.
export { enterView } from '../../../accounts/frontend/__tests__/mount-account-page';
export type { ApiCall, StreamCall };

// What `createShell` does at boot (`addIcons(ION_ICONS)`): `ion:` icons paint by name. `ionicons` is
// not a dependency of the SaaS, so its registry (`window.Ionicons.map`) is filled the way it fills it.
const ionicons = ((window as unknown as { Ionicons?: { map?: Map<string, string> } }).Ionicons ??= {});
ionicons.map ??= new Map();
for (const [name, url] of Object.entries(ION_ICONS)) ionicons.map.set(name, url);

/** The SaaS's `spa-config` as the tests read it (CSRF cookie, hubs' origin). */
export const SAAS_CONFIG = { ...TEST_CONFIG, csrfCookieName: 'csrftoken', hubOrigin: 'http://{slug}.localhost:8000' };

export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Laura Martín', email: 'laura@example.com' },
  permissions: ['hubs.view', 'hubs.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const ANONYMOUS: SessionMe = { ...OWNER, user: null, permissions: [] };

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** Answers every API call (not the stream); `{}` by default. */
  api?: (call: ApiCall) => Response | Promise<Response>;
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

/** The error envelope of the API, as ninja answers it. */
export function apiError(status: number, code: string, message: string, fields?: Record<string, string>): Response {
  return Response.json({ error: { code, message, ...(fields ? { fields } : {}) } }, { status });
}

/** The path and the JSON body (or query) of an API call. */
export function describeCall(call: ApiCall): { method: string; path: string; body: unknown; query: Record<string, string> } {
  const url = new URL(call.url, 'http://localhost');
  const body = typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined;
  return {
    method: (call.init.method ?? 'GET').toUpperCase(),
    path: url.pathname,
    body,
    query: Object.fromEntries(url.searchParams.entries()),
  };
}

export async function mountHubs(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES }, SAAS_CONFIG);
  if (options.api) harness.net.onApi(options.api);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  const me = ref<SessionMe | undefined>(options.session ?? OWNER);
  provideSession(me, ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    attachTo: document.body,
    global: {
      // The entry's catalogue too (`saas.*`): the shared pieces of `frontend/` (LoadFailed) speak with it;
      // and the accounts' (`accounts.*`): the launcher holds the sign-in (`SignInForm`), as the shell merges them all.
      plugins: [
        router,
        createShellI18n({
          locale: options.locale ?? 'en',
          messages: { en: { ...en, ...entryEn, ...accountsEn }, es: { ...es, ...entryEs, ...accountsEs } },
        }),
      ],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
      // An inline `ion-popover` presents itself only in a real browser (the DataTable's row menu «⋮»).
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
  return { ...harness, router, wrapper, live, result, calls, me };
}

/** What Ionic Vue sets on its elements: a property (fill, label, value…) or, for `mode`, an attribute. */
export function ionProps(el: { element: Element }, ...names: string[]): Record<string, unknown> {
  const element = el.element as unknown as Record<string, unknown> & Element;
  const kebab = (name: string) => name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
  return Object.fromEntries(names.map((name) => [name, element[name] ?? element.getAttribute(kebab(name)) ?? undefined]));
}

/** The value of an `ion-select-option` (a property of the element). */
export const optionValue = (el: { element: Element }): unknown => (el.element as unknown as { value?: unknown }).value;


/**
 * The accessible name of an Ionic control: Ionic moves `aria-label` from its host to the native
 * control inside (its shadow `button`), as it does in a browser.
 */
export function accessibleName(el: { element: Element }): string | null {
  const host = el.element;
  return host.getAttribute('aria-label') ?? host.shadowRoot?.querySelector('button, [role]')?.getAttribute('aria-label') ?? null;
}
