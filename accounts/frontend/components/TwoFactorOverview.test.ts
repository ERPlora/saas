// The index of the two-factor settings (`mfa/index.html`) on its own: what it paints from the props the page hands
// it (the app, its recovery codes and the trusted browsers of ACCOUNTS-F17) and what each button asks the page to do.
// The texts in both languages are the page's tests' (TwoFactorSettingsPage.test.ts), which paint it through the page.
// clock: data only — no code under test compares these dates with now.
import { formatDateTime } from '@erplora/ui/components';
import type { Authenticator } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonIcon } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountTwoFactorPiece, recovery } from '../__tests__/two-factor-settings-page';
import TwoFactorOverview from './TwoFactorOverview.vue';

interface Props {
  next: string | undefined;
  totpOn: boolean;
  recoveryAuthenticator: Authenticator | undefined;
  trustedUntil: string | null | undefined;
  trustUnknown: boolean;
  trustRevoked: boolean;
  busy: boolean;
}

const UNTIL = '2026-11-04T10:00:00Z';
const OFF: Props = {
  next: undefined,
  totpOn: false,
  recoveryAuthenticator: undefined,
  trustedUntil: undefined,
  trustUnknown: false,
  trustRevoked: false,
  busy: false,
};
const ON: Props = { ...OFF, totpOn: true, recoveryAuthenticator: recovery(9) as Authenticator };

const mountOverview = (props: Partial<Props>) => mountTwoFactorPiece(TwoFactorOverview, { ...OFF, ...props });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TwoFactorOverview', () => {
  it('with the app off paints only the app, «Off», and «Set up authenticator app» asks for the setup', async () => {
    const { wrapper, button, has } = await mountOverview(OFF);
    expect(wrapper.findAllComponents(IonIcon).map((icon) => icon.props('icon'))).toEqual([ionIconSrc('lucide:smartphone')]);
    expect(wrapper.get('[data-testid="totp-pill"]').classes()).toEqual(['pill', 'off']);
    await button('totp-set-up')!.trigger('click');
    expect(wrapper.emitted('setUp')).toEqual([[]]);
    expect(['totp-turn-off', 'recovery-section', 'trust-section', 'mfa-required', 'mfa-continue'].filter(has)).toEqual([]);
  });

  it('with the app on paints the app, its codes and the trusted browsers, in that order, and «Turn off» asks to', async () => {
    const { wrapper, button, has } = await mountOverview(ON);
    const sections = wrapper.findAll('.auth-section').map((section) => section.attributes('data-testid'));
    expect(sections).toEqual(['totp-section', 'recovery-section', 'trust-section']);
    expect(wrapper.findAllComponents(IonIcon).map((icon) => icon.props('icon'))).toEqual([
      ionIconSrc('lucide:smartphone'),
      ionIconSrc('lucide:key-round'),
      ionIconSrc('laptop-outline'),
    ]);
    expect(wrapper.get('[data-testid="totp-pill"]').classes()).toEqual(['pill']);
    await button('totp-turn-off')!.trigger('click');
    expect(wrapper.emitted('turnOff')).toEqual([[]]);
    expect(has('totp-set-up')).toBe(false);
  });

  it('counts the unused codes it is given; «View» asks for them and «Generate new» for a new set', async () => {
    const { wrapper, button, has } = await mountOverview({ ...ON, recoveryAuthenticator: recovery(1) as Authenticator });
    expect(wrapper.get('[data-testid="recovery-section"] .auth-lead').text()).toMatch(/^1 unused — each one signs/);
    await button('recovery-view')!.trigger('click');
    await button('recovery-generate-new')!.trigger('click');
    expect([wrapper.emitted('viewCodes'), wrapper.emitted('regenerate')]).toEqual([[[]], [[]]]);
    expect([has('recovery-all-used'), has('recovery-generate')]).toEqual([false, false]);
  });

  it('with every code used, or none, asks for a new set with its own button', async () => {
    const allUsed = await mountOverview({ ...ON, recoveryAuthenticator: recovery(0) as Authenticator });
    const none = await mountOverview({ ...ON, recoveryAuthenticator: undefined });
    expect([allUsed.has('recovery-all-used'), none.has('recovery-all-used'), allUsed.has('recovery-view')]).toEqual([true, false, false]);
    for (const { wrapper, button } of [allUsed, none]) {
      await button('recovery-generate')!.trigger('click');
      expect(wrapper.emitted('regenerate')).toEqual([[]]);
    }
  });

  it('tells the trust of this browser from what it is given, and «Stop trusting all browsers» asks to stop', async () => {
    const trusted = await mountOverview({ ...ON, trustedUntil: UNTIL });
    expect(trusted.text('trust-this')).toContain(formatDateTime(UNTIL, 'en'));
    expect((await mountOverview({ ...ON, trustedUntil: null })).text('trust-this')).toBe('This browser is not trusted.');
    expect((await mountOverview({ ...ON, trustUnknown: true })).text('trust-this')).toBe('We could not check this browser.');
    expect((await mountOverview(ON)).has('trust-this')).toBe(false);
    await trusted.button('trust-revoke')!.trigger('click');
    expect(trusted.wrapper.emitted('revokeTrust')).toEqual([[]]);
  });

  it('says every browser stopped being trusted once the page says it did', async () => {
    expect((await mountOverview(ON)).has('trust-done')).toBe(false);
    const { wrapper } = await mountOverview({ ...ON, trustedUntil: null, trustRevoked: true });
    expect(wrapper.get('[data-testid="trust-done"]').attributes('role')).toBe('status');
  });

  it('coming from a page that needs the app, says so until it is on; then «Continue» goes back there in full', async () => {
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const off = await mountOverview({ next: '/admin/' });
    expect([off.has('mfa-required'), off.has('mfa-continue')]).toEqual([true, false]);
    const on = await mountOverview({ ...ON, next: '/admin/accounts/user/' });
    expect(on.has('mfa-required')).toBe(false);
    await on.button('mfa-continue')!.trigger('click');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/admin/accounts/user/');
  });

  it('holds every button that changes something while the page is busy', async () => {
    const on = await mountOverview({ ...ON, busy: true });
    const off = await mountOverview({ ...OFF, busy: true });
    const held = [
      ...['totp-turn-off', 'recovery-view', 'recovery-generate-new', 'trust-revoke'].map((testid) => on.button(testid)!),
      off.button('totp-set-up')!,
    ];
    expect(held.map((button) => button.props('disabled'))).toEqual([true, true, true, true, true]);
  });
});
