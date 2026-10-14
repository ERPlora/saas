// Test helper of the Store's pages and components: the hubs harness (the SDK's fake clock and network on
// the SaaS's op → route map, a session, a memory router) with the catalogues the Store paints with —
// billing's, hubs' for the shared error sentences (`useErrorText`, `hubs/frontend/error-text.ts`) and the
// entry's (`LoadFailed.vue`'s «could not load», merged by main.ts at runtime).
//
// `liveDown` makes `/api/live` refuse the stream (503, as with the SSE down in the audit of 2026-10-14,
// R-04) until it is set back to `false`: the API still answers, and a stream opened after that is served.
//
// A test that opens a dialog mocks Ionic's overlay with the ui's stub, in its own file (hoisted):
//   vi.mock('@ionic/vue', async (importOriginal) => ({
//     ...(await importOriginal<typeof import('@ionic/vue')>()),
//     IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
//   }));
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref, shallowRef } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import { createTestClient, flush, resultFrame, type StreamCall } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { PopoverStub } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import entryEn from '../../../frontend/locale/en.json';
import entryEs from '../../../frontend/locale/es.json';
import hubsEn from '../../../hubs/frontend/locale/en.json';
import hubsEs from '../../../hubs/frontend/locale/es.json';
import { describeCall, OWNER, SAAS_CONFIG, subId } from '../../../hubs/frontend/__tests__/mount-hubs';
import en from '../locale/en.json';
import es from '../locale/es.json';

export {
  accessibleName,
  apiError,
  describeCall,
  enterView,
  flush,
  ionProps,
  optionValue,
  OWNER,
  subId,
} from '../../../hubs/frontend/__tests__/mount-hubs';
export type { ApiCall, StreamCall } from '../../../hubs/frontend/__tests__/mount-hubs';

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** Answers every API call (not the stream); `{}` by default. */
  api?: Parameters<ReturnType<typeof createTestClient>['net']['onApi']>[0];
  /** Extra routes of the memory router (the Store navigates to a business's page). */
  routes?: Array<{ path: string; component: Component }>;
}

export async function mountBilling(component: Component, options: MountOptions = {}) {
  /** `true`: `/api/live` answers 503 (the SSE down); the API keeps answering. */
  const liveDown = shallowRef(false);
  const served: { fetchImpl?: (url: string, init: RequestInit) => Promise<Response> } = {};
  const harness = createTestClient(
    {
      routes: OPERATION_ROUTES,
      fetchImpl: (url, init) =>
        liveDown.value && url.startsWith(`${SAAS_CONFIG.liveUrl}?`)
          ? Promise.resolve(Response.json({ error: { code: 'service_unavailable', message: 'Service unavailable' } }, { status: 503 }))
          : served.fetchImpl!(url, init),
    },
    SAAS_CONFIG,
  );
  served.fetchImpl = harness.net.fetchImpl;
  if (options.api) harness.net.onApi(options.api);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [...(options.routes ?? []), { path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/');
  await router.isReady();
  const app = createApp({});
  const me = ref<SessionMe | undefined>(options.session ?? OWNER);
  provideSession(me, ref('live'), { app });
  const i18n = createShellI18n({
    locale: options.locale ?? 'en',
    messages: { en: { ...entryEn, ...hubsEn, ...en }, es: { ...entryEs, ...hubsEs, ...es } },
  });
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
  async function result(call: StreamCall, op: Parameters<typeof subId>[1], data: unknown, rev = 1): Promise<void> {
    call.push(resultFrame(subId(harness.client, op), data, rev));
    await flush();
  }
  /** The API calls made so far, described. */
  const calls = () => harness.net.api.map(describeCall);
  /** An element by its `data-testid`, anywhere in the document (dialogs render out of the wrapper). */
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as (HTMLElement & Record<string, unknown>) | null;
  /** Every element with that `data-testid`. */
  const qa = (id: string) => [...document.querySelectorAll(`[data-testid="${id}"]`)] as Array<HTMLElement & Record<string, unknown>>;
  return { ...harness, router, wrapper, live, result, calls, me, i18n, q, qa, liveDown };
}
