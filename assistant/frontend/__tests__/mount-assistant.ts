// Test helper of the panel's assistant (assistant/frontend): its pieces mounted as the shell mounts them — the SDK's
// live harness on the SaaS's op → route map (the fake network answers `base.assistant.usage`), the shell's i18n with the
// catalogues main.ts merges (the chat's words as the panel says them and the entry's `saas.*`), a session, the shell's
// config, a memory router with the panel's screens, Ionic's router API on it, and the chat configured as the panel's
// (`SAAS_ASSISTANT`). The tab's assistant is the test's own (`installAssistant`): its turns go to the test's `post`.
import { createAssistant, installAssistant, type Assistant, configureAssistant } from '@erplora/ui/components';
import type { TurnBody, TurnFrame, TurnOptions } from '@erplora/ui/components';
import { createShellI18n, ION_ICONS, provideSession, provideShellConfig, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { enableAutoUnmount, mount } from '@vue/test-utils';
import { afterEach, vi } from 'vitest';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter, type RouteLocationRaw, type Router } from 'vue-router';

import { type ApiHandler, createTestClient } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { ACCOUNT, BILLING, BUSINESSES, STORE } from '../../../accounts/frontend/paths';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import saasEn from '../../../frontend/locale/en.json';
import saasEs from '../../../frontend/locale/es.json';
import { ASK, ASSISTANT_MESSAGES, SAAS_ASSISTANT } from '../options';

export { flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';

// What `createShell` does at boot (`addIcons(ION_ICONS)`): `ion:` icons paint by name.
const ionicons = ((window as unknown as { Ionicons?: { map?: Map<string, string> } }).Ionicons ??= {});
ionicons.map ??= new Map();
for (const [name, url] of Object.entries(ION_ICONS)) ionicons.map.set(name, url);
enableAutoUnmount(afterEach);

/** An account of the panel: it may ask the assistant (every account may). */
export const LENA: SessionMe = {
  user: { id: 'u1', label: 'Lena', email: 'lena@example.com' },
  permissions: ['accounts.view', 'hubs.view', ASK],
  menu: [
    {
      id: 'base',
      label: '',
      items: [
        { path: BUSINESSES, label: 'Businesses', icon: 'lucide:store' },
        { path: STORE, label: 'Store', icon: 'lucide:shopping-bag', webOnly: true },
        { path: BILLING, label: 'Billing', icon: 'lucide:receipt' },
        { path: ACCOUNT, label: 'Account', icon: 'lucide:circle-user' },
      ],
    },
  ],
  apps: [],
  language: 'en',
};

/** The month's allowance as `base.assistant.usage` answers it. */
export function usage(used: number, limit = 30) {
  return { used, limit, resets_at: '2026-11-01T00:00:00Z', demo: false };
}

/** A storage of its own for each test (the conversation, open or closed). */
export function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => void store.delete(key),
    setItem: (key, value) => void store.set(key, String(value)),
  };
}

/** The tab's assistant of a test: what it posts, and the frames each turn answers (`script`, in order). */
export function testAssistant(open = false): { assistant: Assistant; posted: TurnBody[]; script: TurnFrame[][] } {
  const posted: TurnBody[] = [];
  const script: TurnFrame[][] = [];
  const openStorage = memoryStorage();
  if (open) openStorage.setItem('erplora.assistant.open', '1');
  const assistant = createAssistant({
    storage: memoryStorage(),
    openStorage,
    post: async (body: TurnBody, options: TurnOptions) => {
      posted.push(JSON.parse(JSON.stringify(body)) as TurnBody);
      for (const frame of script.shift() ?? []) options.onFrame(frame);
    },
  });
  installAssistant(assistant);
  return { assistant, posted, script };
}

/** Forgets the test's assistant and configuration. */
export function forgetTestAssistant(): void {
  installAssistant(undefined);
  configureAssistant(undefined);
}

/** Ionic's router API (`useIonRouter`) as the shell's Ionic router provides it app-wide (`navManager`). */
function navManager(router: Router) {
  return {
    handleNavigate: vi.fn((location: RouteLocationRaw, action = 'push') =>
      action === 'replace' ? router.replace(location) : router.push(location),
    ),
    canGoBack: () => false,
    goBack: () => router.back(),
    goForward: () => router.forward(),
  };
}

export interface MountOptions {
  locale?: 'en' | 'es';
  /** `null`: nobody signed in. */
  session?: SessionMe | null;
  /** What the fake API answers (`base.assistant.usage`…). */
  onApi?: ApiHandler;
  stubs?: Record<string, Component | boolean>;
}

const BLANK = { template: '<div />' };

export async function mountAssistant(component: Component, options: MountOptions = {}) {
  configureAssistant(SAAS_ASSISTANT);
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.onApi) harness.net.onApi(options.onApi);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...[BUSINESSES, STORE, BILLING, ACCOUNT].map((path) => ({ path, component: BLANK })),
      { path: '/:pathMatch(.*)*', name: 'not-found', component: BLANK },
    ],
  });
  await router.push(BUSINESSES);
  await router.isReady();
  const app = createApp({});
  provideSession(ref(options.session === null ? undefined : (options.session ?? LENA)), ref('live'), { app });
  provideShellConfig({ homePath: BUSINESSES }, app);
  const messages = {
    en: { ...ASSISTANT_MESSAGES.en, ...saasEn },
    es: { ...ASSISTANT_MESSAGES.es, ...saasEs },
  };
  const wrapper = mount(component, {
    attachTo: document.body,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client, navManager: navManager(router) },
      stubs: options.stubs,
    },
  });
  return { ...harness, router, wrapper };
}
