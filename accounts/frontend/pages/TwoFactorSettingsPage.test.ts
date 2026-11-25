// The two-factor settings (`/2fa`), over allauth.headless: one page whose views are the templates
// `mfa/index.html` (the authenticator app and the recovery codes), `mfa/totp/activate_form.html`,
// `mfa/totp/deactivate_form.html`, `mfa/recovery_codes/index.html` and `generate.html`; the URL
// stays `/2fa`. A change that needs a recent login goes to `/reauthenticate` and back; 2FA switched
// off on the server (404) sends to the launcher with a notice.
// clock: data only — no code under test compares these dates with now.
import { formatDateTime } from '@erplora/ui/components';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonIcon } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { anonymous, fakeAllauth, held, notFound, offline, reauthenticationRequired } from '../__tests__/allauth-server';
import { mountAccountPage, SIGNED_IN } from '../__tests__/mount-account-page';
import { list, mountPage, recovery, setUpTwoFactorSettingsPage, TOTP } from '../__tests__/two-factor-settings-page';
import TwoFactorSettingsPage from './TwoFactorSettingsPage.vue';

setUpTwoFactorSettingsPage();

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

  it('holds its buttons while what one of them asked is on its way', async () => {
    const answer = held(offline);
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)), 'GET /account/authenticators/recovery-codes': answer.answer });
    const { button, click } = await mountPage();
    const free = () => ['totp-turn-off', 'recovery-view', 'trust-revoke'].filter((testid) => !button(testid)!.props('disabled'));
    expect(free()).toEqual(['totp-turn-off', 'recovery-view', 'trust-revoke']);
    await click('recovery-view');
    expect(free()).toEqual([]);
    answer.release();
    await flushPromises();
    expect(free()).toEqual(['totp-turn-off', 'recovery-view', 'trust-revoke']);
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
