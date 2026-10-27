// The two-factor settings (`/2fa`), over allauth.headless: one page whose views are the templates
// `mfa/index.html` (the authenticator app and the recovery codes), `mfa/totp/activate_form.html`,
// `mfa/totp/deactivate_form.html`, `mfa/recovery_codes/index.html` and `generate.html`; the URL
// stays `/2fa`. A change that needs a recent login goes to `/reauthenticate` and back; 2FA switched
// off on the server (404) sends to the launcher with a notice.
import { formatDateTime } from '@erplora/ui/components';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type Answer,
  anonymous,
  fakeAllauth,
  held,
  json,
  notFound,
  offline,
  ok,
  reauthenticationRequired,
  rejected,
  signedIn,
} from '../__tests__/allauth-server';
import { mountAccountPage, SIGNED_IN } from '../__tests__/mount-account-page';
import TwoFactorSettingsPage from './TwoFactorSettingsPage.vue';

const toDataURL = vi.hoisted(() => vi.fn((text: string) => Promise.resolve(`data:image/png;base64,QR:${text}`)));
vi.mock('qrcode', () => ({ default: { toDataURL }, toDataURL }));

type Control = HTMLElement & { errorText?: string; disabled?: boolean };

const TOTP = { type: 'totp', created_at: 1760000000, last_used_at: null };
const recovery = (unused: number) => ({
  type: 'recovery_codes',
  created_at: 1760000001,
  last_used_at: null,
  total_code_count: 10,
  unused_code_count: unused,
});
const CODES = ['a1b2-c3d4', 'e5f6-g7h8', 'i9j0-k1l2'];
const SECRET = 'JBSWY3DPEHPK3PXP';
const TOTP_URL = `otpauth://totp/ERPlora:owner%40example.com?secret=${SECRET}&issuer=ERPlora`;

const list =
  (...authenticators: unknown[]): Answer =>
  () =>
    json(200, { status: 200, data: authenticators });
const setup: Answer = () => json(404, { status: 404, meta: { secret: SECRET, totp_url: TOTP_URL } });
const codes = (unusedCodes: string[], unused = unusedCodes.length, total = 10) =>
  ok({ ...recovery(unused), total_code_count: total, unused_codes: unusedCodes });

beforeEach(() => {
  document.cookie = 'csrftoken=tok-123';
  toDataURL.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function mountPage(locale: 'en' | 'es' = 'en', options: { call?: ReturnType<typeof vi.fn>; path?: string } = {}) {
  const mounted = await mountAccountPage(TwoFactorSettingsPage, {
    path: options.path ?? '/2fa',
    session: SIGNED_IN,
    locale,
    call: options.call,
  });
  const { wrapper } = mounted;
  const button = (testid: string) => wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid);
  async function click(testid: string) {
    const target = button(testid);
    if (!target) throw new Error(`no button ${testid}`);
    await target.trigger('click');
    await flushPromises();
  }
  const text = (testid: string) => wrapper.get(`[data-testid="${testid}"]`).text();
  const has = (testid: string) => wrapper.find(`[data-testid="${testid}"]`).exists();
  return { ...mounted, button, click, text, has };
}

describe('TwoFactorSettingsPage: loading', () => {
  it('shows a spinner and «Loading…» until the authenticators arrive', async () => {
    const answer = held(list());
    fakeAllauth({ 'GET /account/authenticators': answer.answer });
    const { wrapper, text, has } = await mountPage();
    expect(wrapper.find('[data-testid="mfa-loading"] ion-spinner').exists()).toBe(true);
    expect(text('mfa-loading')).toContain('Loading…');
    expect(has('totp-section')).toBe(false);
    answer.release();
    await flushPromises();
    expect(has('mfa-loading')).toBe(false);
    expect(has('totp-section')).toBe(true);
  });

  it('sends to the launcher with a notice when the server has 2FA switched off (404), showing nothing else', async () => {
    fakeAllauth({ 'GET /account/authenticators': notFound });
    const { router, has, wrapper } = await mountPage();
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ notice: 'mfa_unavailable' });
    for (const testid of ['mfa-loading', 'mfa-load-error', 'totp-section', 'recovery-section']) expect(has(testid), testid).toBe(false);
    expect(wrapper.find('.non-field-error').exists()).toBe(false);
  });

  it('asks nothing when spa-config already says 2FA is switched off: straight to the launcher with the notice', async () => {
    const server = fakeAllauth({ 'GET /account/authenticators': notFound });
    const { router } = await mountAccountPage(TwoFactorSettingsPage, { path: '/2fa', session: SIGNED_IN, config: { mfaEnabled: false } });
    await flushPromises();
    expect(server.callsTo('GET /account/authenticators')).toEqual([]);
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ notice: 'mfa_unavailable' });
  });

  it('says it could not load the settings and tries again on demand', async () => {
    const server = fakeAllauth({ 'GET /account/authenticators': [offline, list(TOTP)] });
    const { text, click, has } = await mountPage();
    expect(text('mfa-load-error')).toBe('We could not load your security settings. Please try again.');
    expect(text('mfa-retry')).toBe('Try again');
    await click('mfa-retry');
    expect(server.callsTo('GET /account/authenticators')).toHaveLength(2);
    expect(has('mfa-load-error')).toBe(false);
    expect(has('totp-section')).toBe(true);
  });

  it('sends a session that ended to the sign-in, coming back to /2fa', async () => {
    fakeAllauth({ 'GET /account/authenticators': anonymous });
    const { router } = await mountPage();
    expect(router.currentRoute.value.path).toBe('/launch');
    expect(router.currentRoute.value.query).toEqual({ next: '/2fa' });
  });
});

