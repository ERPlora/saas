// The page of the codes allauth mails (`VerifyEmailPage`) mounted for its tests, with `window.location.assign`
// stubbed and a CSRF cookie. A test file calls `setUpVerifyEmailPage()` at its top.
import { applySurface } from '@erplora/ui/shell';
import { IonButton, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, vi } from 'vitest';

import VerifyEmailPage from '../pages/VerifyEmailPage.vue';
import { mountAccountPage } from './mount-account-page';

export type Control = HTMLElement & { errorText?: string; disabled?: boolean };

export let assign: ReturnType<typeof vi.fn>;

export function setUpVerifyEmailPage(): void {
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    document.cookie = 'csrftoken=tok-123';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    applySurface('web');
  });
}

interface Options {
  path?: string;
  locale?: 'en' | 'es';
  /** The address the sign-in typed, handed over in the history state (never in the URL). */
  email?: string;
  /** The code the sign-in left waiting for, handed over the same way. */
  flow?: string;
}

export async function mountPage(options: Options = {}) {
  const state = { ...(options.email ? { email: options.email } : {}), ...(options.flow ? { flow: options.flow } : {}) };
  const mounted = await mountAccountPage(VerifyEmailPage, {
    path: options.path ?? '/verify-email',
    locale: options.locale,
    state: Object.keys(state).length ? state : undefined,
  });
  const { wrapper } = mounted;
  async function verify(code = '123456') {
    await wrapper.getComponent(IonInput).setValue(code);
    await wrapper.get('form[data-testid="verify-email-form"]').trigger('submit');
    await flushPromises();
  }
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid)!;
  async function click(testid: string) {
    await button(testid).trigger('click');
    await flushPromises();
  }
  const failure = () => wrapper.find('.non-field-error');
  const notice = () => wrapper.find('[data-testid="verify-email-notice"]');
  return { ...mounted, verify, button, click, failure, notice };
}
