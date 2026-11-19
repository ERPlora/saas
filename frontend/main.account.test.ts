// What the account chose (theme mode, transparency effects, language) painted at boot, the session read again once an
// Account page changes it, and the user menu's theme kept in the account.
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
vi.mock('@erplora/ui/components', async (original) => (await import('./__tests__/main-doubles')).componentsDouble(original));
vi.mock('@erplora/ui/sdk', async (original) => (await import('./__tests__/main-doubles')).sdkDouble(original));

import { chooseThemeMode, createShell, setThemeMode, themeMode, themeTransparency, toastError } from '@erplora/ui/shell';
import { ApiError } from '@erplora/ui/sdk';

import { fakeShell, main, ME, renderShellHtml, setUpMain, shellOptions } from './__tests__/main-boot';
import { sdk } from './__tests__/main-doubles';
import entryEn from './locale/en.json';
import entryEs from './locale/es.json';
import { sessionChanged } from './session-changed';

/** `base.session.me` without an account: no preferences, no language of its own. */
const ANONYMOUS = { ...ME, user: null, preferences: null, account_language: null };

setUpMain();

describe("what the account chose, painted at boot (Account → Preferences; base.session.me)", () => {
  const dark = () => document.documentElement.classList.contains('ion-palette-dark');

  it('paints the theme mode and the transparency of the embedded session before the shell boots (no flash)', async () => {
    renderShellHtml({ ...ME, preferences: { theme_mode: 'dark', transparency: false } });
    let lookAtShell: [string, boolean, boolean] | undefined;
    const { app, router } = fakeShell();
    vi.mocked(createShell).mockImplementation(async () => {
      lookAtShell = [themeMode.value, themeTransparency.value, document.documentElement.classList.contains('ep-opaque')];
      return { app, router } as never;
    });
    await main.boot({});
    expect(lookAtShell).toEqual(['dark', false, true]);
    expect([themeMode.value, dark()]).toEqual(['dark', true]);
  });

  it('or the one /api/me answers, before the session goes live (the gate mounts after that)', async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...ME, preferences: { theme_mode: 'dark', transparency: false } });
    fakeShell();
    await main.boot({});
    const { status } = shellOptions();
    let lookWhenLive: [string, boolean] | undefined;
    await vi.waitFor(() => {
      expect(status.value).toBe('live');
      lookWhenLive = [themeMode.value, themeTransparency.value];
    });
    expect(lookWhenLive).toEqual(['dark', false]);
    expect(dark()).toBe(true);
  });

  it("leaves an anonymous visitor this device's mode (no account to read it from)", async () => {
    setThemeMode('dark');
    renderShellHtml(ANONYMOUS);
    fakeShell();
    await main.boot({});
    expect([themeMode.value, dark()]).toEqual(['dark', true]);
  });

  it("switches the SPA to the account's own language when the session speaks another one", async () => {
    renderShellHtml({ ...ME, language: 'en', account_language: 'es' });
    fakeShell();
    await main.boot({});
    // createShell follows `session.language` (i18n locale and <html lang>).
    expect(shellOptions().session.value?.language).toBe('es');
  });

  it("also when the account's language comes with /api/me", async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...ME, language: 'es', account_language: 'en' });
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    await vi.waitFor(() => expect(status.value).toBe('live'));
    expect(session.value?.language).toBe('en');
  });

  it("keeps the session's language without an account language of its own", async () => {
    renderShellHtml({ ...ANONYMOUS, language: 'es' });
    fakeShell();
    await main.boot({});
    expect(shellOptions().session.value?.language).toBe('es');
  });
});