describe('TwoFactorSettingsPage: index (mfa/index.html)', () => {
  it('with the app off: «Off», what it is and «Set up authenticator app», no recovery codes', async () => {
    fakeAllauth({ 'GET /account/authenticators': list() });
    const { wrapper, text, has, button } = await mountPage();
    expect(wrapper.get('.biz-sub').text()).toBe('Two-factor authentication');
    expect(document.title).toBe('Two-factor authentication - ERPlora Cloud');
    const section = wrapper.get('[data-testid="totp-section"]');
    expect(section.get('h2').text()).toBe('Authenticator app');
    expect(section.findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:smartphone'));
    const pill = wrapper.get('[data-testid="totp-pill"]');
    expect([pill.text(), pill.classes()]).toEqual(['Off', ['pill', 'off']]);
    expect(section.get('.auth-lead').text()).toBe(
      'Codes from an app such as Google Authenticator or 1Password, asked after your password.',
    );
    const setUp = button('totp-set-up')!;
    expect([setUp.props('color'), setUp.props('expand'), setUp.text()]).toEqual(['primary', 'block', 'Set up authenticator app']);
    expect(has('totp-turn-off')).toBe(false);
    expect(has('recovery-section')).toBe(false);
    const foot = wrapper.get('.foot a');
    // Back where the «Two-step verification» row is: Account › Security (it went to the launcher).
    expect([foot.text(), foot.attributes('href')]).toEqual(['Back to settings', '/dashboard/account/security']);
    expect(text('totp-section')).not.toContain('On');
  });

  it('with the app on: «On», «Turn off», and the unused recovery codes with «View» and «Generate new»', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const { wrapper, button, has } = await mountPage();
    const pill = wrapper.get('[data-testid="totp-pill"]');
    expect([pill.text(), pill.classes()]).toEqual(['On', ['pill']]);
    expect(wrapper.get('[data-testid="totp-section"] .auth-lead').text()).toBe(
      'You are asked for a code from your app after your password.',
    );
    const turnOff = button('totp-turn-off')!;
    expect([turnOff.props('fill'), turnOff.text()]).toEqual(['outline', 'Turn off']);
    expect(has('totp-set-up')).toBe(false);
    const section = wrapper.get('[data-testid="recovery-section"]');
    expect(section.get('h2').text()).toBe('Recovery codes');
    expect(section.findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:key-round'));
    expect(section.get('.auth-lead').text()).toBe('9 unused — each one signs you in once if you lose your authenticator.');
    expect([button('recovery-view')!.props('fill'), button('recovery-view')!.text()]).toEqual(['outline', 'View']);
    expect([button('recovery-generate-new')!.props('fill'), button('recovery-generate-new')!.text()]).toEqual([
      'clear',
      'Generate new',
    ]);
  });

  it('warns when every recovery code is used, with «Generate new codes»', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(0)) });
    const { text, button, has } = await mountPage();
    expect(text('recovery-all-used')).toBe('You have used all your recovery codes. Generate a new set now.');
    expect([button('recovery-generate')!.props('color'), button('recovery-generate')!.text()]).toEqual([
      'primary',
      'Generate new codes',
    ]);
    expect(has('recovery-view')).toBe(false);
  });

  it('asks to generate recovery codes when there are none', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP) });
    const { wrapper, button } = await mountPage();
    expect(wrapper.get('[data-testid="recovery-section"] .auth-lead').text()).toBe(
      'Without them, losing your authenticator locks you out of your account.',
    );
    expect(button('recovery-generate')!.text()).toBe('Generate recovery codes');
  });

  it('speaks Spanish, one code and several in their plural', async () => {
    fakeAllauth({ 'GET /account/authenticators': [list(TOTP, recovery(1)), list(TOTP, recovery(9))] });
    const first = await mountPage('es');
    expect(first.wrapper.get('.biz-sub').text()).toBe('Verificación en dos pasos');
    expect(first.text('totp-pill')).toBe('Activada');
    expect(first.wrapper.get('[data-testid="recovery-section"] .auth-lead').text()).toBe(
      '1 sin usar — te inicia sesión una vez si pierdes tu autenticador.',
    );
    const second = await mountPage('es');
    expect(second.wrapper.get('[data-testid="recovery-section"] .auth-lead').text()).toBe(
      '9 sin usar — cada uno te inicia sesión una vez si pierdes tu autenticador.',
    );
    expect(second.button('totp-turn-off')!.text()).toBe('Desactivar');
  });
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

