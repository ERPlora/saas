// The two-factor settings page (`TwoFactorSettingsPage`) mounted for its tests on `/2fa`, signed in, and the
// authenticators allauth answers with. A test file calls `setUpTwoFactorSettingsPage()` at its top. Its views that are
// components of their own are mounted alone with `mountTwoFactorPiece`.
import { IonButton } from '@ionic/vue';
import { flushPromises, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, vi } from 'vitest';
import type { Component } from 'vue';

import TwoFactorSettingsPage from '../pages/TwoFactorSettingsPage.vue';
import { type Answer, json, ok } from './allauth-server';
import { mountAccountPage, SIGNED_IN } from './mount-account-page';

export const TOTP = { type: 'totp', created_at: 1760000000, last_used_at: null };
export const recovery = (unused: number) => ({
  type: 'recovery_codes',
  created_at: 1760000001,
  last_used_at: null,
  total_code_count: 10,
  unused_code_count: unused,
});
export const CODES = ['a1b2-c3d4', 'e5f6-g7h8', 'i9j0-k1l2'];

export const list =
  (...authenticators: unknown[]): Answer =>
  () =>
    json(200, { status: 200, data: authenticators });
export const codes = (unusedCodes: string[], unused = unusedCodes.length, total = 10) =>
  ok({ ...recovery(unused), total_code_count: total, unused_codes: unusedCodes });

export function setUpTwoFactorSettingsPage(): void {
  beforeEach(() => {
    document.cookie = 'csrftoken=tok-123';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
}

export async function mountPage(locale: 'en' | 'es' = 'en', options: { call?: ReturnType<typeof vi.fn>; path?: string } = {}) {
  const mounted = await mountAccountPage(TwoFactorSettingsPage, {
    path: options.path ?? '/2fa',
    session: SIGNED_IN,
    locale,
    call: options.call,
  });
  const { wrapper } = mounted;
  const { button, text, has } = finders(wrapper);
  async function click(testid: string) {
    const target = button(testid);
    if (!target) throw new Error(`no button ${testid}`);
    await target.trigger('click');
    await flushPromises();
  }
  return { ...mounted, button, click, text, has };
}

/** A view of the page that is a component of its own, mounted alone with the props the page would hand it. */
export async function mountTwoFactorPiece(component: Component, props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const { wrapper } = await mountAccountPage(component, { props, locale });
  return { wrapper, ...finders(wrapper) };
}

/** Its buttons, texts and parts, by `data-testid`. */
function finders(wrapper: VueWrapper) {
  return {
    button: (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid),
    text: (testid: string) => wrapper.get(`[data-testid="${testid}"]`).text(),
    has: (testid: string) => wrapper.find(`[data-testid="${testid}"]`).exists(),
  };
}
