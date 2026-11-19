// The page Django serves the SPA entry (spa-config and the embedded session) and `main.ts`, which boots on import,
// imported once per test file. A test file mocks the modules of `main-doubles.ts` and calls `setUpMain()` at its top.
import { createShell, resetUserThemePreferences, setThemePersister } from '@erplora/ui/shell';
import { afterEach, beforeAll, beforeEach, vi } from 'vitest';

import { sdk } from './main-doubles';

type Main = typeof import('../main');

export const ME = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [],
  menu: [],
  apps: [],
  language: 'es',
  preferences: { theme_mode: 'system', transparency: true },
  account_language: 'es',
};

export function fakeShell(isReady: () => Promise<void> = () => Promise.resolve()) {
  const app = { mount: vi.fn() };
  const router = { isReady: vi.fn(isReady) };
  vi.mocked(createShell).mockResolvedValue({ app, router } as never);
  return { app, router };
}

export function shellOptions() {
  return vi.mocked(createShell).mock.calls.at(-1)![0];
}

export function renderShellHtml(session: object | null = ME, config: object = {}) {
  const spaConfig = JSON.stringify({ csrfCookieName: 'csrftoken', lang: 'es', googleEnabled: true, ...config });
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">${spaConfig}</script>
    ${session ? `<script id="session-me" type="application/json">${JSON.stringify(session)}</script>` : ''}
    <div id="app"></div>`;
}

export let main: Main;
export let importBoot: ReturnType<typeof shellOptions>;
export let assign: ReturnType<typeof vi.fn>;

export function setUpMain(): void {
  beforeAll(async () => {
    sdk.client.api.call = vi.fn();
    sdk.auth.logout = vi.fn();
    renderShellHtml();
    fakeShell();
    main = await import('../main');
    importBoot = shellOptions();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    setThemePersister(undefined);
    resetUserThemePreferences();
    document.documentElement.lang = '';
    sdk.client.api.call = vi.fn();
    sdk.auth.logout = vi.fn();
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    renderShellHtml();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });
}
