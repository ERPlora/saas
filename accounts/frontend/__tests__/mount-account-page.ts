// Test helper of the account pages and components: the shell's i18n with the accounts catalogues,
// a session, a memory router and a live client whose API call is a mock. Mounted as the shell would.
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { flushPromises, mount } from '@vue/test-utils';
import { vi } from 'vitest';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import saasEn from '../../../frontend/locale/en.json';
import saasEs from '../../../frontend/locale/es.json';
import accountsEn from '../locale/en.json';
import accountsEs from '../locale/es.json';

// The catalogues the shell merges at boot (`main.ts`): the entry's own (`saas.*`) and the accounts' (`accounts.*`).
const en = { ...saasEn, ...accountsEn };
const es = { ...saasEs, ...accountsEs };

export const ANONYMOUS: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
export const SIGNED_IN: SessionMe = { ...ANONYMOUS, user: { id: 'u1', label: 'Owner' } };

export const CONFIG = {
  csrfCookieName: 'csrftoken',
  csrfHeader: 'X-CSRFToken',
  liveUrl: '/api/live',
  apiBase: '/api',
  lang: 'en',
  deviceIdStorageKey: 'erplora.device_id',
  hubOrigin: 'http://{slug}.localhost:8000',
};

export interface MountOptions {
  path?: string;
  /** The history state the page arrives with (`router.push({ state })`), e.g. the address a sign-up typed. */
  state?: Record<string, string>;
  locale?: 'en' | 'es';
  session?: SessionMe;
  config?: Record<string, unknown>;
  /** `client.api.call`; a mock that never answers by default. */
  call?: ReturnType<typeof vi.fn>;
  props?: Record<string, unknown>;
  slots?: Record<string, string>;
}

export async function mountAccountPage(component: Component, options: MountOptions = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  const path = options.path ?? '/';
  // The string as given (a location object would re-encode its query); the object only to carry a state.
  const target = router.resolve(path);
  await router.push(options.state ? { path: target.path, query: target.query, hash: target.hash, state: options.state } : path);
  await router.isReady();
  const app = createApp({});
  provideSession(ref(options.session ?? ANONYMOUS), ref('live'), { app });
  const call = options.call ?? vi.fn(() => new Promise(() => undefined));
  const client = { config: { ...CONFIG, ...options.config }, api: { call } };
  const wrapper = mount(component, {
    props: options.props,
    slots: options.slots,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: client },
    },
  });
  await flushPromises();
  return { wrapper, call, router };
}

/** What IonRouterOutlet does each time the page comes on screen (also when Ionic reuses it). */
export function enterView(wrapper: { vm: unknown }): void {
  // Ionic keeps the hooks under `onIonViewWillEnter`, on the instance's exposed object (`<script setup>`).
  type Hooks = { onIonViewWillEnter?: Array<() => void> };
  const instance = (wrapper.vm as { $: { exposed: Hooks | null; proxy: Hooks } }).$;
  for (const hook of instance.exposed?.onIonViewWillEnter ?? instance.proxy.onIonViewWillEnter ?? []) hook();
}
