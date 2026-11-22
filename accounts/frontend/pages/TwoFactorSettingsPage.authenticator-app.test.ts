// The authenticator app of the two-factor settings: setting it up (`mfa/totp/activate_form.html`), with the QR of
// its secret, and turning it off (`mfa/totp/deactivate_form.html`).
import { ionIconSrc } from '@erplora/ui/shell';
import { IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type Answer,
  anonymous,
  fakeAllauth,
  held,
  json,
  notFound,
  ok,
  reauthenticationRequired,
  rejected,
  signedIn,
} from '../__tests__/allauth-server';
import { CODES, codes, list, mountPage, recovery, setUpTwoFactorSettingsPage, TOTP } from '../__tests__/two-factor-settings-page';

const toDataURL = vi.hoisted(() => vi.fn((text: string) => Promise.resolve(`data:image/png;base64,QR:${text}`)));
vi.mock('qrcode', () => ({ default: { toDataURL }, toDataURL }));

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

const SECRET = 'JBSWY3DPEHPK3PXP';
const TOTP_URL = `otpauth://totp/ERPlora:owner%40example.com?secret=${SECRET}&issuer=ERPlora`;

const setup: Answer = () => json(404, { status: 404, meta: { secret: SECRET, totp_url: TOTP_URL } });

setUpTwoFactorSettingsPage();

beforeEach(() => {
  toDataURL.mockClear();
});