describe('TwoFactorSettingsPage: the recovery codes (mfa/recovery_codes/index.html)', () => {
  async function openCodes(answer: Answer, more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(9)),
      'GET /account/authenticators/recovery-codes': answer,
      ...more,
    });
    const page = await mountPage();
    await page.click('recovery-view');
    return { ...page, server };
  }

  it('lists the unused codes one per line, how many are left, «Download» and «Generate new codes»', async () => {
    const { wrapper, text, button } = await openCodes(codes(CODES, 3, 10));
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:key-round'));
    expect(wrapper.get('h2.auth-title').text()).toBe('Recovery codes');
    expect(text('codes-lead')).toBe('Each code signs you in once if you lose your authenticator. Keep them somewhere safe.');
    const pre = wrapper.get('pre[data-testid="codes-list"]');
    expect([pre.text(), pre.classes()]).toEqual([CODES.join('\n'), ['recovery-codes']]);
    expect(text('codes-count')).toBe('3 of 10 unused');
    expect([button('codes-download')!.props('fill'), button('codes-download')!.text()]).toEqual(['outline', 'Download']);
    expect([button('codes-generate')!.props('fill'), button('codes-generate')!.text()]).toEqual(['outline', 'Generate new codes']);
    expect(button('codes-back')!.text()).toBe('Back');
    expect(document.title).toBe('Recovery codes - ERPlora Cloud');
  });

  it('counts the codes allauth hides, without listing nor downloading them', async () => {
    const { has, text } = await openCodes(codes([], 9, 10));
    expect(has('codes-list')).toBe(false);
    expect(text('codes-count')).toBe('9 of 10 unused');
    expect(has('codes-download')).toBe(false);
  });

  it('warns when none is left, with nothing to download', async () => {
    const { has, text } = await openCodes(codes([], 0, 10));
    expect(text('codes-none')).toBe('You have no codes left. Generate a new set now, before you need one.');
    expect(has('codes-count')).toBe(false);
    expect(has('codes-download')).toBe(false);
    expect(has('codes-generate')).toBe(true);
  });

  it('downloads them as erplora-recovery-codes.txt, one per line, built here (no server route)', async () => {
    const page = await openCodes(codes(CODES, 3, 10));
    const blobs: Blob[] = [];
    const createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return 'blob:recovery-codes';
    });
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    await page.click('codes-download');
    expect(clicked).toHaveLength(1);
    expect([clicked[0].download, clicked[0].getAttribute('href')]).toEqual(['erplora-recovery-codes.txt', 'blob:recovery-codes']);
    expect(blobs[0].type).toBe('text/plain');
    expect(await blobs[0].text()).toBe(`${CODES.join('\n')}\n`);
    expect(page.server.calls.filter((c) => c.path.includes('download'))).toEqual([]);
  });

  it('goes to confirm it is you when reading them needs a recent login', async () => {
    const { router } = await openCodes(reauthenticationRequired());
    expect(router.currentRoute.value.path).toBe('/reauthenticate');
    expect(router.currentRoute.value.query).toMatchObject({ next: '/2fa', method: 'totp' });
  });

  it('«Back» shows the settings again, read anew', async () => {
    const page = await openCodes(codes(CODES, 3, 10));
    await page.click('codes-back');
    expect(page.server.callsTo('GET /account/authenticators')).toHaveLength(2);
    expect(page.has('recovery-section')).toBe(true);
  });

  it('speaks Spanish', async () => {
    fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(9)),
      'GET /account/authenticators/recovery-codes': codes(CODES, 3, 10),
    });
    const page = await mountPage('es');
    await page.click('recovery-view');
    expect(page.text('codes-count')).toBe('3 de 10 sin usar');
    expect(page.button('codes-download')!.text()).toBe('Descargar');
  });
});

