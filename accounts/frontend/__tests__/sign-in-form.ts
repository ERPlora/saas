// The launcher's form (`SignInForm`) mounted for its tests, on the launcher's route over a blank page, with
// `window.location.assign` stubbed and a CSRF cookie. A test file calls `setUpSignInForm()` at its top.
import { IonInput, IonSegment } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, vi } from 'vitest';
import type { RouteRecordRaw } from 'vue-router';

import hubRoutes from '../../../hubs/frontend/routes';
import SignInForm from '../components/SignInForm.vue';
import { LAUNCHER } from '../paths';
import { mountAccountPage } from './mount-account-page';
import { choose } from './mount-panel';

export type Control = HTMLElement & { errorText?: string; disabled?: boolean };

/** The launcher's route as the app defines it (its path and its other addresses, `/shell`), on a blank page. */
const LAUNCHER_ROUTE = { ...hubRoutes.find((route) => route.path === LAUNCHER), component: { template: '<div />' } } as RouteRecordRaw;

export let assign: ReturnType<typeof vi.fn>;

export function setUpSignInForm(): void {
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    document.cookie = 'csrftoken=tok-123';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });
}

interface Options {
  path?: string;
  locale?: 'en' | 'es';
  googleEnabled?: boolean;
}

export async function mountForm(options: Options = {}) {
  const mounted = await mountAccountPage(SignInForm, {
    path: options.path ?? '/launch',
    locale: options.locale,
    config: options.googleEnabled === undefined ? {} : { googleEnabled: options.googleEnabled },
    routes: [LAUNCHER_ROUTE],
  });
  const { wrapper } = mounted;
  const input = (name: 'email' | 'password') =>
    wrapper.findAllComponents(IonInput).find((c) => c.attributes('data-testid') === `login-${name}`)!;
  async function signIn(email = 'owner@example.com', password = 'owner') {
    await input('email').setValue(email);
    await input('password').setValue(password);
    await wrapper.get('form[data-testid="login-form"]').trigger('submit');
    await flushPromises();
  }
  const failure = () => wrapper.find('.non-field-error');
  /** Picks a tab of the segment above the form, as a person taps it. */
  const chooseTab = (tab: 'signin' | 'signup') => choose(wrapper.get('[data-testid="login-tabs"]').element, { value: tab });
  const tab = () => wrapper.findComponent(IonSegment).props('value');
  // In jsdom, Ionic's segment button hides its label from `textContent` (its slot patches): read the markup.
  const tabLabel = (value: 'signin' | 'signup') =>
    wrapper.get(`[data-testid="login-tab-${value}"]`).element.innerHTML.replace(/<[^>]*>/g, '').trim();
  return { ...mounted, input, signIn, failure, chooseTab, tab, tabLabel };
}