describe('TwoFactorSettingsPage: setting up the app (mfa/totp/activate_form.html)', () => {
  async function openSetup(more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({ 'GET /account/authenticators': list(), 'GET /account/authenticators/totp': setup, ...more });
    const page = await mountPage();
    await page.click('totp-set-up');
    return { ...page, server };
  }

  it('shows the QR of the secret (an image, baked here) and the key to type by hand', async () => {
    const { wrapper, text, button, has } = await openSetup();
    expect(has('totp-section')).toBe(false);
    expect(wrapper.get('h2.auth-title').text()).toBe('Set up your authenticator app');
    expect(text('activate-lead')).toBe('Scan this code with your authenticator app, then type the number it shows.');
    expect(toDataURL).toHaveBeenCalledExactlyOnceWith(TOTP_URL, { margin: 1, width: 220 });
    const qr = wrapper.get('img[data-testid="totp-qr"]');
    expect([qr.attributes('src'), qr.attributes('alt'), qr.classes()]).toEqual([`data:image/png;base64,QR:${TOTP_URL}`, 'QR code', ['qr']]);
    expect(text('activate-cant-scan')).toBe("Can't scan? Enter this key by hand:");
    expect(wrapper.get('code.auth-secret').text()).toBe(SECRET);
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Verification code');
    expect([button('activate-submit')!.props('type'), button('activate-submit')!.props('size'), button('activate-submit')!.text()]).toEqual([
      'submit',
      'large',
      'Turn on',
    ]);
    expect([button('activate-cancel')!.props('fill'), button('activate-cancel')!.text()]).toEqual(['clear', 'Cancel']);
    expect(document.title).toBe('Set up your authenticator app - ERPlora Cloud');
  });

  async function turnOn(page: Awaited<ReturnType<typeof openSetup>>, code = '123456') {
    await page.wrapper.getComponent(IonInput).setValue(code);
    await page.wrapper.get('form[data-testid="activate-form"]').trigger('submit');
    await flushPromises();
  }

  it('turns it on with the code and shows the recovery codes allauth generated, once', async () => {
    const page = await openSetup({
      'GET /account/authenticators': [list(), list(TOTP, recovery(10))],
      'POST /account/authenticators/totp': ok(TOTP),
      'GET /account/authenticators/recovery-codes': codes(CODES, 3, 3),
    });
    await turnOn(page, '654321');
    expect(page.server.callsTo('POST /account/authenticators/totp').map((c) => c.body)).toEqual([{ code: '654321' }]);
    expect(page.text('codes-list')).toBe(CODES.join('\n'));
    expect(page.text('codes-count')).toBe('3 of 3 unused');
  });

  it('goes back to the settings, now on, when there are no codes to show', async () => {
    const page = await openSetup({
      'GET /account/authenticators': [list(), list(TOTP)],
      'POST /account/authenticators/totp': ok(TOTP),
      'GET /account/authenticators/recovery-codes': notFound,
    });
    await turnOn(page);
    expect(page.text('totp-pill')).toBe('On');
    expect(page.has('codes-view')).toBe(false);
  });

  it('paints a wrong code under the input and stays', async () => {
    const page = await openSetup({ 'POST /account/authenticators/totp': rejected('Incorrect code.', 'code', 'incorrect_code') });
    await turnOn(page, '000000');
    const input = page.wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toContain('ion-invalid');
    expect(page.has('activate-view')).toBe(true);
    expect(page.has('failure')).toBe(false);
  });

  it('disables «Turn on» while the code is on its way', async () => {
    const answer = held(ok(TOTP));
    const page = await openSetup({ 'POST /account/authenticators/totp': answer.answer });
    await turnOn(page);
    expect((page.wrapper.get('[data-testid="activate-submit"]').element as Control).disabled).toBe(true);
    answer.release();
    await flushPromises();
  });

  // allauth issues a NEW secret on every GET of the setup and asks for a recent login on the POST:
  // leaving for /reauthenticate and back would show another QR, and the scanned one would fail.
  describe('when turning on needs a recent login', () => {
    const needsRecentLogin = (flows: string[], more: Record<string, Answer | Answer[]> = {}) =>
      openSetup({
        'GET /account/authenticators': [list(), list(TOTP, recovery(10))],
        'POST /account/authenticators/totp': [reauthenticationRequired(flows), ok(TOTP)],
        'GET /account/authenticators/recovery-codes': codes(CODES, 3, 3),
        ...more,
      });
    const input = (page: Awaited<ReturnType<typeof openSetup>>, testid: string) =>
      page.wrapper.findAllComponents(IonInput).find((i) => i.attributes('data-testid') === testid)!;
    async function confirmWith(page: Awaited<ReturnType<typeof openSetup>>, testid: string, value: string) {
      await input(page, testid).setValue(value);
      await page.wrapper.get('form[data-testid="confirm-form"]').trigger('submit');
      await flushPromises();
    }

    it('asks for the password right here, keeping the secret and the page', async () => {
      const page = await needsRecentLogin(['reauthenticate']);
      await turnOn(page, '123456');
      expect(page.router.currentRoute.value.path).toBe('/2fa');
      expect(page.has('activate-confirm')).toBe(true);
      expect(page.has('totp-qr')).toBe(false);
      expect(page.wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:lock'));
      expect(page.wrapper.get('h2.auth-title').text()).toBe("Confirm it's you");
      expect(page.text('confirm-lead')).toBe('Enter your password to change your sign-in security.');
      const password = input(page, 'confirm-password');
      expect([password.attributes('mode'), password.props('type'), password.props('fill'), password.props('label')]).toEqual([
        'md',
        'password',
        'outline',
        'Password',
      ]);
      expect(page.button('confirm-submit')!.text()).toBe('Confirm');
    });

    it('then turns on with the same code, without asking allauth for another secret', async () => {
      const page = await needsRecentLogin(['reauthenticate'], { 'POST /auth/reauthenticate': signedIn });
      await turnOn(page, '123456');
      await confirmWith(page, 'confirm-password', 'owner');
      expect(page.server.callsTo('POST /auth/reauthenticate').map((c) => c.body)).toEqual([{ password: 'owner' }]);
      expect(page.server.callsTo('POST /account/authenticators/totp').map((c) => c.body)).toEqual([
        { code: '123456' },
        { code: '123456' },
      ]);
      expect(page.server.callsTo('GET /account/authenticators/totp')).toHaveLength(1);
      expect(page.text('codes-list')).toBe(CODES.join('\n'));
    });

    it('asks for an authenticator code when that is the way allauth lists', async () => {
      const page = await needsRecentLogin(['mfa_reauthenticate'], { 'POST /auth/2fa/reauthenticate': signedIn });
      await turnOn(page, '123456');
      expect(page.wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:shield-check'));
      await confirmWith(page, 'code', '777777');
      expect(page.server.callsTo('POST /auth/2fa/reauthenticate').map((c) => c.body)).toEqual([{ code: '777777' }]);
      expect(page.server.callsTo('POST /account/authenticators/totp')).toHaveLength(2);
      expect(page.server.callsTo('GET /account/authenticators/totp')).toHaveLength(1);
    });

    it('paints a wrong password under its input and does not turn on', async () => {
      const page = await needsRecentLogin(['reauthenticate'], {
        'POST /auth/reauthenticate': rejected('Incorrect password.', 'password', 'incorrect_password'),
      });
      await turnOn(page);
      await confirmWith(page, 'confirm-password', 'wrong');
      expect((input(page, 'confirm-password').element as Control).errorText).toBe('Incorrect password.');
      expect(page.has('failure')).toBe(false);
      expect(page.server.callsTo('POST /account/authenticators/totp')).toHaveLength(1);
    });

    it('«Cancel» goes back to the same QR and key, without a new secret', async () => {
      const page = await needsRecentLogin(['reauthenticate']);
      await turnOn(page);
      await page.click('confirm-cancel');
      expect(page.has('activate-confirm')).toBe(false);
      expect(page.wrapper.get('code.auth-secret').text()).toBe(SECRET);
      expect(page.server.callsTo('GET /account/authenticators/totp')).toHaveLength(1);
    });

    it('speaks Spanish', async () => {
      fakeAllauth({
        'GET /account/authenticators': list(),
        'GET /account/authenticators/totp': setup,
        'POST /account/authenticators/totp': reauthenticationRequired(['reauthenticate']),
      });
      const page = await mountPage('es');
      await page.click('totp-set-up');
      await turnOn(page as unknown as Awaited<ReturnType<typeof openSetup>>);
      expect(page.wrapper.get('h2.auth-title').text()).toBe('Confirma que eres tú');
      expect(page.button('confirm-submit')!.text()).toBe('Confirmar');
    });
  });

  it('says why allauth will not set it up (unverified email) and stays on the settings', async () => {
    const page = await openSetup({
      'GET /account/authenticators/totp': () =>
        json(409, {
          status: 409,
          errors: [{ message: 'You cannot activate two-factor authentication until you have verified your email address.', code: 'unverified_email' }],
        }),
    });
    expect(page.text('failure')).toBe('You cannot activate two-factor authentication until you have verified your email address.');
    expect(page.has('totp-section')).toBe(true);
  });

  it('«Cancel» goes back to the settings', async () => {
    const page = await openSetup();
    await page.click('activate-cancel');
    expect(page.has('activate-view')).toBe(false);
    expect(page.has('totp-section')).toBe(true);
  });
});

describe('TwoFactorSettingsPage: turning the app off (mfa/totp/deactivate_form.html)', () => {
  async function openDeactivate(more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)), ...more });
    const page = await mountPage();
    await page.click('totp-turn-off');
    return { ...page, server };
  }

  it('asks first, with the shield of the template', async () => {
    const { wrapper, text, button } = await openDeactivate();
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:shield-x'));
    expect(wrapper.get('h2.auth-title').text()).toBe('Turn off the authenticator app?');
    // ACCOUNTS-F16: the code mailed at every sign-in stays (old «re-activa Email OTP»): never «your password only».
    expect(text('deactivate-lead')).toBe('You will sign in with your password and the code we email you.');
    const submit = button('deactivate-submit')!;
    expect([submit.props('color'), submit.props('size'), submit.text()]).toEqual(['danger', 'large', 'Turn off']);
    expect([button('deactivate-keep')!.props('fill'), button('deactivate-keep')!.text()]).toEqual(['clear', 'Keep it on']);
  });

  it('turns it off and shows the settings again, now off', async () => {
    const page = await openDeactivate({
      'GET /account/authenticators': [list(TOTP, recovery(9)), list()],
      'DELETE /account/authenticators/totp': ok(),
    });
    await page.click('deactivate-submit');
    expect(page.server.callsTo('DELETE /account/authenticators/totp')).toHaveLength(1);
    expect(page.text('totp-pill')).toBe('Off');
  });

  it('goes to confirm it is you, with the app, when allauth asks for a recent login', async () => {
    const page = await openDeactivate({ 'DELETE /account/authenticators/totp': reauthenticationRequired() });
    await page.click('deactivate-submit');
    expect(page.router.currentRoute.value.path).toBe('/reauthenticate');
    expect(page.router.currentRoute.value.query).toEqual({
      next: '/2fa',
      method: 'totp',
      flows: 'reauthenticate,mfa_reauthenticate',
    });
  });

  it('says why allauth will not turn it off', async () => {
    const page = await openDeactivate({
      'DELETE /account/authenticators/totp': rejected('You cannot deactivate two-factor authentication.', undefined, 'cannot_delete_authenticator'),
    });
    await page.click('deactivate-submit');
    expect(page.text('failure')).toBe('You cannot deactivate two-factor authentication.');
    expect(page.has('deactivate-view')).toBe(true);
  });

  it('sends a session that ended to the sign-in', async () => {
    const page = await openDeactivate({ 'DELETE /account/authenticators/totp': anonymous });
    await page.click('deactivate-submit');
    expect(page.router.currentRoute.value.fullPath).toBe('/launch?next=/2fa');
  });

  it('«Keep it on» goes back to the settings', async () => {
    const page = await openDeactivate();
    await page.click('deactivate-keep');
    expect(page.text('totp-pill')).toBe('On');
  });
});