describe('TwoFactorSettingsPage: new recovery codes (mfa/recovery_codes/generate.html)', () => {
  async function openRegenerate(unused: number, more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(unused)), ...more });
    const page = await mountPage();
    await page.click(unused ? 'recovery-generate-new' : 'recovery-generate');
    return { ...page, server };
  }

  it('says how many unused codes it throws away, in its plural', async () => {
    const several = await openRegenerate(9);
    expect(several.wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:refresh-cw'));
    expect(several.wrapper.get('h2.auth-title').text()).toBe('Generate new recovery codes?');
    expect(several.text('regenerate-lead')).toBe('This replaces your 9 unused codes.');
    const submit = several.button('regenerate-submit')!;
    expect([submit.props('color'), submit.props('size'), submit.text()]).toEqual(['primary', 'large', 'Generate']);
    expect([several.button('regenerate-cancel')!.props('fill'), several.button('regenerate-cancel')!.text()]).toEqual(['clear', 'Cancel']);
    expect((await openRegenerate(1)).text('regenerate-lead')).toBe('This replaces your 1 unused code.');
  });

  it('says nothing is thrown away when none is left', async () => {
    const { text } = await openRegenerate(0);
    expect(text('regenerate-lead')).toBe('You have no unused codes left, so nothing is thrown away.');
  });

  it('generates them and shows the new set', async () => {
    const fresh = ['n1n1-n1n1', 'n2n2-n2n2'];
    const page = await openRegenerate(9, { 'POST /account/authenticators/recovery-codes': codes(fresh, 2, 2) });
    await page.click('regenerate-submit');
    expect(page.server.callsTo('POST /account/authenticators/recovery-codes')).toHaveLength(1);
    expect(page.text('codes-list')).toBe(fresh.join('\n'));
    expect(page.text('codes-count')).toBe('2 of 2 unused');
  });

  it('goes to confirm it is you when generating needs a recent login', async () => {
    const page = await openRegenerate(9, { 'POST /account/authenticators/recovery-codes': reauthenticationRequired(['mfa_reauthenticate']) });
    await page.click('regenerate-submit');
    expect(page.router.currentRoute.value.path).toBe('/reauthenticate');
    expect(page.router.currentRoute.value.query).toEqual({ next: '/2fa', method: 'totp', flows: 'mfa_reauthenticate' });
  });

  it('says why allauth will not generate them, and stays', async () => {
    const page = await openRegenerate(9, {
      'POST /account/authenticators/recovery-codes': rejected('You cannot generate recovery codes.', undefined, 'cannot_generate_recovery_codes'),
    });
    await page.click('regenerate-submit');
    expect(page.text('failure')).toBe('You cannot generate recovery codes.');
    expect(page.has('regenerate-view')).toBe(true);
  });

  it('says something went wrong when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)), 'POST /account/authenticators/recovery-codes': offline });
    const page = await mountPage('es');
    await page.click('recovery-generate-new');
    await page.click('regenerate-submit');
    expect(page.text('failure')).toBe('Algo ha ido mal. Inténtalo de nuevo.');
  });

  it('«Cancel» goes back to where it came from: the settings, or the codes', async () => {
    const fromIndex = await openRegenerate(9);
    await fromIndex.click('regenerate-cancel');
    expect(fromIndex.has('recovery-section')).toBe(true);

    fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(3)),
      'GET /account/authenticators/recovery-codes': codes(CODES, 3, 10),
    });
    const fromCodes = await mountPage();
    await fromCodes.click('recovery-view');
    await fromCodes.click('codes-generate');
    expect(fromCodes.text('regenerate-lead')).toBe('This replaces your 3 unused codes.');
    await fromCodes.click('regenerate-cancel');
    expect(fromCodes.text('codes-list')).toBe(CODES.join('\n'));
  });
});

