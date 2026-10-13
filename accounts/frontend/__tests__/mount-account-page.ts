// Test helper of the account pages and components: the shell's i18n with the accounts catalogues,
// a session, a memory router and a live client whose API call is a mock. Mounted as the shell would.
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { flushPromises, mount } from '@vue/test-utils';
import { vi } from 'vitest';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import en from '../locale/en.json';
import es from '../locale/es.json';

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
  await router.push(options.path ?? '/');
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