describe('the session read again once an Account page changes what it says (saas#292, ACCOUNTS-F22)', () => {
  /** The panel's menu as the server translates it (`base/navigation.py`): the shell paints these labels as they come. */
  const menuIn = (language: 'en' | 'es') => [
    {
      id: 'base',
      label: '',
      items: [{ path: '/dashboard/businesses', label: language === 'es' ? 'Negocios' : 'Businesses', icon: 'lucide:store' }],
    },
  ];
  const IN_ENGLISH = { ...ME, language: 'en', account_language: 'en', menu: menuIn('en') };

  it('asks /api/me again, and the shell paints the menu it answers: in the language just saved', async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    expect(session.value?.menu).toEqual(menuIn('en'));
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...IN_ENGLISH, language: 'es', account_language: 'es', menu: menuIn('es') });
    sessionChanged();
    expect(sdk.client.api.call).toHaveBeenCalledWith('base.session.me', {});
    await vi.waitFor(() => expect(session.value?.menu).toEqual(menuIn('es')));
    expect(session.value?.language).toBe('es');
  });

  it("takes the answer as at boot: the account's own language wins over the one the session speaks", async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...IN_ENGLISH, language: 'en', account_language: 'es', menu: menuIn('es') });
    sessionChanged();
    await vi.waitFor(() => expect(session.value?.menu).toEqual(menuIn('es')));
    expect(session.value?.language).toBe('es');
  });

  it('leaves the theme painted as it is: a save of it may still be on its way, and the answer predate it', async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    setThemeMode('dark');
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...IN_ENGLISH, preferences: { theme_mode: 'light', transparency: true }, menu: menuIn('es') });
    sessionChanged();
    await vi.waitFor(() => expect(session.value?.menu).toEqual(menuIn('es')));
    expect(themeMode.value).toBe('dark');
  });

  it('two changes in a row: the answer to the last one is the one painted, whatever arrives first', async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    const answers: Array<(answer: unknown) => void> = [];
    vi.mocked(sdk.client.api.call).mockImplementation(() => new Promise((resolve) => answers.push(resolve)));
    // Every boot of this file listens, in the order they booted: this one's ask is the last of each change.
    sessionChanged();
    const perChange = answers.length;
    sessionChanged();
    const [first, last] = [answers[perChange - 1], answers[2 * perChange - 1]];
    last({ ...IN_ENGLISH, menu: menuIn('en') });
    await vi.waitFor(() => expect(session.value?.menu).toEqual(menuIn('en')));
    first({ ...IN_ENGLISH, language: 'es', account_language: 'es', menu: menuIn('es') });
    await new Promise((settle) => setTimeout(settle, 0));
    expect(session.value?.menu).toEqual(menuIn('en'));
    expect(session.value?.language).toBe('en');
  });

  it('nor says a failure of an ask a later one already replaced', async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    const asks: Array<{ resolve: (answer: unknown) => void; reject: (error: unknown) => void }> = [];
    vi.mocked(sdk.client.api.call).mockImplementation(() => new Promise((resolve, reject) => asks.push({ resolve, reject })));
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    sessionChanged();
    const perChange = asks.length;
    sessionChanged();
    asks[perChange - 1].reject(new ApiError(0, 'network_error', 'Network error'));
    asks[2 * perChange - 1].resolve({ ...IN_ENGLISH, menu: menuIn('es') });
    await vi.waitFor(() => expect(session.value?.menu).toEqual(menuIn('es')));
    expect(logged).toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
    logged.mockRestore();
  });

  it('a read that fails keeps the session on screen (the person stays signed in) and says so, in the language of the page', async () => {
    renderShellHtml(IN_ENGLISH);
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    const failure = new ApiError(0, 'network_error', 'Network error');
    vi.mocked(sdk.client.api.call).mockRejectedValue(failure);
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    document.documentElement.lang = 'es';
    sessionChanged();
    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith(entryEs.saas.session.notRefreshed));
    expect(session.value).toEqual(IN_ENGLISH);
    expect(status.value).toBe('live');
    expect(logged).toHaveBeenCalledWith('saas: base.session.me failed', failure);
    logged.mockRestore();
  });

  it("says it in en and es (the entry's own catalogue)", () => {
    expect([entryEn.saas.session.notRefreshed, entryEs.saas.session.notRefreshed]).toEqual([
      "Couldn't update the menu with your changes. Reload the page.",
      'No se ha podido actualizar el menú con tus cambios. Recarga la página.',
    ]);
  });
});

describe("the user menu's theme, kept in the account (accounts.preferences.update)", () => {
  it('choosing a mode in the user menu saves it through the typed client, and it stays painted', async () => {
    vi.mocked(sdk.client.api.call).mockResolvedValue({ theme_mode: 'dark' });
    fakeShell();
    await main.boot({});
    chooseThemeMode('dark');
    expect(sdk.client.api.call).toHaveBeenCalledExactlyOnceWith('accounts.preferences.update', { theme_mode: 'dark' });
    await Promise.resolve();
    expect(themeMode.value).toBe('dark');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a save that fails keeps the mode on screen and says so with a toast, in the language of the page', async () => {
    const failure = new ApiError(0, 'network_error', 'Network error');
    vi.mocked(sdk.client.api.call).mockRejectedValue(failure);
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeShell();
    await main.boot({});
    document.documentElement.lang = 'es';
    chooseThemeMode('light');
    await vi.waitFor(() => expect(toastError).toHaveBeenCalledExactlyOnceWith(entryEs.saas.userMenu.themeNotSaved));
    expect(themeMode.value).toBe('light');
    expect(logged).toHaveBeenCalledWith('saas: accounts.preferences.update failed', failure);
    logged.mockRestore();
  });

  it('without an account there is nothing to save it in: the mode is painted, no call', async () => {
    renderShellHtml(ANONYMOUS);
    fakeShell();
    await main.boot({});
    chooseThemeMode('dark');
    expect(themeMode.value).toBe('dark');
    expect(sdk.client.api.call).not.toHaveBeenCalled();
  });

  it("says it in en and es (the entry's own catalogue)", () => {
    expect([entryEn.saas.userMenu.themeNotSaved, entryEs.saas.userMenu.themeNotSaved]).toEqual([
      "Couldn't save the appearance to your account.",
      'No se ha podido guardar la apariencia en tu cuenta.',
    ]);
  });
});