// flow: ACCOUNTS-F17 — the trusted browsers (old «Dispositivos de confianza»): whether this one is trusted and until when
// (allauth keeps no list, so only this browser can be told), and «Stop trusting all browsers».
describe('TwoFactorSettingsPage: the trusted browsers', () => {
  const UNTIL = '2026-11-04T10:00:00Z';
  /** `client.api.call` answering the trust of this browser with `trust`, and the revocation with `revoke`. */
  function api(trust: () => Promise<unknown>, revoke: () => Promise<unknown> = () => Promise.resolve({ trusted_until: null })) {
    return vi.fn((op: string) => {
      if (op === 'accounts.browser_trust.get') return trust();
      if (op === 'accounts.browser_trust.revoke') return revoke();
      return new Promise(() => undefined);
    });
  }

  it('with the app on, says this browser is trusted and until when, with «Stop trusting all browsers»', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const call = api(() => Promise.resolve({ trusted_until: UNTIL }));
    const { wrapper, button, text } = await mountPage('en', { call });
    expect(call).toHaveBeenCalledWith('accounts.browser_trust.get');
    const section = wrapper.get('[data-testid="trust-section"]');
    expect(section.get('h2').text()).toBe('Trusted browsers');
    expect(section.findComponent(IonIcon).props('icon')).toBe(ionIconSrc('laptop-outline'));
    expect(text('trust-lead')).toBe('Browsers you trust skip the code from your app for 14 days.');
    expect(text('trust-this')).toBe(`This browser is trusted until ${formatDateTime(UNTIL, 'en')}.`);
    const revoke = button('trust-revoke')!;
    expect([revoke.props('fill'), revoke.props('expand'), revoke.text()]).toEqual(['outline', 'block', 'Stop trusting all browsers']);
  });

  it('says when this browser is not trusted', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const { text } = await mountPage('en', { call: api(() => Promise.resolve({ trusted_until: null })) });
    expect(text('trust-this')).toBe('This browser is not trusted.');
  });

  it('says it could not check this browser, and still offers to stop trusting them all', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const { text, has } = await mountPage('en', { call: api(() => Promise.reject(new Error('offline'))) });
    expect(text('trust-this')).toBe('We could not check this browser.');
    expect(has('trust-revoke')).toBe(true);
  });

  it('has nothing to say without the app', async () => {
    fakeAllauth({ 'GET /account/authenticators': list() });
    const call = api(() => Promise.resolve({ trusted_until: UNTIL }));
    const { has } = await mountPage('en', { call });
    expect(has('trust-section')).toBe(false);
  });

  it('«Stop trusting all browsers» ends the trust of every one, this one too, and says so', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const call = api(() => Promise.resolve({ trusted_until: UNTIL }));
    const { click, text } = await mountPage('en', { call });
    await click('trust-revoke');
    expect(call).toHaveBeenCalledWith('accounts.browser_trust.revoke');
    expect(text('trust-this')).toBe('This browser is not trusted.');
    expect(text('trust-done')).toBe('No browser is trusted now: each one will ask for the code from your app at its next sign-in.');
  });

  it('says something went wrong when it could not stop trusting them, and keeps what it knew', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const call = api(
      () => Promise.resolve({ trusted_until: UNTIL }),
      () => Promise.reject(new Error('offline')),
    );
    const { click, text, has } = await mountPage('en', { call });
    await click('trust-revoke');
    expect(text('failure')).toBe('Something went wrong. Please try again.');
    expect(text('trust-this')).toBe(`This browser is trusted until ${formatDateTime(UNTIL, 'en')}.`);
    expect(has('trust-done')).toBe(false);
  });

  it('speaks Spanish', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)) });
    const { text, button, click } = await mountPage('es', { call: api(() => Promise.resolve({ trusted_until: UNTIL })) });
    expect(text('trust-lead')).toBe('Los navegadores en los que confías no piden el código de tu app durante 14 días.');
    expect(text('trust-this')).toBe(`Este navegador es de confianza hasta el ${formatDateTime(UNTIL, 'es')}.`);
    expect(button('trust-revoke')!.text()).toBe('Dejar de confiar en todos los navegadores');
    await click('trust-revoke');
    expect(text('trust-done')).toBe(
      'Ya no confías en ningún navegador: cada uno te pedirá el código de tu app la próxima vez que entres.',
    );
  });
});

