// Setting up the authenticator app (`mfa/totp/activate_form.html`) on its own: the QR and the key the page hands it,
// the code typed back to the page, and the recent login allauth may ask for on the way, confirmed right here.
// The texts and the calls to allauth are the page's tests' (TwoFactorSettingsPage.authenticator-app.test.ts).
import { ionIconSrc } from '@erplora/ui/shell';
import { IonIcon, IonInput } from '@ionic/vue';
import { describe, expect, it, vi } from 'vitest';

import { mountTwoFactorPiece } from '../__tests__/two-factor-settings-page';
import TotpActivateView from './TotpActivateView.vue';

type Control = HTMLElement & { errorText?: string };

const SETUP = { secret: 'JBSWY3DPEHPK3PXP', totpUrl: 'otpauth://totp/ERPlora:owner?secret=JBSWY3DPEHPK3PXP' };
const QR = 'data:image/png;base64,QR';

async function mountActivate(props: Record<string, unknown> = {}) {
  const models = { 'onUpdate:code': vi.fn(), 'onUpdate:confirmPassword': vi.fn(), 'onUpdate:confirmCode': vi.fn() };
  const base = { setup: SETUP, qrDataUrl: QR, confirmWith: null, busy: false, fields: {}, code: '', confirmPassword: '', confirmCode: '' };
  const piece = await mountTwoFactorPiece(TotpActivateView, { ...base, ...models, ...props });
  const input = (testid: string) => piece.wrapper.findAllComponents(IonInput).find((i) => i.attributes('data-testid') === testid)!;
  return { ...piece, models, input };
}

describe('TotpActivateView: the setup', () => {
  it('paints the QR and the key it is given', async () => {
    const { wrapper, has } = await mountActivate();
    expect([has('activate-view'), has('activate-confirm')]).toEqual([true, false]);
    expect(wrapper.get('img[data-testid="totp-qr"]').attributes('src')).toBe(QR);
    expect(wrapper.get('code.auth-secret').text()).toBe(SETUP.secret);
    expect(wrapper.get('[data-testid="activate-cant-scan"]').classes()).toEqual(['auth-lead', 'secret-lead']);
  });

  it('hands the code typed back to the page; «Turn on» and «Cancel» ask the page', async () => {
    const { wrapper, models, input, button } = await mountActivate();
    await input('code').setValue('654321');
    expect(models['onUpdate:code']).toHaveBeenLastCalledWith('654321');
    await wrapper.get('form[data-testid="activate-form"]').trigger('submit');
    await button('activate-cancel')!.trigger('click');
    expect([wrapper.emitted('turnOn'), wrapper.emitted('cancel')]).toEqual([[[]], [[]]]);
    expect(wrapper.emitted('confirm')).toBeUndefined();
  });

  it('paints the code’s error it is given under the input, and holds its buttons while the page is busy', async () => {
    const { input, button } = await mountActivate({ fields: { code: 'Incorrect code.' }, busy: true });
    expect((input('code').element as Control).errorText).toBe('Incorrect code.');
    expect(['activate-submit', 'activate-cancel'].map((testid) => button(testid)!.props('disabled'))).toEqual([true, true]);
  });
});

describe('TotpActivateView: confirming a recent login', () => {
  it('asks for the password instead of the QR, and hands it and its error to and from the page', async () => {
    const { wrapper, models, input, has } = await mountActivate({ confirmWith: 'password', fields: { password: 'Incorrect password.' } });
    expect([has('activate-confirm'), has('totp-qr'), has('code')]).toEqual([true, false, false]);
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:lock'));
    const password = input('confirm-password');
    expect([password.props('type'), password.attributes('mode'), (password.element as Control).errorText]).toEqual([
      'password',
      'md',
      'Incorrect password.',
    ]);
    await password.setValue('owner');
    expect(models['onUpdate:confirmPassword']).toHaveBeenLastCalledWith('owner');
  });

  it('asks for an authenticator code when that is the way, and hands it and its error to and from the page', async () => {
    const { wrapper, models, input, has } = await mountActivate({ confirmWith: 'code', fields: { code: 'Incorrect code.' } });
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:shield-check'));
    expect(has('confirm-password')).toBe(false);
    expect((input('code').element as Control).errorText).toBe('Incorrect code.');
    await input('code').setValue('777777');
    expect(models['onUpdate:confirmCode']).toHaveBeenLastCalledWith('777777');
    expect(models['onUpdate:code']).not.toHaveBeenCalled();
  });

  it('«Confirm» and «Cancel» ask the page, and wait while it is busy', async () => {
    const { wrapper, button } = await mountActivate({ confirmWith: 'password' });
    await wrapper.get('form[data-testid="confirm-form"]').trigger('submit');
    await button('confirm-cancel')!.trigger('click');
    expect([wrapper.emitted('confirm'), wrapper.emitted('cancelConfirm')]).toEqual([[[]], [[]]]);
    expect(wrapper.emitted('turnOn')).toBeUndefined();
    const busy = await mountActivate({ confirmWith: 'password', busy: true });
    expect(['confirm-submit', 'confirm-cancel'].map((testid) => busy.button(testid)!.props('disabled'))).toEqual([true, true]);
  });
});