// flow: ACCOUNTS-F20 — the staff kept out of the admin for lack of the app land here with `?next=/admin/…`: the page
// says the app is needed to go on and, once it is on, «Continue» goes back there (a page of Django: a full load).
describe('TwoFactorSettingsPage: setting the app up to go on (next)', () => {
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
  });

  it('says the app is needed to continue while it is off, with no «Continue» yet', async () => {
    fakeAllauth({ 'GET /account/authenticators': list() });
    const { text, has, wrapper } = await mountPage('en', { path: '/2fa?next=%2Fadmin%2Faccounts%2Fuser%2F' });
    expect(text('mfa-required')).toBe('Turn on the authenticator app to continue.');
    // A notice of what is still to do, not an error: the warning banner, never the red error box.
    const notice = wrapper.get('[data-testid="mfa-required"]');
    expect([notice.attributes('data-tone'), notice.classes('non-field-error')]).toEqual(['warning', false]);
    expect(has('mfa-continue')).toBe(false);
  });

  it('once the app is on, «Continue» goes back to next', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(10)) });
    const { button, click, has } = await mountPage('en', { path: '/2fa?next=%2Fadmin%2Faccounts%2Fuser%2F' });
    expect(has('mfa-required')).toBe(false);
    const go = button('mfa-continue')!;
    expect([go.props('color'), go.props('expand'), go.text()]).toEqual(['primary', 'block', 'Continue']);
    await click('mfa-continue');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/admin/accounts/user/');
  });

  it('speaks Spanish', async () => {
    fakeAllauth({ 'GET /account/authenticators': list() });
    const { text } = await mountPage('es', { path: '/2fa?next=%2Fadmin%2F' });
    expect(text('mfa-required')).toBe('Activa la app autenticadora para continuar.');
  });

  it('never goes to a next of another site', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(10)) });
    const { has } = await mountPage('en', { path: `/2fa?next=${encodeURIComponent('//evil.example.com/')}` });
    expect(has('mfa-continue')).toBe(false);
    expect(has('mfa-required')).toBe(false);
  });

  it("keeps next through «Confirm it's you» and a sign-in, so it still goes back there", async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)), 'DELETE /account/authenticators/totp': reauthenticationRequired() });
    const page = await mountPage('en', { path: '/2fa?next=%2Fadmin%2F' });
    await page.click('totp-turn-off');
    await page.click('deactivate-submit');
    expect(page.router.currentRoute.value.path).toBe('/reauthenticate');
    expect(page.router.currentRoute.value.query.next).toBe('/2fa?next=%2Fadmin%2F');

    fakeAllauth({ 'GET /account/authenticators': anonymous });
    const ended = await mountPage('en', { path: '/2fa?next=%2Fadmin%2F' });
    expect(ended.router.currentRoute.value.path).toBe('/launch');
    expect(ended.router.currentRoute.value.query).toEqual({ next: '/2fa?next=%2Fadmin%2F' });
  });

  it('without next, neither the notice nor «Continue»', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(10)) });
    const { has } = await mountPage();
    expect(has('mfa-continue')).toBe(false);
    expect(has('mfa-required')).toBe(false);
  });
});
